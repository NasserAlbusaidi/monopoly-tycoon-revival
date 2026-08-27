#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <dshow.h>
#include <stdio.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "strmiids.lib")

namespace {

const CLSID kLegacyWindowsMediaSource = {
    0x6b6d0800,
    0x9ada,
    0x11d0,
    {0xa5, 0x20, 0x00, 0xa0, 0xd1, 0x01, 0x29, 0xc0},
};

const CLSID kWmAsfReader = {
    0x187463a0,
    0x5bb7,
    0x11d3,
    {0xac, 0xbe, 0x00, 0x80, 0xc7, 0x5e, 0x24, 0x6e},
};

void PrintResult(const wchar_t* operation, HRESULT result) {
  wprintf(L"%-32ls 0x%08lX\n", operation,
          static_cast<unsigned long>(result));
}

void ReleasePinInfo(PIN_INFO* info) {
  if (info->pFilter != nullptr) {
    info->pFilter->Release();
    info->pFilter = nullptr;
  }
}

int Probe(const CLSID& source_clsid, const wchar_t* source_name,
          const wchar_t* media_path) {
  wprintf(L"\n[%ls]\n", source_name);

  IGraphBuilder* graph = nullptr;
  HRESULT result = CoCreateInstance(
      CLSID_FilterGraph, nullptr, CLSCTX_INPROC_SERVER, IID_IGraphBuilder,
      reinterpret_cast<void**>(&graph));
  PrintResult(L"CoCreateInstance(IGraphBuilder)", result);
  if (FAILED(result)) {
    return 1;
  }

  IBaseFilter* source = nullptr;
  result = CoCreateInstance(source_clsid, nullptr, CLSCTX_INPROC_SERVER,
                            IID_IBaseFilter,
                            reinterpret_cast<void**>(&source));
  PrintResult(L"CoCreateInstance(IBaseFilter)", result);
  if (FAILED(result)) {
    graph->Release();
    return 1;
  }

  result = graph->AddFilter(source, source_name);
  PrintResult(L"IGraphBuilder::AddFilter", result);
  if (FAILED(result)) {
    source->Release();
    graph->Release();
    return 1;
  }

  IFileSourceFilter* file_source = nullptr;
  result = source->QueryInterface(IID_IFileSourceFilter,
                                  reinterpret_cast<void**>(&file_source));
  PrintResult(L"QueryInterface(IFileSourceFilter)", result);
  if (FAILED(result)) {
    source->Release();
    graph->Release();
    return 1;
  }

  result = file_source->Load(media_path, nullptr);
  PrintResult(L"IFileSourceFilter::Load", result);

  IEnumPins* pins = nullptr;
  HRESULT enum_result = source->EnumPins(&pins);
  PrintResult(L"IBaseFilter::EnumPins", enum_result);
  if (SUCCEEDED(enum_result)) {
    IPin* pin = nullptr;
    while (pins->Next(1, &pin, nullptr) == S_OK) {
      LPWSTR id = nullptr;
      PIN_INFO info = {};
      HRESULT id_result = pin->QueryId(&id);
      HRESULT info_result = pin->QueryPinInfo(&info);
      wprintf(L"  pin id=%ls name=%ls direction=%ls\n",
              SUCCEEDED(id_result) && id != nullptr ? id : L"<unavailable>",
              SUCCEEDED(info_result) ? info.achName : L"<unavailable>",
              SUCCEEDED(info_result) && info.dir == PINDIR_OUTPUT ? L"output"
                                                                  : L"input");
      if (id != nullptr) {
        CoTaskMemFree(id);
      }
      ReleasePinInfo(&info);
      pin->Release();
    }
    pins->Release();
  }

  IPin* stream_one = nullptr;
  HRESULT find_result = source->FindPin(L"Stream 1", &stream_one);
  PrintResult(L"IBaseFilter::FindPin(Stream 1)", find_result);
  if (stream_one != nullptr) {
    stream_one->Release();
  }

  file_source->Release();
  source->Release();
  graph->Release();
  return SUCCEEDED(result) && SUCCEEDED(find_result) ? 0 : 1;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) {
    fwprintf(stderr, L"Usage: probe-wma-source.exe <path-to-wma>\n");
    return 2;
  }

  HRESULT init_result = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  PrintResult(L"CoInitializeEx", init_result);
  if (FAILED(init_result)) {
    return 1;
  }

  const int legacy_result = Probe(kLegacyWindowsMediaSource,
                                  L"Legacy Windows Media Source", argv[1]);
  const int modern_result =
      Probe(kWmAsfReader, L"WM ASF Reader", argv[1]);

  CoUninitialize();
  return legacy_result == 0 || modern_result == 0 ? 0 : 1;
}
