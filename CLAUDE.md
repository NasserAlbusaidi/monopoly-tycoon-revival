# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Make Monopoly Tycoon (2001) run and be moddable on Windows 10/11. The repo ships
**tools and docs only**. Game content (ISO, cabs, `.lua`, `.wma`, `archive.bin`,
…) is gitignored by extension and must never be committed or quoted at length —
users bring their own disc. This is a legal rule, not a preference.

Install media and crash dumps live outside the repo at
`../monopoly-tycoon/` and `../crashdumps/`. The installed game is at
`C:\Program Files (x86)\Infogrames\Monopoly Tycoon`.

## Commands

Python ≥3.12, stdlib only, no runtime deps. A venv exists at `.venv/`.

```powershell
.venv\Scripts\python -m pip install -e .        # editable install
.venv\Scripts\python -m pytest -q               # all tests (~90, <1 s)
.venv\Scripts\python -m pytest tests/test_fixpack.py -k landscape   # one test
.venv\Scripts\python -m mtrevival adapters      # list adapters + 640x480 fit
.venv\Scripts\python -m mtrevival check         # dry run against real install
.venv\Scripts\python -m mtrevival fix [--game-dir DIR]   # writes config.cfg
.venv\Scripts\python -m mtrevival fix --resolution 1920x1080 [--windowed] [--music]
pwsh tools\wmsource-shim\build.ps1               # builds src\mtrevival\bin\wmsource-shim.dll (MSVC x86)
```

`pyproject.toml` sets `pythonpath = ["src", "tests"]`, so tests import
`mtrevival` directly and `test_fixpack.py` imports the `REAL` fixture from
`test_d3denum.py`. No lint/format tool is configured. `test_music.py` writes
real registry keys under `HKCU\Software\mtrevival-test\<uuid>` and deletes
them; the fixpack and CLI tests monkeypatch `music.*` so they never read the
real registry or need the built DLL.

`tools/wmsource-shim/` is the C++ COM shim that restores music (see below);
its built DLL is package data and is committed. `tools/probe-wma-source.cpp`
is the standalone DirectShow probe used to diagnose it. `tools/monitor-run.ps1`
launches an exe and logs every child process command line and every dialog's
text (run it elevated to see elevated windows). None of these are in the test
suite.

## Architecture

`src/mtrevival/` — one module per concern, all pure except `displays.py`:

- `d3denum.py` — parses the game's own `D3DEnum.txt` (adapter list with
  `Vid Mode W X H X bpp` lines) into `Adapter` objects; `choose_adapter()` picks
  the first adapter that offers the target mode. **This is the authoritative
  source**: it records what the *game* enumerates, which can differ from Windows.
- `displays.py` — ctypes `EnumDisplayDevices`/`EnumDisplaySettings` fallback for
  first run, before `D3DEnum.txt` exists. Imported lazily (Windows-only). D3D8
  adapter order is not guaranteed to match it; a config from this path should be
  re-derived once the game has run.
- `gameconfig.py` — reads/writes `config.cfg`: `SysSetup <key> <value>` lines,
  **CRLF**, ASCII, fixed `KEY_ORDER`. Key spellings match the game's own format
  strings (`Texdetail` is capitalised on purpose).
- `fixpack.py` — orchestration: `find_install` → `build_plan` (pure, returns a
  `Plan`) → `describe` / `apply` (side effects: timestamped `.bak`, write).
  `find_install` never falls back to a search when `--game-dir` is explicit.
  With `--music`, `apply` installs the shim (copy next to `mc.exe`, per-user
  COM registration) *before* writing `config.cfg`, so a failure leaves
  `music 1` in place.
- `music.py` — the soundtrack fix: `winreg` access to the 32-bit view of
  `HKCU\Software\Classes\CLSID\{6B6D0800-…}` (the game is 32-bit), the WM ASF
  Reader preflight, and the run-as-administrator check. Never registers under
  HKLM.
- `__main__.py` — argparse CLI over `fixpack`. Exit codes: 0 ok, 1 plan not ok /
  apply failed, 2 install not found.

Tests build a fake install in `tmp_path` (`mc.exe` stub + the real `D3DEnum.txt`
text captured from the portrait-primary machine) so the adapter-selection logic
is exercised against the actual crash scenario.

## Domain facts that shape the code

- Both startup crashes are unchecked-null bugs in `mc.exe`; the fix is
  configuration plus a COM shim, never exe patching. `SysSetup device N` must
  be chosen **by capability** (adapter has `640 X 480`), never hardcoded — a
  portrait primary display is adapter 0 and offers only `480 X 640`.
  `SysSetup music 1` means music **off** (the game stores `enabled = value == 0`)
  and skips the WMA DirectShow path; `music 0` is only safe with the shim.
