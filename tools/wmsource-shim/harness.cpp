// harness: replays mc.exe's music call sequence against whatever answers the
// legacy Windows Media Source Filter CLSID, and fails on any deviation from
// what the game needs. CI runs it against the freshly built wmsource-shim.dll
// with two synthesised tone files (no game content).
//
//   harness [--null-renderer] first.wma second.wma
//
// --null-renderer connects the source to a Null Renderer instead of calling
// IGraphBuilder::Render, for machines with no audio device (CI runners). The
// shim behaviour under test — a fresh reader per Load, FindPin(L"Stream 1"),
// COM identity, volume kept across tracks — is the same either way.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dshow.h>
#include <stdio.h>
#include <string.h>
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "strmiids.lib")
#pragma comment(lib, "user32.lib")

namespace {

const CLSID kLegacy = {0x6b6d0800, 0x9ada, 0x11d0, {0xa5, 0x20, 0x00, 0xa0, 0xd1, 0x01, 0x29, 0xc0}};
// Null Renderer (qedit.dll); its header left the SDK, the filter did not.
const CLSID kNullRenderer = {0xc1f400a4, 0x3f08, 0x11d3, {0x9f, 0x0b, 0x00, 0x60, 0x08, 0x03, 0x9e, 0x37}};

int g_failures = 0;

void Report(const char* what, bool ok, HRESULT hr) {
  printf("%-46s %s (0x%08lX)\n", what, ok ? "ok" : "FAIL", (unsigned long)hr);
  if (!ok) g_failures++;
}
#define CHECK_HR(what, expr) do { HRESULT hr_ = (expr); Report(what, SUCCEEDED(hr_), hr_); } while (0)
#define CHECK(what, cond) Report(what, (cond), (cond) ? S_OK : E_FAIL)

struct Graph {
  IGraphBuilder* builder = nullptr;
  IMediaControl* control = nullptr;
  IMediaSeeking* seeking = nullptr;
  IMediaEventEx* events = nullptr;
  IBasicAudio* audio = nullptr;
  IBaseFilter* source = nullptr;
  IFileSourceFilter* file = nullptr;
  IBaseFilter* null_renderer = nullptr;
};

// The game's way of tearing down connections: remove and re-add every filter.
void DisconnectAll(IGraphBuilder* g) {
  IEnumFilters* e = nullptr;
  if (FAILED(g->EnumFilters(&e))) return;
  IBaseFilter* list[32];
  int n = 0;
  IBaseFilter* f = nullptr;
  while (n < 32 && e->Next(1, &f, nullptr) == S_OK) list[n++] = f;
  e->Release();
  for (int i = 0; i < n; i++) {
    g->RemoveFilter(list[i]);
    g->AddFilter(list[i], nullptr);
    list[i]->Release();
  }
}

IPin* FirstPin(IBaseFilter* f, PIN_DIRECTION want) {
  IEnumPins* e = nullptr;
  if (FAILED(f->EnumPins(&e))) return nullptr;
  IPin* p = nullptr;
  IPin* found = nullptr;
  while (found == nullptr && e->Next(1, &p, nullptr) == S_OK) {
    PIN_DIRECTION dir;
    if (SUCCEEDED(p->QueryDirection(&dir)) && dir == want) found = p; else p->Release();
  }
  e->Release();
  return found;
}

bool SameObject(IUnknown* a, IUnknown* b) {
  IUnknown* ia = nullptr;
  IUnknown* ib = nullptr;
  a->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(&ia));
  b->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(&ib));
  bool same = ia == ib;
  if (ia) ia->Release();
  if (ib) ib->Release();
  return same;
}

