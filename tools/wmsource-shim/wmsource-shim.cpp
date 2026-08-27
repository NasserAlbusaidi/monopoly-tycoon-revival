// wmsource-shim: a stand-in for the 2001 "Windows Media Source Filter"
// (CLSID {6B6D0800-9ADA-11D0-A520-00A0D10129C0}, dxmasf.dll) that Monopoly
// Tycoon creates to play its WMA soundtrack. Modern Windows no longer
// registers that class, so the game's CoCreateInstance fails and the game
// later dereferences the null pointer.
//
// The shim aggregates the filter that replaced it, the WM ASF Reader
// (qasf.dll), with two adaptations the game needs:
//   1. The reader refuses a second Load() on one instance, and the game
//      loads every track into the same filter. Each Load() therefore creates
//      a fresh reader and retires the old one.
//   2. The game asks FindPin(L"Stream 1"); the reader names its pin
//      "Raw Audio 0". "Stream N" is answered with the N-th output pin.
// Everything else is forwarded to the current reader. Aggregation keeps
// COM identity: the reader's pins report a filter whose IUnknown is this
// object, which is what the filter graph holds.
//
// Build (x86 only; the game is 32-bit): tools\wmsource-shim\build.ps1.
// Register per user: mtrevival fix --music (see docs\music.md).
// Trace: set WMSOURCE_SHIM_LOG=<file>; lines also go to OutputDebugString.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dshow.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "uuid.lib")
#pragma comment(lib, "strmiids.lib")

namespace {

const CLSID kLegacySource = {
    0x6b6d0800, 0x9ada, 0x11d0, {0xa5, 0x20, 0x00, 0xa0, 0xd1, 0x01, 0x29, 0xc0}};
const CLSID kAsfReader = {
    0x187463a0, 0x5bb7, 0x11d3, {0xac, 0xbe, 0x00, 0x80, 0xc7, 0x5e, 0x24, 0x6e}};

LONG g_objects = 0;
LONG g_locks = 0;

void Log(const char* fmt, ...) {
  char buf[600];
  va_list ap;
  va_start(ap, fmt);
  _vsnprintf_s(buf, sizeof buf, _TRUNCATE, fmt, ap);
  va_end(ap);
  OutputDebugStringA(buf);
  OutputDebugStringA("\n");
  static char path[MAX_PATH];
  static bool resolved = false;
  if (!resolved) {
    resolved = true;
    GetEnvironmentVariableA("WMSOURCE_SHIM_LOG", path, MAX_PATH);
  }
  if (path[0] == 0) return;
  FILE* f = nullptr;
  if (fopen_s(&f, path, "a") == 0 && f != nullptr) {
    fprintf(f, "%s\n", buf);
    fclose(f);
  }
}

// Parses L"Stream N" into N, or returns 0 when the id has another shape.
int StreamIndex(LPCWSTR id) {
  if (id == nullptr || wcsncmp(id, L"Stream ", 7) != 0) return 0;
  int n = 0;
  for (const wchar_t* p = id + 7; *p != 0; ++p) {
    if (*p < L'0' || *p > L'9') return 0;
    n = n * 10 + (*p - L'0');
  }
  return n;
}

class Shim : public IBaseFilter, public IFileSourceFilter {
 public:
  Shim() { InterlockedIncrement(&g_objects); }
  ~Shim() {
    ref_ = 0x40000000;  // inner releases delegate here; stay off zero
    Retire();
    InterlockedDecrement(&g_objects);
  }

  IUnknown* Controlling() { return static_cast<IBaseFilter*>(this); }

  // Creates the initial reader so AddFilter/JoinFilterGraph have a target.
  HRESULT Create() { return Swap(nullptr, nullptr); }

