# Music on Windows 11

**Date:** 2026-08-27
**Result:** the soundtrack plays. `mtrevival fix --music` installs a small COM
shim for the current user and writes `SysSetup music 0`. Verified on one
machine, patch 1.2, by the shim's own trace inside `mc.exe` and by ear.

## What the game does

From the disassembly of the 1.2 executable (1.0 differs only in addresses):

```
Init  (0x4A8940)   CoCreateInstance(CLSID_FilterGraph, IID_IGraphBuilder)
                   QI IMediaControl, IMediaSeeking, IMediaEventEx, IBasicAudio
                   CoCreateInstance({6B6D0800-9ADA-11D0-A520-00A0D10129C0},
                                    CLSCTX_INPROC_SERVER, IID_IBaseFilter)   <- fails
                   graph->AddFilter(source, NULL)
                   source->QI(IFileSourceFilter)
Play  (0x4A8BC0)   source->Load(L"gamedata\sound\music\<track>.wma")
                   source->FindPin(L"Stream 1", &pin)
                   control->Stop()
                   for every filter: graph->RemoveFilter(f); graph->AddFilter(f)
                   graph->Render(pin)
                   seeking->SetPositions(0, AbsolutePositioning)
                   control->Run()
```

`{6B6D0800-…}` is the 2001 **Windows Media Source Filter** from `dxmasf.dll`.
Windows 11 still ships a `dxmasf.dll`, but it is a 5 KB stub and the class is
not registered, so `CoCreateInstance` returns `REGDB_E_CLASSNOTREG`. `Init`
checks that result and returns false; its caller ignores the false, and
`Play` dereferences the null `IFileSourceFilter` at `0x4A8BED` (1.0:
`0x4A800D`). That is crash 2 from `phase-0-findings.md`.

`SysSetup music N` is stored as a byte, and the game keeps
`music_enabled = (N == 0)` (`0x4A5D43`). So `music 1` is **off**, which is why
it avoided the crash, and `music 0` is on. `Init` runs during sound-manager
startup whenever the flag is set; every later track change goes through
`Play` on the **same** filter instance.

## What Windows still has

| Component | State on Windows 11 26200 |
|---|---|
| `dxmasf.dll` | present, 5 KB stub, exports `DllGetClassObject` that serves nothing; CLSID unregistered |
| WM ASF Reader `{187463A0-5BB7-11D3-ACBE-0080C75E246E}`, `qasf.dll` | registered, 32- and 64-bit |
| WMAudio Decoder DMO, `wmadmod.dll` | registered, 32- and 64-bit |
| `Media Type\Extensions\.wma` | absent (no extension → filter mapping) |

The reader is the supported replacement. Two probes (`tools/probe-wma-source.cpp`
and scratch harnesses replaying the call list above) established how it
differs from what the game expects:

1. **Pin name.** The reader's output pin is `Raw Audio 0`;
   `FindPin(L"Stream 1")` returns `VFW_E_NOT_FOUND`.
2. **One `Load` per instance.** A second `Load` on the same reader returns
   `E_FAIL` in every state tried: still running, stopped, stopped and
   disconnected, removed from the graph. A **fresh instance** per track works,
   including in the game's order (load the new one while the old one is still
   playing, then stop, remove, disconnect-all, render, run).
3. The reader supports COM aggregation.

All ten shipped tracks load and expose `Raw Audio 0` in the 32-bit probe:

```
music_30s music_40s music_50s music_60s music_70s music_80s music_90s
music_intro music_loser music_winner        Load=0x00000000  pin='Raw Audio 0'
```

## Why not patch the executable

