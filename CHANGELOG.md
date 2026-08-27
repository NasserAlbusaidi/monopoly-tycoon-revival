# Changelog

All notable changes to `mtrevival`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Everything is verified on one
machine (Windows 11, English CD, patch 1.0 and 1.2) unless stated otherwise.

## [Unreleased]

## [0.4.0] - 2026-08-27

For players, not just for people with a terminal.

### Added
- **`MonopolyTycoonFix.exe`** on every release: one file, double-click, no
  Python needed. Built by CI with PyInstaller from this source; unsigned, so
  Windows SmartScreen asks once.
- **Guided fix** when run with no arguments (`mtrevival`, `mtrevival wizard`,
  or the exe): finds the install, fixes the folder permission itself through
  a single Windows elevation prompt instead of printing an `icacls` command,
  offers landscape resolutions (1920x1080 recommended, your desktop mode as
  unverified, 640x480 original), asks about music, applies.
- `--version`.
- README that starts with "Own the CD? Three steps." and says plainly where
  the game can and cannot be had.

### Fixed
- The wizard never offers a portrait display's own mode, even when that
  adapter lists it; the game's UI is landscape and that display is the
  original crash.

## [0.3.1] - 2026-08-27

First release on PyPI: `pip install mtrevival` or `pipx run mtrevival`.
No change to what the tool does on the game.

### Changed
- `wmsource-shim.dll` is no longer committed. CI builds it from
  `tools/wmsource-shim` on every push; wheels and GitHub releases carry it.
  From a git checkout, run `tools\wmsource-shim\build.ps1` or take the DLL
  from a release.
- `mtrevival` is now a console script (`mtrevival check`, `pipx run mtrevival`).

### Added
- CI: pytest on Windows and Ubuntu; MSVC build of the shim; an end-to-end
  harness that replays the game's music call sequence through the built shim
  against synthesised tone files.
- Release workflow: tag → build → PyPI (Trusted Publishing) → GitHub release.
- `CONTRIBUTING.md`, issue and pull request templates, this changelog.

## [0.3.0] - 2026-08-27

### Added
- `fix --music` restores the soundtrack. The game creates the 2001 Windows
  Media Source Filter (`{6B6D0800-…}`), which modern Windows no longer
  registers. `wmsource-shim.dll` answers that CLSID by aggregating Windows'
  WM ASF Reader, creating a fresh reader per `Load` (the reader refuses a
  second one) and mapping `FindPin(L"Stream 1")` onto its `Raw Audio 0` pin.
  Registered per user in the 32-bit view of `HKCU\Software\Classes`; no
  elevation, no system codecs, no patched executable.
- Preflight: refuses without the WM ASF Reader (Media Feature Pack on N
  editions); warns when `mc.exe` is flagged run-as-administrator or the shell
  is elevated.
- `docs/music.md`: disassembly of the music path, reader behaviour, why an
  executable byte patch was rejected, verification record.

### Fixed
- Documented that patch 1.2 drops `MTS.txt` while running and offers Safe
  Mode (which overwrites `config.cfg`) after a killed process.

## [0.2.0] - 2026-08-27

### Added
- `--resolution WxH` on every subcommand; any mode the chosen adapter lists.
- `--windowed` on `check`/`fix` (patch 1.2's `Window 1`), with game-version
  detection by `mc.exe` MD5 and a warning on 1.0, which ignores the key.
- `docs/patch-1.2.md`: the official patch applies on Windows 11 (run it
  elevated) and runs with the same `config.cfg`.
- `tools/monitor-run.ps1`: logs child processes and dialog text of a launch.

## [0.1.0] - 2026-08-27

### Added
- `fixpack`: derives a working `config.cfg` from the game's own `D3DEnum.txt`,
  choosing a display adapter by capability (a portrait primary display is
  the crash) and writing `music 1` to avoid the WMA crash. `adapters`,
  `check`, `fix` subcommands; timestamped backups; detects an unwritable
  Program Files install and prints the `icacls` command.
- `docs/phase-0-findings.md`: both startup crashes traced to unchecked
  nulls in `mc.exe`.

[Unreleased]: https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/NasserAlbusaidi/monopoly-tycoon-revival/releases/tag/v0.1.0