  // IUnknown
  STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
    if (ppv == nullptr) return E_POINTER;
    if (riid == IID_IUnknown || riid == IID_IPersist ||
        riid == IID_IMediaFilter || riid == IID_IBaseFilter) {
      *ppv = static_cast<IBaseFilter*>(this);
      AddRef();
      return S_OK;
    }
    if (riid == IID_IFileSourceFilter) {
      *ppv = static_cast<IFileSourceFilter*>(this);
      AddRef();
      return S_OK;
    }
    *ppv = nullptr;
    return inner_ != nullptr ? inner_->QueryInterface(riid, ppv) : E_NOINTERFACE;
  }
  STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref_); }
  STDMETHODIMP_(ULONG) Release() override {
    ULONG n = InterlockedDecrement(&ref_);
    if (n == 0) delete this;
    return n;
  }

  // IPersist
  STDMETHODIMP GetClassID(CLSID* id) override {
    if (id == nullptr) return E_POINTER;
    *id = kLegacySource;
    return S_OK;
  }

  // IMediaFilter
  STDMETHODIMP Stop() override { return filter_->Stop(); }
  STDMETHODIMP Pause() override { return filter_->Pause(); }
  STDMETHODIMP Run(REFERENCE_TIME start) override { return filter_->Run(start); }
  STDMETHODIMP GetState(DWORD ms, FILTER_STATE* state) override {
    return filter_->GetState(ms, state);
  }
  STDMETHODIMP SetSyncSource(IReferenceClock* clock) override {
    return filter_->SetSyncSource(clock);
  }
  STDMETHODIMP GetSyncSource(IReferenceClock** clock) override {
    return filter_->GetSyncSource(clock);
  }

  // IBaseFilter
  STDMETHODIMP EnumPins(IEnumPins** pins) override { return filter_->EnumPins(pins); }
  STDMETHODIMP FindPin(LPCWSTR id, IPin** pin) override {
    HRESULT hr = filter_->FindPin(id, pin);
    if (SUCCEEDED(hr)) return hr;
    int n = StreamIndex(id);
    if (n < 1) return hr;
    hr = NthOutputPin(n, pin);
    Log("FindPin(%ls) -> output pin %d: 0x%08lX", id, n, (unsigned long)hr);
    return hr;
  }
  STDMETHODIMP QueryFilterInfo(FILTER_INFO* info) override {
    return filter_->QueryFilterInfo(info);
  }
  STDMETHODIMP JoinFilterGraph(IFilterGraph* graph, LPCWSTR name) override {
    graph_ = graph;
    if (name != nullptr) {
      wcsncpy_s(name_, name, _TRUNCATE);
    } else {
      name_[0] = 0;
    }
    return filter_->JoinFilterGraph(graph, name);
  }
  STDMETHODIMP QueryVendorInfo(LPWSTR* info) override {
    return filter_->QueryVendorInfo(info);
  }

  // IFileSourceFilter
  STDMETHODIMP Load(LPCOLESTR file, const AM_MEDIA_TYPE* type) override {
    HRESULT hr = Swap(file, type);
    Log("Load(%ls): 0x%08lX", file != nullptr ? file : L"(null)", (unsigned long)hr);
    return hr;
  }
  STDMETHODIMP GetCurFile(LPOLESTR* file, AM_MEDIA_TYPE* type) override {
    return source_->GetCurFile(file, type);
  }

 private:
  // Creates a fresh aggregated reader, loads the file into it, and on
  // success retires the previous reader. On failure the previous reader
  // stays, so a bad path leaves the graph as it was.
  HRESULT Swap(LPCOLESTR file, const AM_MEDIA_TYPE* type) {
    IUnknown* inner = nullptr;
    HRESULT hr = CoCreateInstance(kAsfReader, Controlling(), CLSCTX_INPROC_SERVER,
                                  IID_IUnknown, reinterpret_cast<void**>(&inner));
    if (FAILED(hr)) {
      Log("CoCreateInstance(WM ASF Reader) failed: 0x%08lX", (unsigned long)hr);
      return hr;
    }
    IBaseFilter* filter = nullptr;
    IFileSourceFilter* source = nullptr;
    // Interfaces from the non-delegating unknown AddRef the outer (us);
    // cancel that so the cached pointers do not keep us alive.
    hr = inner->QueryInterface(IID_IBaseFilter, reinterpret_cast<void**>(&filter));
    if (SUCCEEDED(hr)) {
      Release();
      hr = inner->QueryInterface(IID_IFileSourceFilter, reinterpret_cast<void**>(&source));
      if (SUCCEEDED(hr)) Release();
    }
    if (FAILED(hr)) {
      Log("reader lacks IBaseFilter/IFileSourceFilter: 0x%08lX", (unsigned long)hr);
      Drop(inner, filter, source);
      return hr;
    }
    if (graph_ != nullptr) filter->JoinFilterGraph(graph_, name_[0] != 0 ? name_ : nullptr);
    if (file != nullptr) {
      hr = source->Load(file, type);
      if (FAILED(hr)) {
        filter->JoinFilterGraph(nullptr, nullptr);
        Drop(inner, filter, source);
        return hr;
      }
    }
    Retire();
    inner_ = inner;
    filter_ = filter;
    source_ = source;
    return hr;
  }

  // Stops the graph, disconnects the current reader's pins, releases it.
  void Retire() {
    if (inner_ == nullptr) return;
    if (graph_ != nullptr) {
      IMediaControl* control = nullptr;
      if (SUCCEEDED(graph_->QueryInterface(IID_IMediaControl,
                                           reinterpret_cast<void**>(&control)))) {
        control->Stop();
        control->Release();
      }
    }
    DisconnectAll(filter_);
    filter_->JoinFilterGraph(nullptr, nullptr);
    Drop(inner_, filter_, source_);
    inner_ = nullptr;
    filter_ = nullptr;
    source_ = nullptr;
  }

  void Drop(IUnknown* inner, IBaseFilter* filter, IFileSourceFilter* source) {
    if (filter != nullptr) {
      AddRef();
      filter->Release();
    }
    if (source != nullptr) {
      AddRef();
      source->Release();
    }
    if (inner != nullptr) inner->Release();
  }

  void DisconnectAll(IBaseFilter* filter) {
    IEnumPins* pins = nullptr;
    if (FAILED(filter->EnumPins(&pins))) return;
    IPin* pin = nullptr;
    while (pins->Next(1, &pin, nullptr) == S_OK) {
      IPin* peer = nullptr;
      if (pin->ConnectedTo(&peer) == S_OK && peer != nullptr) {
        if (graph_ != nullptr) {
          graph_->Disconnect(peer);
          graph_->Disconnect(pin);
        } else {
          peer->Disconnect();
          pin->Disconnect();
        }
        peer->Release();
      }
      pin->Release();
    }
    pins->Release();
  }

  HRESULT NthOutputPin(int n, IPin** out) {
    *out = nullptr;
    IEnumPins* pins = nullptr;
    HRESULT hr = filter_->EnumPins(&pins);
    if (FAILED(hr)) return hr;
    hr = VFW_E_NOT_FOUND;
    IPin* pin = nullptr;
    int seen = 0;
    while (pins->Next(1, &pin, nullptr) == S_OK) {
      PIN_DIRECTION dir;
      if (SUCCEEDED(pin->QueryDirection(&dir)) && dir == PINDIR_OUTPUT && ++seen == n) {
        *out = pin;
        hr = S_OK;
        break;
      }
      pin->Release();
    }
    pins->Release();
    return hr;
  }

  LONG ref_ = 1;
  IUnknown* inner_ = nullptr;          // reader's non-delegating unknown (owned)
  IBaseFilter* filter_ = nullptr;      // reader interfaces, outer refs cancelled
  IFileSourceFilter* source_ = nullptr;
  IFilterGraph* graph_ = nullptr;      // not AddRef'd, per DirectShow rules
  WCHAR name_[MAX_FILTER_NAME] = {};
};

