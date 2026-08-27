# Patch 1.2 on Windows 11

**Date:** 2026-08-27
**Result:** applies cleanly, and the patched game runs with the same
`config.cfg` as 1.0. Verified on one machine.

## What the patch is

`Extras\Patch\MTPatch1_2.exe` (3,072,936 bytes, Dec 2001) is an InstallShield
self-extractor. It unpacks to `%TEMP%\pft*.tmp` and runs this chain, recorded
with a process monitor:

```
MTPatch1_2.exe
└─ MTPatchInstall.exe            front-end; reads LANGUAGE from the registry
   └─ Setup.exe -l0x0009         InstallShield 6 stub (0x0009 = English)
      └─ IKernel.exe -Embedding  the engine the game installed (6.30)
```

The installer locates the game through
`HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{B975F4A1-63B6-11D4-BFEC-005004AF2D32}`
(`UninstallString`), with a browse-for-folder fallback. It never asked for a
folder here. It checks the `Monopoly Tycoon mutex` first and refuses with
`PATCH_ERROR` if the game is running.

## What it changes

Static diff of the payload against a 1.0 install, then confirmed by hashing all
461 files after the run:

| | Files |
|---|---|
| Changed (6) | `mc.exe` (1,495,082 → 1,511,466 bytes), `language\gb\tycoon.bin`, `language\gb\tycoon.off`, `scripts\DEFAULT\hub.lua`, `scripts\GAMESTART\hub.lua`, `scripts\SCENARIO1\initialpref.lua` |
| New (19) | `patchreadme.wri`, `scripts\sandbox\{hub,players}.lua`, `language\{dan,f,fin,ger,hol,nor,spa,swe}\tycoon.{bin,off}` |
| Removed | none |
| Untouched | `config.cfg`, profiles, `gamedata\`, `parameters\`, every other script |

Lua changes are small: `DEFAULT\hub.lua` adds `Tweaks.railutilincome*` and
`Tweaks.dailyfreight*` values; `GAMESTART\hub.lua` registers the new
`sandbox` level (`Frontend.RegisterLevel_Id(400002, "sandbox", ...)`);
`SCENARIO1\initialpref.lua` is whitespace only.

## The 1.2 executable

Both unchecked-null bugs are still present, at moved offsets:

| Bug | 1.0 | 1.2 |
|---|---|---|
| `CreateDevice` result unchecked | `0x0E78FE` | `0x0E8ECB` |
| media interface load before null check | `0x0A800D` | `0x0A8BED` |

So `SysSetup device` remains required, and music still needs either
`SysSetup music 1` (off) or the shim from `music.md`. `config.cfg` is still
read the same way.

`SysSetup` keys in 1.2 (from the exe's format strings):

```
api device width height bitdepth texbitdepth Texdetail avail sound music shware
Window Fog Halos Multitexture No3d NoMovie          <- new in 1.2
```

**`windowed` is renamed `Window`.** The 1.0 key `windowed` was observed being
ignored. On 1.2, `Window 1` was verified: the game ran in a desktop window at
640×480 and at 1280×720. `width`/`height` were verified too: 1920×1080
exclusive fullscreen on adapter 1 ran with a correctly laid-out UI. In every
case the game left `config.cfg` untouched, so what you write is what runs.

Three files ran on 1.2, byte for byte (`tests/test_gameconfig.py` pins them):

```
640x480 fullscreen        1920x1080 fullscreen      1280x720 windowed
SysSetup api D3D          SysSetup api D3D          SysSetup api D3D
SysSetup device 1         SysSetup device 1         SysSetup device 1
SysSetup width 640        SysSetup width 1920       SysSetup width 1280
SysSetup height 480       SysSetup height 1080      SysSetup height 720
SysSetup bitdepth 32      SysSetup bitdepth 32      SysSetup bitdepth 32
SysSetup texbitdepth 16   SysSetup texbitdepth 16   SysSetup texbitdepth 16
SysSetup music 1          SysSetup music 1          SysSetup music 1
                          SysSetup Window 0         SysSetup Window 1
```

The fixpack writes the middle shape *without* `Window 0` — omitting the key is
verified fullscreen by the first file, the resolution by the second. The exact
seven-line 1080p file was not itself run. The 1080p file with `Window 0` is
what the dev machine keeps.

Other 1.2 additions, from `patchreadme.wri` and the exe strings:

- **Safe Mode.** Triggered by a file named `MTS.txt` in the game folder, or
  offered after a crash. Overwrites `config.cfg` with lowest settings.
  Observed: the game itself creates an empty `MTS.txt` the moment it starts
  and removes it on a clean exit. A process that is killed leaves it behind,
  and the next launch will then offer Safe Mode. Delete the file before
  launching again if you do not want that.
- **Crash handler.** Writes `__crash.sav` and prompts for Safe Mode on the next
  launch.
- Command-line switches dropped from 1.0: `NOMOVIE`, `WINDOW` (now `SysSetup`
  keys). Kept: `L <lang>`, `DEBUGSTUFF`, `NOEXCEPTIONHANDLING`, `HOST`, `PORT`,
  `JOIN`, `SESSIONNAME`, `MAXPLAYERS`. Unknown switches are ignored silently.
- `Alt+F5` screenshot to `tycoonNNNNN.tga`; `Alt+F` free camera.

## Running the patcher

Run it **elevated**. The first attempt here was launched without elevation and
produced a series of error dialogs (paraphrased by the user as "unknown command
l") and changed nothing on disk. The second attempt, launched from an elevated
shell with a process monitor attached, completed with no dialog. The dialog
text was not captured, and no binary in the chain contains matching strings
(the game's own `Error. Unrecognised command %s` goes only to its in-game
console), so the cause is recorded as unexplained; elevation is the only known
difference.

`tools\monitor-run.ps1` is the monitor used: it launches an executable and
logs every new process command line and every visible dialog's text until the
process tree exits.

## Corrections to earlier findings

- `phase-0-findings.md` said no registry entries exist for the game. Wrong.
  The 1.0 installer created `Infogrames\Monopoly Tycoon\1.00.000`,
  `Infogrames Interactive\MONOPOLY TYCOON` (`PATH`, `LANGUAGE`, `DEFAULTBOARD`,
  `SETUP`, `UNINSTALLPATH`) and the Uninstall key, all under `WOW6432Node`.
- The earlier query that produced that claim used a key path containing a
  space without quoting; `reg` reports a syntax error, not "not found".
