# Contributing

Thanks for helping keep a 2001 game alive. Two rules come before anything else:

1. **No game content, ever.** No ISO, cabs, Lua, `.wma`, `.wav`, archives, or
   long quotes from any of them — in commits, issues, or pull requests. Users
   bring their own disc. `.gitignore` blocks the extensions; do not add
   exceptions for game files. (The two `.wma` files under
   `tools/wmsource-shim/harness` are synthesised sine tones, not game data.)
2. **Say what was observed, not what should work.** "Verified on one machine"
   with the game version, Windows build, and the evidence (a trace, a log,
   the exact `config.cfg`) beats "this works". A `SysSetup` key that has not
   been watched taking effect is unproven — say so.

## Workflow

`main` is protected: every change lands through a pull request with green CI,
squash-merged. Direct pushes are refused, including for maintainers.

1. **Start from an issue.** Open one or pick one; the tracker's milestones are
   the roadmap. Small fixes can skip this, but the PR still says why.
2. **Branch** from `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
3. **Commit** in [Conventional Commits](https://www.conventionalcommits.org/)
   style (`feat(fixpack): …`, `fix(music): …`, `docs: …`). One PR, one concern;
   tangents become follow-up issues.
4. **Test.** A fixed bug ends with a regression test that fails without the
   fix; a feature ends with tests that define it. `pytest -q` must pass on
   Windows and Ubuntu (registry-only tests skip on Ubuntu).
5. **Open the PR** with the template filled in: summary, evidence, test plan,
   `Closes #N`. CI runs pytest on both platforms, builds the shim with MSVC
   and replays the game's music call sequence through it.
6. **Review**, then **squash-merge**. The squash message is the PR title in
   Conventional Commits form.

## Local development

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e . pytest
.venv\Scripts\python -m pytest -q

# the music shim (needs the MSVC Build Tools, x86 toolchain)
pwsh tools\wmsource-shim\build.ps1            # -> src\mtrevival\bin\wmsource-shim.dll
pwsh tools\wmsource-shim\build-harness.ps1    # -> src\mtrevival\bin\harness.exe

# register the built shim for your account, then replay the game's calls through it
.venv\Scripts\python -c "from pathlib import Path; from mtrevival import music; music.register(Path('src/mtrevival/bin/wmsource-shim.dll').resolve())"
src\mtrevival\bin\harness.exe tools\wmsource-shim\harness\tone-a.wma tools\wmsource-shim\harness\tone-b.wma
```

```powershell
# the player-facing exe (PyInstaller; needs the shim built first)
.venv\Scripts\python -m pip install pyinstaller
pwsh tools\exe\build-exe.ps1                  # -> dist\MonopolyTycoonFix.exe
```

`harness.exe --null-renderer …` skips the audio device (what CI does).
`tools\wmsource-shim\harness\make-fixtures.ps1` regenerates the tone files
with ffmpeg. The built DLL is gitignored; wheels and releases carry it.

Changes that touch how the game behaves (a new `SysSetup` key, the shim, the
adapter choice) need a real launch on a real install, and the PR says what
was seen. `tools\monitor-run.ps1` records child processes and dialog text;
set `WMSOURCE_SHIM_LOG=<file>` for the shim's trace.

## Releasing

1. In a PR: bump `version` in `pyproject.toml`, move the `Unreleased` notes
   in `CHANGELOG.md` under the new version with today's date, update the
   compare links.
2. After the merge: `git tag -a vX.Y.Z -m "vX.Y.Z"` on `main`, `git push origin vX.Y.Z`.
3. The Release workflow checks the tag against `pyproject.toml`, builds the
   shim and the wheel, runs the tests, publishes to PyPI through Trusted
   Publishing, and creates the GitHub release with the changelog section as
   notes and the DLL, wheel and sdist attached.
4. Verify from the registry: `pipx run mtrevival==X.Y.Z check`.

## Issues

Bug reports need the output of `mtrevival check` (it prints the game version
by hash), `config.cfg`, `D3DEnum.txt`, and the Application event log entry
for the crash if there is one. The templates ask for exactly that.