class Factory : public IClassFactory {
 public:
  Factory() { InterlockedIncrement(&g_objects); }
  ~Factory() { InterlockedDecrement(&g_objects); }

  STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
    if (ppv == nullptr) return E_POINTER;
    if (riid == IID_IUnknown || riid == IID_IClassFactory) {
      *ppv = static_cast<IClassFactory*>(this);
      AddRef();
      return S_OK;
    }
    *ppv = nullptr;
    return E_NOINTERFACE;
  }
  STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref_); }
  STDMETHODIMP_(ULONG) Release() override {
    ULONG n = InterlockedDecrement(&ref_);
    if (n == 0) delete this;
    return n;
  }
  STDMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) override {
    if (ppv == nullptr) return E_POINTER;
    *ppv = nullptr;
    if (outer != nullptr) return CLASS_E_NOAGGREGATION;
    Shim* shim = new Shim();
    HRESULT hr = shim->Create();
    if (SUCCEEDED(hr)) hr = shim->QueryInterface(riid, ppv);
    Log("CreateInstance: 0x%08lX", (unsigned long)hr);
    shim->Release();
    return hr;
  }
  STDMETHODIMP LockServer(BOOL lock) override {
    if (lock) {
      InterlockedIncrement(&g_locks);
    } else {
      InterlockedDecrement(&g_locks);
    }
    return S_OK;
  }

 private:
  LONG ref_ = 1;
};

}  // namespace

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** ppv) {
  if (ppv == nullptr) return E_POINTER;
  *ppv = nullptr;
  if (clsid != kLegacySource) return CLASS_E_CLASSNOTAVAILABLE;
  Factory* factory = new Factory();
  HRESULT hr = factory->QueryInterface(riid, ppv);
  factory->Release();
  return hr;
}

STDAPI DllCanUnloadNow() {
  return (g_objects == 0 && g_locks == 0) ? S_OK : S_FALSE;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(instance);
    Log("wmsource-shim loaded into pid %lu", (unsigned long)GetCurrentProcessId());
  }
  return TRUE;
}
