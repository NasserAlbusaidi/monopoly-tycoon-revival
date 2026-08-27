# Phase 0 Findings

**Date:** 2026-08-27
**Status:** In progress. Root cause identified, not yet confirmed by test.

Every statement below is an observation with its evidence named. Anything not
yet observed says so.

## Install

The stock InstallShield installer **works on Windows 11**. No workaround needed.

- Install location: `C:\Program Files (x86)\Infogrames\Monopoly Tycoon`
- 438 files.
- The plan's premise that `ikernel.exe` fails on 64-bit Windows did not hold on
  this machine. That claim came from general knowledge, not observation, and was
  wrong here.

**Patch 1.2 is not applied.** `mc.exe` is dated Oct 10 2001 at 1,495,082 bytes,
byte-identical in size to the CD copy. The patch is dated Dec 18 2001.

**No registry entries exist** under `HKLM\SOFTWARE\WOW6432Node\Infogrames` or
`HKCU\Software\Infogrames`. If `MTPatch1_2.exe` locates the install through the
registry, it may refuse to run. Not yet tested.

## Gate question 1: are the .lua files loose on disk?

**Yes.** 200 `.lua` files under `scripts\`, in 56 namespace directories, plain
text, carrying their original 2001 timestamps.

```
scripts\DEFAULT\ai.lua                47,316   2001-08-29
scripts\DEFAULT\businesssettings.lua  37,188   2001-08-22
scripts\DEFAULT\blocksettings.lua     13,365   2001-05-01
scripts\DEFAULT\default.lua           57,480   2001-05-14
scripts\DEFAULT\buildingsettings.lua       0   2001-02-28  (empty, as on the CD)
```

**Consequence: the modding path is "edit a text file in the install directory".**
No archive tooling is required. `mtarc` and the cab reader drop off the critical
path entirely.

## Gate question 2: did patch 1.2 change the scripts?

Not applicable yet — the patch is not applied. The on-disk scripts carry CD
timestamps.

## Gate question 3: road binaries

Both exist: `gamedata\RoadNodes.bin` and `gamedata\route_smalltable.bin`.
Their relationship to the `MAPS\*.lua` scripts is not yet examined.

## Additional moddable data not in the design spec

- `parameters\` — 34 `.prm` files, one set per decade: `1930.prm` … `1990.prm`.
- 10 `.tab`, 22 `.off`, 25 `.bin` files under the install tree.

## The crash

**Symptom:** the game starts, opens its renderer, and dies.

`D3DLOG.txt` (written by the game, 2026-08-27 14:12):

```
***** Open Renderer
* MODE - 640X480X16
```

Windows Application event log, two crashes seven seconds apart:

| Time | Exception | Fault offset | Faulting module |
|---|---|---|---|
| 14:12:19 | `c0000005` (access violation) | `0x000e792e` | `mc.exe` |
| 14:12:26 | `c000041d` (fatal exception in callback) | `0x000e792e` | `mc.exe` |

The faulting module is the game's own code, not a driver. The offset is
identical across both crashes, so the fault is deterministic.

### Root cause

The primary display is a **portrait monitor**:

```
\\.\DISPLAY1   Primary=False   5120 x 1440   (landscape ultrawide)
\\.\DISPLAY2   Primary=True    1440 x 2560   (portrait)
```

`D3DEnum.txt`, written by the game, shows it enumerated two adapters. Adapter #0
lists only portrait modes — `480 X 640`, `600 X 800`, `768 X 1024` — and
**contains no `640 X 480` mode**. Adapter #1 lists landscape modes including
`640 X 480`.

The chain, each link observed:

1. The game defaults to adapter #0, the portrait primary.
2. It requests 640x480x16, which that adapter does not offer.
3. Device creation fails. The game does not check the return value.
4. It dereferences the failed device, raising an access violation.

This is not a Windows 11 problem and not a DirectX 8 problem. The same crash
would occur on Windows XP with a portrait primary monitor.

**Status: identified, not yet confirmed.** The discriminating test is to make the
landscape display primary and relaunch.

## Why the game had no configuration

The exe references `config.cfg` and the string
`Unable to gain write access to config.cfg`. No `config.cfg` exists — not in the
install directory, not in `%LOCALAPPDATA%\VirtualStore`.

The game **crashed before it ever wrote one**, so every run starts from built-in
defaults: adapter 0, 640x480, 16-bit. That is exactly what `D3DLOG.txt` records.

Writes to the install directory do succeed — `D3DEnum.txt` and `D3DLOG.txt` were
both written there today.

## The SysSetup configuration interface

`config.cfg` is driven by a `SYSSETUP` command. The exe carries these format
strings:

```
SysSetup api D3D | Software | Test
SysSetup device %d          SysSetup windowed %d
SysSetup width %d           SysSetup height %d
SysSetup bitdepth %d        SysSetup texbitdepth %d
SysSetup Texdetail %d       SysSetup avail %d
SysSetup sound %s           SysSetup music %d
SysSetup shware %d
```

`SYSSETUP` appears inside a table of all-caps command tokens alongside
`SAVEGAME`, `LOADGAME`, `DEBUGFLAG`, `TIMETABLE`, `BUILDINGCOSTPERUNIT`,
`CLASSWEIGHTING`, `BLOCKCLASSSCORE` — the commands the Lua scripts call.

**`device` is an adapter index.** If the config format can be authored, the fix
becomes a config file rather than a change to the user's desktop layout. The
exact file syntax is **not yet known** — the format above is inferred from
printf-style strings, not from a real `config.cfg`.

## Debug and developer features found in the shipped exe

Not yet tested, recorded for the modding phase.

Debug flags, reachable through a `DEBUGFLAG` command:

```
TIMEDLOGIC  SIMPLEBUILDINGS  CHEATINGGIT  DEBUGTEXT  AIDEBUG
TAXICAMERA  PEOPLEDEBUG  PEOPLERAILS  SHOWALLCARS  SHOWDOORPOS  TRAFFICRAILS
```

Editor remnants:

- `Tycoon Block Editor Window` — a registered window class.
- `Failed to register window class (for building editor).`
- Original build paths: `C:\projects\Tycoon\CODE\panels\panels.cpp`,
  `C:\projects\Tycoon\CODE\PANELS\widgets.cpp`.
- A developer's network path: `\\LEE-TARGET\TYCOON_DATA\max\BuildEditorModels\BuildFile.dat`.

## Open items

- Confirm the root cause by making the landscape display primary and relaunching.
- Determine the real `config.cfg` syntax.
- Test whether `MTPatch1_2.exe` applies without registry entries.
- Read the minidumps at
  `C:\ProgramData\Microsoft\Windows\WER\ReportArchive\AppCrash_mc.exe_*`.
  They need an elevated shell; a non-elevated `icacls` grant did not take effect.
- Examine `RoadNodes.bin` and `route_smalltable.bin` against the map scripts.

## Corrections to the design spec

1. `mtarc` and the cab reader are **not** on the critical path. The scripts are
   loose on disk.
2. The claim that InstallShield fails on 64-bit Windows was wrong on this machine.
3. The resolution ceiling is not 800x600 or 1024x768. The game enumerates every
   mode the adapter reports, up to 3840x2160.
4. `parameters\*.prm` is a moddable data source the spec does not mention.