// One track change exactly as mc.exe does it (see docs/music.md).
void Play(Graph& g, const wchar_t* path, bool null_renderer) {
  printf("\n== %ls\n", path);
  CHECK_HR("Load", g.file->Load(path, nullptr));
  IPin* pin = nullptr;
  CHECK_HR("FindPin(Stream 1)", g.source->FindPin(L"Stream 1", &pin));
  if (pin == nullptr) return;
  PIN_INFO info = {};
  pin->QueryPinInfo(&info);
  CHECK("pin is an output pin", info.dir == PINDIR_OUTPUT);
  CHECK("pin's filter has the shim's COM identity", info.pFilter && SameObject(info.pFilter, g.source));
  if (info.pFilter) info.pFilter->Release();
  CHECK_HR("Stop", g.control->Stop());
  DisconnectAll(g.builder);
  if (null_renderer) {
    IPin* in = FirstPin(g.null_renderer, PINDIR_INPUT);
    CHECK("null renderer input pin", in != nullptr);
    if (in) { CHECK_HR("Connect(pin, null renderer)", g.builder->Connect(pin, in)); in->Release(); }
  } else {
    CHECK_HR("Render", g.builder->Render(pin));
  }
  pin->Release();
  LONGLONG zero = 0;
  CHECK_HR("SetPositions(0)", g.seeking->SetPositions(&zero, AM_SEEKING_AbsolutePositioning, nullptr, AM_SEEKING_NoPositioning));
  CHECK_HR("Run", g.control->Run());
  Sleep(1200);
  LONGLONG pos = 0;
  g.seeking->GetCurrentPosition(&pos);
  printf("  position after 1.2 s: %.2f s\n", pos / 1e7);
  CHECK("playback advances", pos > 5000000);  // > 0.5 s
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  bool null_renderer = false;
  const wchar_t* files[2] = {nullptr, nullptr};
  int nfiles = 0;
  for (int i = 1; i < argc; i++) {
    if (wcscmp(argv[i], L"--null-renderer") == 0) null_renderer = true;
    else if (nfiles < 2) files[nfiles++] = argv[i];
  }
  if (nfiles != 2) {
    fwprintf(stderr, L"usage: harness [--null-renderer] first.wma second.wma\n");
    return 2;
  }
  CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  Graph g;
  CHECK_HR("FilterGraph", CoCreateInstance(CLSID_FilterGraph, nullptr, CLSCTX_INPROC_SERVER, IID_IGraphBuilder, reinterpret_cast<void**>(&g.builder)));
  if (g.builder == nullptr) return 1;
  CHECK_HR("QI IMediaControl", g.builder->QueryInterface(IID_IMediaControl, reinterpret_cast<void**>(&g.control)));
  CHECK_HR("QI IMediaSeeking", g.builder->QueryInterface(IID_IMediaSeeking, reinterpret_cast<void**>(&g.seeking)));
  CHECK_HR("QI IMediaEventEx", g.builder->QueryInterface(IID_IMediaEventEx, reinterpret_cast<void**>(&g.events)));
  CHECK_HR("QI IBasicAudio", g.builder->QueryInterface(IID_IBasicAudio, reinterpret_cast<void**>(&g.audio)));
  CHECK_HR("CoCreateInstance(legacy CLSID, IID_IBaseFilter)", CoCreateInstance(kLegacy, nullptr, CLSCTX_INPROC_SERVER, IID_IBaseFilter, reinterpret_cast<void**>(&g.source)));
  if (g.source == nullptr) {
    printf("nothing answers the legacy CLSID; is wmsource-shim.dll registered for this user?\n");
    return 1;
  }
  CHECK_HR("AddFilter", g.builder->AddFilter(g.source, nullptr));
  CHECK_HR("QI IFileSourceFilter", g.source->QueryInterface(IID_IFileSourceFilter, reinterpret_cast<void**>(&g.file)));
  if (null_renderer) {
    CHECK_HR("Null Renderer", CoCreateInstance(kNullRenderer, nullptr, CLSCTX_INPROC_SERVER, IID_IBaseFilter, reinterpret_cast<void**>(&g.null_renderer)));
    if (g.null_renderer) g.builder->AddFilter(g.null_renderer, L"Null Renderer");
  }
  HWND hwnd = CreateWindowExW(0, L"STATIC", L"harness", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr, nullptr, nullptr);
  CHECK_HR("SetNotifyWindow", g.events->SetNotifyWindow(reinterpret_cast<OAHWND>(hwnd), WM_APP + 1, 0));

  Play(g, files[0], null_renderer);
  // IBasicAudio is implemented by the audio renderer; without one it is
  // E_NOTIMPL, so the volume checks only run in the default mode.
  if (!null_renderer) CHECK_HR("put_Volume(-1500)", g.audio->put_Volume(-1500));
  Play(g, files[1], null_renderer);
  if (!null_renderer) {
    long volume = 0;
    g.audio->get_Volume(&volume);
    CHECK("volume kept across the track change", volume == -1500);
  } else {
    printf("  (volume checks need an audio renderer; skipped)\n");
  }
  Play(g, files[0], null_renderer);

  printf("\n== Load of a missing file must fail and leave the track playing\n");
  HRESULT bad = g.file->Load(L"C:\\does\\not\\exist.wma", nullptr);
  CHECK("Load(missing) fails", FAILED(bad));
  LONGLONG before = 0, after = 0;
  g.seeking->GetCurrentPosition(&before);
  Sleep(600);
  g.seeking->GetCurrentPosition(&after);
  CHECK("previous track still advancing", after > before);

  printf("\n== teardown\n");
  CHECK_HR("Stop", g.control->Stop());
  g.file->Release();
  g.audio->Release();
  g.events->Release();
  g.seeking->Release();
  g.control->Release();
  if (g.null_renderer) g.null_renderer->Release();
  g.source->Release();
  ULONG left = g.builder->Release();
  CHECK("graph fully released", left == 0);
  DestroyWindow(hwnd);
  CoUninitialize();
  printf("\n%d failure(s)\n", g_failures);
  return g_failures == 0 ? 0 : 1;
}
