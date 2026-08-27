# Phase 0 Findings

**Date:** 2026-08-27
**Status:** COMPLETE. The game runs on Windows 11. Gate is open.

## Result

The game reaches the main menu and plays. It was closed normally, and the
Windows Application log records **no crash after the fix was applied**. It also
wrote a player profile and its own configuration, which only happens on a
successful run.

Two independent bugs had to be fixed. Both are the same defect class: the game
creates a COM or Direct3D object, never checks the return value, and
dereferences null.

| # | Fault | Cause | Fix |
|---|---|---|---|
| 1 | `mc.exe+0xE792E`, `IDirect3DDevice8::SetViewport` | `CreateDevice` failed. The game asked for 640x480 **exclusive fullscreen** on adapter 0, which is a portrait monitor offering `480 X 640` and no `640 X 480`. | `SysSetup device 1` |
| 2 | `mc.exe+0xA801B`, opening `gamedata\sound\music\music_intro.wma` | The Windows Media DirectShow source filter (`dxmasf.dll`) no longer exists on Windows 11, so the media object came back null. | `SysSetup music 1` |

Bug 2 was diagnosed by Codex and independently confirmed here from the crash
dump: the recovered filename is `gamedata\sound\music\music_intro.wma`, both
interface pointers at `ebx+0x2CE4` and `ebx+0x2CE8` are null, and the loaded
module list contains `quartz.dll` and `devenum.dll` but no `dxmasf.dll` or
`wmvcore.dll`.

A third fix was needed before either could be applied: the install directory
must be writable by the user (see below), otherwise `config.cfg` cannot exist.

## The working configuration

`C:\Program Files (x86)\Infogrames\Monopoly Tycoon\config.cfg`:

```
SysSetup api D3D
SysSetup device 1
SysSetup width 640
SysSetup height 480
SysSetup bitdepth 32
SysSetup texbitdepth 16
SysSetup music 1
```

`device 1` is machine-specific. It means "the second enumerated adapter", which
on this machine is the landscape display. Any `fixpack` must pick the adapter by
capability — an adapter whose mode list contains the requested resolution — not
by a hardcoded index.

## Files the successful run created

- `profiles\Nasser\settings.lua` — **the game saves in Lua.**

  ```lua
  g_ProfileOptions.BoardName = "gb"
  g_ProfileOptions.DetailLevel = 2
  g_ProfileOptions.LightingLevel = 2
  SetLevelInfo(100000, DEPRECATED, 0, 0, 0, 0)
  ```

  `BoardName` selects among the 19 national boards shipped on the CD.

- `profiles\memory.lua` — one line, `ProfileName = "Nasser"`.
- `max\archive.DIR` was **rewritten**: same size (463,880 bytes), different MD5
  from the CD copy. The `Regenerating archive file` path ran. The pristine CD
  copy is intact for comparison.

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

~~No registry entries exist.~~ **Correction (later the same day):** the installer
did create `HKLM\SOFTWARE\WOW6432Node\Infogrames\Monopoly Tycoon\1.00.000`,
`...\Infogrames Interactive\MONOPOLY TYCOON` (`PATH`, `LANGUAGE`, `DEFAULTBOARD`)
and the Uninstall key. The original query was malformed. Patch 1.2 applies
without prompting — see `patch-1.2.md`.

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

**Confirmed** by the crash dump. The `D3DPRESENT_PARAMETERS` struct recovered
from the faulting process:

| Offset | Field | Value |
|---|---|---|
| 0x00 | BackBufferWidth | 640 |
| 0x04 | BackBufferHeight | 480 |
| 0x08 | BackBufferFormat | 22 = `D3DFMT_X8R8G8B8` |
| 0x1C | Windowed | 0 — exclusive fullscreen |
| 0x24 | AutoDepthStencilFormat | 80 = `D3DFMT_D16` |
| 0x5C | returned device | NULL |

The faulting instruction is `mov ecx,[eax]` with `EAX = 0`, followed by
`call [ecx+0xA0]` — vtable slot 40 of `IDirect3DDevice8`, which is `SetViewport`.
The call immediately before it is `call [edx+0x3C]`, slot 15, `CreateDevice`,
whose HRESULT is never tested.

Fixed by `SysSetup device 1`.

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

**`device` is an adapter index**, and the file syntax is now **confirmed**: one
`SysSetup <key> <value>` per line, CRLF. The game reads it during renderer
initialisation — `device 1` changed which adapter `CreateDevice` targeted and
moved the crash past `SetViewport`.

Two caveats found the hard way:

- `windowed 1` and `bitdepth 16` were both **ignored** in an earlier test, while
  `device` and `bitdepth 32` took effect. Not every key is honoured on every
  path, so never assume a `SysSetup` key works without observing it.
- An earlier version of this document concluded `config.cfg` was not read at
  device-creation time, reasoning from those two ignored keys. **That conclusion
  was wrong.** `device 1` disproved it.

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

## System changes made to get here

Both are deliberate and should be reproduced by `fixpack`. Neither is a hack.

1. **Write access to the install directory.** Program Files grants standard users
   read-and-execute only, so the game could not write `config.cfg`, its profile,
   or savegames. Granted once, elevated:

   ```powershell
   icacls "C:\Program Files (x86)\Infogrames\Monopoly Tycoon" /grant "$($env:USERNAME):(OI)(CI)M" /T
   ```

2. **WER LocalDumps for `mc.exe`**, so crashes produce a full dump. This was a
   debugging aid, not part of the fix, and can be removed with
   `Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\mc.exe"`.
   Dumps land in `D:\personal\reviving-games\crashdumps` (gitignored).

## Open items

- `SysSetup music 1` currently disables the WMA path. Confirm the flag's
  semantics, and find a way to restore music without the bundled 2001 Windows
  Media installer.
- Diff the rewritten `max\archive.DIR` against the CD copy to see what the
  regeneration path changed.
- ~~Test whether `MTPatch1_2.exe` applies.~~ Done: it applies and the game runs.
  See `patch-1.2.md`.
- Examine `RoadNodes.bin` and `route_smalltable.bin` against the map scripts.
- Decide how `fixpack` picks the adapter by capability rather than index.

## Corrections to the design spec

1. `mtarc` and the cab reader are **not** on the critical path. The scripts are
   loose on disk.
2. The claim that InstallShield fails on 64-bit Windows was wrong on this machine.
3. The resolution ceiling is not 800x600 or 1024x768. The game enumerates every
   mode the adapter reports, up to 3840x2160.
4. `parameters\*.prm` is a moddable data source the spec does not mention.
