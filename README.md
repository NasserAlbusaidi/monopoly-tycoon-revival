# Monopoly Tycoon Revival

Make **Monopoly Tycoon** (2001, Deep Red Games / Infogrames) install and run on
Windows 10 and 11.

The game installs fine on modern Windows and then crashes on startup — usually
right after the studio logo, sometimes before anything appears. There are two
separate causes, both fixable in about a minute. No patched executable, no
wrapper DLL, no compatibility mode required.

**This repository contains no game content.** You need your own copy of the game.

---

## Quick fix, by hand

### 1. Let the game write to its own folder

The game stores settings, profiles and savegames next to `mc.exe`. Under
`C:\Program Files (x86)` a standard user account cannot write there, so the game
silently fails to save anything — including the settings that fix the crash.

Run once in an **elevated** PowerShell:

```powershell
icacls "C:\Program Files (x86)\Infogrames\Monopoly Tycoon" /grant "$($env:USERNAME):(OI)(CI)M" /T
```

### 2. Create `config.cfg`

In the game folder, create a file named `config.cfg`:

```
SysSetup api D3D
SysSetup device 1
SysSetup width 640
SysSetup height 480
SysSetup bitdepth 32
SysSetup texbitdepth 16
SysSetup music 1
```

**`device` is the display adapter index and is specific to your machine.** Use
`0` if your primary display is a normal landscape monitor. Use `1` (or higher)
if your primary display is rotated to portrait, or does not offer a 640×480
mode. The tool below works this out for you.

That is the whole fix. Launch `mc.exe`.

---

## Working it out automatically

Requires Python 3.12 or newer. Standard library only.

```
py -m pip install .
py -m mtrevival adapters     # list adapters, show which support 640x480
py -m mtrevival check        # show what would be written, change nothing
py -m mtrevival fix          # write config.cfg, backing up any existing one
```

Example on a machine with a portrait primary display:

```
source: D3DEnum.txt
  adapter 0  NVIDIA GeForce RTX 4080   modes=46   no 640x480  [portrait]
  adapter 1  NVIDIA GeForce RTX 4080   modes=54   OK 640x480
```

`fix` never overwrites an existing `config.cfg` without copying it to a
timestamped `.bak` first.

---

## What actually goes wrong

Both crashes are the same defect: the game creates an object, never checks
whether creation succeeded, and then dereferences the null pointer.

### Crash 1 — access violation at `mc.exe+0x000E792E`

Windows logs exception `0xC0000005`, fault offset `0x000E792E`, faulting module
`mc.exe`. The instruction is:

```asm
004E78FE  call dword ptr [edx+0x3C]   ; IDirect3D8::CreateDevice  (vtable slot 15)
004E7901  mov  eax, [ebp+0x44]        ; ...continues without checking the HRESULT
004E792E  mov  ecx, [eax]             ; <-- faults, EAX = 0
004E7932  call dword ptr [ecx+0xA0]   ; IDirect3DDevice8::SetViewport (slot 40)
```

The game requests **640×480 exclusive fullscreen** on adapter 0. Recovered
`D3DPRESENT_PARAMETERS` from a crash dump:

| Field | Value |
|---|---|
| BackBufferWidth / Height | 640 × 480 |
| BackBufferFormat | 22 (`D3DFMT_X8R8G8B8`) |
| Windowed | 0 — exclusive fullscreen |
| returned device | **NULL** |

For exclusive fullscreen, Direct3D 8 requires the width, height and format to
match an enumerated display mode. If your primary display is rotated to
portrait, its mode list contains `480 X 640` and **no** `640 X 480`.
`CreateDevice` fails, and the unchecked null device is dereferenced by
`SetViewport`.

The game writes its own evidence to `D3DEnum.txt` in the install folder. Look for
an adapter whose modes are all taller than they are wide — that is the culprit.

**Fix:** point `SysSetup device` at an adapter that offers 640×480.

### Crash 2 — access violation at `mc.exe+0x000A801B`

```asm
004A8007  call dword ptr [0x96E4E8]   ; MultiByteToWideChar -> filename
004A800D  mov  eax, [ebx+0x2CE8]      ; media interface -> NULL
004A801B  mov  edx, [eax]             ; <-- faults, EAX = 0
004A801E  call dword ptr [edx+0xC]
```

The filename recovered from the dump is
`gamedata\sound\music\music_intro.wma`. The game builds a DirectShow graph to
play its WMA soundtrack, but the Windows Media DirectShow source filter
(`dxmasf.dll`) no longer ships with Windows. `quartz.dll` and `devenum.dll` load;
the Windows Media source does not. The interface comes back null and is used
anyway.

**Fix:** `SysSetup music 1` suppresses that path. The game runs without its
music. Restoring music is tracked as future work — the 2001 Windows Media
redistributable on the CD is not a safe answer on a modern system.

---

## Compatibility notes

- Tested on Windows 11 Pro (build 26200), NVIDIA RTX 4080, English CD.
  Verified with game version 1.0 and again after applying the official patch
  1.2 — the same `config.cfg` works for both. Verified on one machine only.
- Patch 1.2 applies cleanly on Windows 11 when run **elevated**. It changes
  `mc.exe`, three Lua scripts and the string tables, and leaves `config.cfg`
  alone. Both crashes above are still present in the 1.2 executable. Details
  in [`docs/patch-1.2.md`](docs/patch-1.2.md).
- The game runs at 640×480. Higher resolutions are enumerated by the engine and
  are not yet explored.
- GameSpy multiplayer is dead and out of scope.

## Modding

The game is unusually open for its age, and this is the reason the project
exists. All verified:

- **200 plain-text Lua scripts** in `scripts\`, across 56 namespaces —
  `DEFAULT`, `MAPS`, `SCENARIO1`–`SCENARIO20`, `TUTORIAL1`–`TUTORIAL12`,
  `NET0`–`NET8`. Economy tuning lives in `businesssettings.lua`,
  `blocksettings.lua` and `commoditysettings.lua`.
- **Saves are Lua too.** `profiles\<name>\settings.lua` contains
  `g_ProfileOptions.BoardName = "gb"`, which selects among **19 national
  boards** shipped on the disc (`usa`, `f`, `ger`, `aus`, `swe`, and more).
- `parameters\*.prm` holds per-decade tuning, plus `aiparameter.prm` and
  `consumer.prm`.
- The shipped executable still contains debug flags (`AIDEBUG`, `DEBUGTEXT`,
  `SHOWALLCARS`, `CHEATINGGIT`) and remnants of the developers' block and
  building editors.

See [`docs/phase-0-findings.md`](docs/phase-0-findings.md) for the full
investigation, and
[`docs/superpowers/specs/`](docs/superpowers/specs/) for the project design.

## Licence

MIT — see [LICENSE](LICENSE). This covers the tools and documentation in this
repository only. Monopoly Tycoon itself is the property of its rights holders
and is not distributed here.
