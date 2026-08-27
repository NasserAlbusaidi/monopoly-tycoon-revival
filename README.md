# Monopoly Tycoon Revival

Make **Monopoly Tycoon** (2001, Deep Red Games / Infogrames) run on Windows
10 and 11 — with its music.

On a modern PC the game installs fine and then crashes right after the
studio logo. This fixes that in under a minute. Nothing in the game is
modified: it writes one settings file and, for the music, registers one
small component for your user account.

## Own the CD? Three steps.

1. **Install the game from your CD** as usual (`Setup.exe`). Optional but
   recommended: apply the publisher's free [patch 1.2](https://archive.org/details/MonopolyTycoon1.2)
   afterwards (right-click → *Run as administrator*); it adds a sandbox
   scenario and lets the game run in a window.
2. **Download `MonopolyTycoonFix.exe`** from the
   [latest release](https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/releases/latest)
   and double-click it. It asks two questions (resolution, music) and does
   the rest. If Windows says *"Windows protected your PC"*, click **More
   info → Run anyway**: the file is unsigned, not harmful — every release is
   built by GitHub from the source in this repository, and you can read
   exactly what it does below.
3. **Launch the game** from the Start menu or `mc.exe`. Do not use "Run as
   administrator" — the music component is registered for your user, and an
   elevated game cannot see it.

Something went wrong? [Open an issue](https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/issues/new/choose)
and paste what the fix printed.

### Where to get the game

It is not sold anywhere. Hasbro owns the *Monopoly* brand, Atari owns the
2001 code, and nobody currently holds both, so there is no GOG or Steam
release (you can [vote for one](https://www.gog.com/dreamlist/game/monopoly-tycoon-2001)).
Your own CD, or a second-hand copy — they are cheap. **This project does not
distribute the game and contains no game content.**

---

## For the technically inclined

Everything below is what the exe does, spelled out, plus the Python package
it is built from.

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

`music 1` means music **off**. That is the safe setting without the shim
described under [Music](#music); the game runs, silently.

That is the whole fix. Launch `mc.exe`.

---

## Working it out automatically

Requires Python 3.12 or newer. Standard library only.

```
py -m pip install mtrevival        # or: pipx install mtrevival
mtrevival                          # no arguments: the guided fix (what the exe runs)
mtrevival adapters                 # list adapters, show which support 640x480
mtrevival check                    # show what would be written, change nothing
mtrevival fix                      # write config.cfg, backing up any existing one

mtrevival fix --resolution 1920x1080             # any mode the adapter lists
mtrevival fix --resolution 1280x720 --windowed   # windowed needs patch 1.2
mtrevival fix --music                            # restore the soundtrack
```

`py -m mtrevival …` works too. From a git checkout use `py -m pip install .`;
the music shim then needs building (see `CONTRIBUTING.md`) or the DLL from a
[release](https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/releases).

Example on a machine with a portrait primary display:

```
source: D3DEnum.txt
  adapter 0  NVIDIA GeForce RTX 4080   modes=46   no 640x480  [portrait]
  adapter 1  NVIDIA GeForce RTX 4080   modes=54   OK 640x480
```

`fix` never overwrites an existing `config.cfg` without copying it to a
timestamped `.bak` first.

### Music

The game plays its WMA soundtrack through a DirectShow filter that Windows
dropped years ago. `fix --music` copies `wmsource-shim.dll` (built from
[`tools/wmsource-shim`](tools/wmsource-shim), source included) next to
`mc.exe`, registers it **for your user only** — no elevation, nothing outside
your profile — and writes `music 0`. The shim hands the game Windows' own
WM ASF Reader with the two adaptations the game needs. Details, evidence and
removal in [`docs/music.md`](docs/music.md).

Do not run the game "as administrator" with music on: an elevated process
cannot see per-user COM registrations. `fix --music` warns if that flag is set.

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
play its WMA soundtrack and asks for the 2001 Windows Media DirectShow source
filter by CLSID. Windows 11 keeps only a 5 KB stub of `dxmasf.dll` and no
longer registers the class, so `CoCreateInstance` fails. `quartz.dll` and
`devenum.dll` load; the Windows Media source does not. The interface comes
back null and is used anyway.

**Fix:** `SysSetup music 1` suppresses that path, and the game runs without
its music. `fix --music` restores it: the filter the game asks for,
`{6B6D0800-…}`, is answered by a shim that wraps Windows' WM ASF Reader,
creating a fresh reader per track (the reader refuses a second `Load`) and
mapping the game's `FindPin(L"Stream 1")` onto the reader's `Raw Audio 0`.
The 2001 Windows Media redistributable on the CD is not touched. See
[`docs/music.md`](docs/music.md).

---

## Compatibility notes

- Tested on Windows 11 Pro (build 26200), NVIDIA RTX 4080, English CD.
  Verified with game version 1.0 and again after applying the official patch
  1.2 — the same `config.cfg` works for both. Verified on one machine only.
- Patch 1.2 applies cleanly on Windows 11 when run **elevated**. It changes
  `mc.exe`, three Lua scripts and the string tables, and leaves `config.cfg`
  alone. Both crashes above are still present in the 1.2 executable. Details
  in [`docs/patch-1.2.md`](docs/patch-1.2.md).
- Resolution is free. `SysSetup width` / `height` accept any mode the chosen
  adapter enumerates; 1920×1080 exclusive fullscreen and 1280×720 windowed
  (`SysSetup Window 1`, patch 1.2 only) were verified running with a sane UI.
  The 1.0 key `windowed` is ignored; 1.2 renamed it.
- Music was verified on patch 1.2 (intro track by ear, all ten tracks and
  repeated track changes in a DirectShow harness). It needs Windows Media,
  which N editions get from the Media Feature Pack.
- Patch 1.2 drops an empty `MTS.txt` in the game folder while it runs and
  removes it on exit. If the game is killed, delete that file, or the next
  launch offers Safe Mode and overwrites `config.cfg`.
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