The obvious fix is two same-size constant swaps in `mc.exe`: the CLSID (the
reader's CLSID is even already present in the binary, unused, at `0x5205FC`)
and the pin name (`L"Stream 1"` at `0x535C78` is followed by exactly six zero
bytes, so `L"Raw Audio 0\0"` fits in place). That was tried on paper and
rejected because of point 2 above: the intro track would play, and every
later `Load` would fail. The game checks that `HRESULT` and jumps past
`Stop`, so the previous track keeps playing forever. Making the game create
a new reader per track needs a code cave that rebuilds the whole graph per
track, with per-build offsets, and it resets the volume each time because
`IBasicAudio` lives on the graph. Not worth it.

## The shim

`tools/wmsource-shim/wmsource-shim.cpp` builds `wmsource-shim.dll`, an
in-process COM server for `{6B6D0800-…}` with no dependencies beyond
`ole32`. Its one class:

- **aggregates** a WM ASF Reader, so the reader's pins report a filter whose
  `IUnknown` is the shim — the identity the filter graph holds after
  `AddFilter`;
- on every `IFileSourceFilter::Load` creates a **fresh** aggregated reader,
  loads the file into it, and only then retires the old one (stops the graph
  through `IMediaControl`, disconnects the old pins through
  `IFilterGraph::Disconnect`, releases it). A failed `Load` leaves the old
  reader and the playing track untouched;
- answers `FindPin(L"Stream N")` with the current reader's N-th output pin
  after the reader's own lookup fails;
- forwards every other `IBaseFilter`, `IMediaFilter`, `IPersist` and
  `IFileSourceFilter` call to the current reader, and every other
  `QueryInterface` to the reader's non-delegating unknown.

Set `WMSOURCE_SHIM_LOG=<file>` in the game's environment to append a trace
(`CreateInstance`, `Load`, `FindPin` with `HRESULT`s); the same lines go to
`OutputDebugString`.

### Registration

`fix --music` copies the DLL next to `mc.exe` and registers it in the
**32-bit view of `HKCU\Software\Classes`** — the game is a 32-bit process,
and per-user registration needs no elevation and touches nothing outside the
profile:

```
HKCU\Software\Classes\WOW6432Node\CLSID\{6B6D0800-9ADA-11D0-A520-00A0D10129C0}
    (default)            Windows Media Source Filter (mtrevival wmsource-shim)
    InprocServer32
        (default)        C:\Program Files (x86)\Infogrames\Monopoly Tycoon\wmsource-shim.dll
        ThreadingModel   Both
```

Two preflight checks gate `--music`: the reader must be registered for
32-bit programs (Windows N editions need the Media Feature Pack), and the
shim must be bundled. Wheels from PyPI and the GitHub releases carry it; a
git checkout does not — run `tools\wmsource-shim\build.ps1` (MSVC Build
Tools, x86) or drop the DLL from a release into `src\mtrevival\bin\`. `fix --music` warns if `mc.exe` has
the "run as administrator" compatibility flag: an elevated process ignores
per-user COM classes, would not see the shim, and would crash with `music 0`.

To remove it, unhook the class, write `music 1` again with whatever
resolution flags you use, and delete the copied DLL:

```
py -c "from mtrevival import music; print(music.unregister())"
py -m mtrevival fix --resolution 1920x1080      # your usual flags, minus --music
del "C:\Program Files (x86)\Infogrames\Monopoly Tycoon\wmsource-shim.dll"
```

`fix --music` also warns when the shell itself is elevated: the registration
lands in the HKCU of the account running the command, and the game must run
as that same account, unelevated.

## Verification record

Harness replaying the game's exact call list through the registered CLSID
(`probe4`, x86): four consecutive track changes, every call `S_OK`, pin
owner identity `==` the shim, `IBasicAudio` volume persisted across tracks,
a `Load` of a missing file returned `0x80070003` and left the current track
playing, all references released at teardown.

In the game (1280x720 windowed, `music 0`, trace enabled):

```
wmsource-shim loaded into pid 229392
CreateInstance: 0x00000000
Load(gamedata\sound\music\music_intro.wma): 0x00000000
FindPin(Stream 1) -> output pin 1: 0x00000000
```

and the intro music was audible. Track changes during play were verified in
the harness, not yet by ear across a long session.

Verified config, byte for byte (`tests/test_gameconfig.py::VERIFIED_MUSIC`):

```
SysSetup api D3D
SysSetup device 1
SysSetup width 1280
SysSetup height 720
SysSetup bitdepth 32
SysSetup texbitdepth 16
SysSetup music 0
SysSetup Window 1
```

## Side finding: `MTS.txt`

Patch 1.2 creates an empty `MTS.txt` in the game folder the moment `mc.exe`
starts and deletes it on a clean exit. A killed process leaves it behind, and
the next launch offers Safe Mode, which overwrites `config.cfg`. Delete the
file after any forced stop. `patch-1.2.md` has the details.