- Music: the game does `CoCreateInstance({6B6D0800-…}, IID_IBaseFilter)` — the
  2001 Windows Media Source Filter, unregistered on Win11 — then
  `FindPin(L"Stream 1")`, and re-`Load`s the same filter for every track. The
  modern WM ASF Reader names its pin `Raw Audio 0` and **refuses a second
  `Load` on one instance**, so a CLSID/pin-name byte patch of the exe gives one
  track only. `wmsource-shim.dll` aggregates a fresh reader per `Load` under
  the legacy CLSID. Per-user registration is invisible to an elevated process;
  `fix --music` warns if `mc.exe` carries the RUNASADMIN compat flag. Full
  evidence: `docs/music.md`.
- Patch 1.2 creates an empty `MTS.txt` at launch and deletes it on clean
  exit. Killing the process leaves it, and the next launch offers Safe Mode,
  which overwrites `config.cfg`. Delete `MTS.txt` after any forced stop.
- Observed to take effect: `device`, `bitdepth 32`, `music` (both values),
  `width`, `height` (1920x1080 fullscreen), and on 1.2 `Window 1` (1280x720
  windowed). Observed ignored: 1.0's `windowed 1`, `bitdepth 16`. Treat any
  other `SysSetup` key as unproven until watched working. `KEY_ORDER` in
  `gameconfig.py` mirrors the verified files — `Window` goes after `music`.
  Full evidence, disassembly, and dump analysis: `docs/phase-0-findings.md`,
  `docs/patch-1.2.md`, `docs/music.md`.
- `fixpack.KNOWN_BUILDS` maps `mc.exe` MD5 → game version; `--windowed` warns
  (does not refuse) when the build is not 1.2.
- Program Files is not writable for a standard user, so the game silently fails
  to persist config/profiles; `fixpack` detects this and prints the `icacls`
  command rather than elevating itself.
- Verified on one machine only (Win11 26200, RTX 4080, English CD, game 1.0
  and 1.2). Say "verified on one machine", never "works".
- Patch 1.2 is applied on the dev machine and works with the same `config.cfg`.
  It renames `windowed` → `Window` and adds `Fog`, `Halos`, `Multitexture`,
  `No3d`, `NoMovie`, plus Safe Mode (`MTS.txt`) and a crash handler
  (`__crash.sav`). Both null-deref bugs persist at `0xE8ECB` / `0xA8BED`.
  Run the patcher elevated. See `docs/patch-1.2.md`. Pre-patch 1.0 backup:
  `D:\personal\reviving-games\install-backup-prepatch-20260827`.
- The game's registry keys live under `HKLM\SOFTWARE\WOW6432Node\Infogrames*`
  and the Uninstall key `{B975F4A1-63B6-11D4-BFEC-005004AF2D32}`.
- Gameplay, scenarios, and even savegames are plain-text Lua under the install
  dir — the basis for Phases 2–3. Mods must ship as diffs/overlays against the
  user's files, never as copies of game Lua.

## Roadmap

`docs/superpowers/specs/2026-08-27-monopoly-tycoon-revival-design.md` defines
Phases 0–4. Phase 0 (boot) is complete; Phase 1 `fixpack` is released
(v0.1.0 config, v0.2.0 resolution/windowed, v0.3.0 music). Note the spec's
Phase 1 also calls for direct cab extraction and patch application — **not
implemented**; the current fixpack only writes `config.cfg` (and the music
shim) against an existing install. Phase 2 (`mtdata` Lua schema + demo mod)
and Phase 3 (`mtarc` archive reader) are unstarted. The GitHub issue tracker
(31 issues, milestones v0.2.0–v1.0.0) plans a managed-instance /
compatibility-profile / patch-engine architecture that the shipped fixpack
does not follow; work is tracked there by issue and PR, and the drift is a
known open decision.

## Debugging lessons from Phase 0

Recorded because Claude took two failed sessions to reach a fix that was in
hand after the first diagnosis. Do not repeat this.

- **When the root cause names a knob, test that knob first.** The first pass
  identified "adapter 0 has no 640x480" and found `SysSetup device`. The next
  experiment tested `windowed 1` instead. `windowed` is ignored by the game, so
  the result was a false negative that cost the rest of the session.
- **One ignored key is not proof the file is ignored.** "`windowed` and
  `bitdepth 16` did nothing" was promoted to "`config.cfg` is not read at
  device creation". Wrong. Only a positive observation (`device 1` moved the
  crash) settles what the game reads.
- **Root cause was reached at step 1; stop proving it.** Crash dumps,
  disassembly and `D3DPRESENT_PARAMETERS` recovery all confirmed what
  `D3DEnum.txt` already showed. Reach for dumps when the knob fails, not before.
- **Each test costs a user launch plus an elevated command.** Spend round-trips
  on the highest-evidence hypothesis. Applying two fixes at once (`device 1` +
  `music 1`) beat single-variable purity here, because crash 2 was unreachable
  until crash 1 was gone.
- Game-side evidence order, cheapest first: `D3DEnum.txt` / `D3DLOG.txt` →
  Application event log (offset + exception) → `config.cfg` change → WER
  `LocalDumps` (needs the registry key; `ReportArchive` holds no `.mdmp`).
