"""Apply the Windows 11 fixes to an installed copy of Monopoly Tycoon.

Two crashes stop the 2001 game on modern Windows, both the same defect: the
game creates an object, never checks whether it succeeded, then dereferences
null.

1. ``IDirect3D8::CreateDevice`` fails when the game asks for 640x480 exclusive
   fullscreen on an adapter with no such mode — for example a rotated portrait
   primary display. It then calls ``SetViewport`` on the null device.
   Fixed by pointing ``SysSetup device`` at an adapter that has the mode.

2. Opening ``gamedata\\sound\\music\\music_intro.wma`` fails because the Windows
   Media DirectShow source filter no longer ships with Windows.
   Avoided by ``SysSetup music 1``, which suppresses that path; fixed by
   ``--music``, which installs a stand-in for the missing filter and writes
   ``music 0`` (see ``music.py``).

A third problem must be solved before either fix can persist: the game cannot
write ``config.cfg`` inside Program Files under a standard user account.

The same mechanism sets the resolution. Any mode the chosen adapter enumerates
works, fullscreen or (on patch 1.2) windowed; 1920x1080 and 1280x720 windowed
were verified on one machine.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import d3denum, gameconfig, music

DEFAULT_INSTALL = Path(r"C:\Program Files (x86)\Infogrames\Monopoly Tycoon")
DEFAULT_WIDTH = gameconfig.DEFAULT_WIDTH
DEFAULT_HEIGHT = gameconfig.DEFAULT_HEIGHT
TARGET_BPP = 32

# MD5 of mc.exe for the builds this tool has been run against. Patch 1.2
# renamed the windowed-mode key, so the version decides which keys are honoured.
KNOWN_BUILDS = {
    "fd34022887dc347b664b689fedeb9a37": "1.0",
    "5965dbb1a4be4f58fa4452df78786e63": "1.2",
}
WINDOWED_NEEDS = "1.2"


class FixError(Exception):
    """A problem that stops the fix being applied."""


@dataclass
class Plan:
    """What the fix would do, before it does it."""

    game_dir: Path
    game_version: str
    writable: bool
    adapter: int | None
    adapter_source: str
    adapter_description: str
    width: int
    height: int
    windowed: bool
    config_path: Path
    config_exists: bool
    rendered: str
    music: bool = False
    shim_source: Path | None = None
    shim_target: Path | None = None
    reader_available: bool = True
    run_as_admin: bool = False

    @property
    def ok(self) -> bool:
        return (self.writable and self.adapter is not None
                and not self.music_problems)

    @property
    def music_problems(self) -> list[str]:
        """What stops ``--music`` from being applied. Empty when music is off."""
        if not self.music:
            return []
        out = []
        if self.shim_source is None:
            out.append("%s is not bundled with this copy of mtrevival. Build it "
                       "with tools\\wmsource-shim\\build.ps1 (needs the MSVC "
                       "Build Tools) or install a release that includes it."
                       % music.SHIM_NAME)
        if not self.reader_available:
            out.append("The WM ASF Reader (Windows Media) is not registered for "
                       "32-bit programs. On Windows N editions install the "
                       "Media Feature Pack, then retry.")
        return out

    @property
    def warnings(self) -> list[str]:
        """Things the user should know that do not stop the fix.

        Only 1.0 was observed ignoring the Window key. An unrecognised build
        gets told exactly that, not a prediction.
        """
        out = []
        if self.windowed and self.game_version == "unknown":
            out.append("Windowed mode is only verified on patch %s, and this "
                       "mc.exe is not a build this tool recognises. The Window "
                       "key is written; whether the game honours it is unproven."
                       % WINDOWED_NEEDS)
        elif self.windowed and self.game_version != WINDOWED_NEEDS:
            out.append("Windowed mode needs patch %s; game version here is %s, "
                       "which ignores the Window key and runs fullscreen."
                       % (WINDOWED_NEEDS, self.game_version))
        if self.music and self.run_as_admin:
            out.append("mc.exe is set to run as administrator. An elevated "
                       "process ignores per-user COM registrations, so it will "
                       "not see the music shim and will crash with music 0. "
                       "Clear that compatibility setting before playing.")
        return out


def find_install(explicit: Path | None = None) -> Path:
    """Locate the game directory, or raise FixError.

    An explicitly supplied directory is never overridden by a search: writing
    into a different install than the one the caller named would be worse than
    failing.
    """
    if explicit is not None:
        if (explicit / "mc.exe").is_file():
            return explicit
        raise FixError("Could not find mc.exe in %s" % explicit)

    for path in (DEFAULT_INSTALL,
                 Path(r"C:\Program Files\Infogrames\Monopoly Tycoon"),
                 Path(r"C:\Program Files (x86)\Infogrames Interactive\Monopoly Tycoon")):
        if (path / "mc.exe").is_file():
            return path
    raise FixError(
        "Could not find mc.exe. Pass the install directory with --game-dir.")


def game_version(game_dir: Path) -> str:
    """'1.0', '1.2', or 'unknown', from the hash of mc.exe."""
    digest = hashlib.md5((game_dir / "mc.exe").read_bytes()).hexdigest()
    return KNOWN_BUILDS.get(digest, "unknown")


def is_writable(directory: Path) -> bool:
    """True if this account can create files in the game directory."""
    probe = directory / ".mtrevival-write-probe"
    try:
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def grant_command(directory: Path) -> str:
    """The elevated command that makes the game directory writable."""
    return ('icacls "%s" /grant "$($env:USERNAME):(OI)(CI)M" /T' % directory)


def read_adapters(game_dir: Path) -> tuple[list[d3denum.Adapter], str]:
    """Adapters as the game sees them, falling back to Windows enumeration."""
    enum_file = game_dir / "D3DEnum.txt"
    if enum_file.is_file():
        adapters = d3denum.parse(enum_file.read_text(errors="replace"))
        if adapters:
            return adapters, "D3DEnum.txt"
    from . import displays  # imported lazily; Windows-only
    return displays.enumerate_adapters(), "Windows display enumeration"


def build_plan(game_dir: Path, width: int = DEFAULT_WIDTH,
               height: int = DEFAULT_HEIGHT, windowed: bool = False,
               with_music: bool = False) -> Plan:
    """Work out what to do without changing anything."""
    adapters, source = read_adapters(game_dir)
    index = d3denum.choose_adapter(adapters, width, height, TARGET_BPP)
    if index is None:
        # Retry ignoring colour depth: some sources record modes without bpp.
        index = d3denum.choose_adapter(adapters, width, height)

    description = ""
    for adapter in adapters:
        if adapter.index == index:
            description = adapter.description
            break

    config_path = game_dir / "config.cfg"
    config = gameconfig.default_config(index if index is not None else 0,
                                       width, height, windowed, with_music)
    return Plan(
        game_dir=game_dir,
        game_version=game_version(game_dir),
        writable=is_writable(game_dir),
        adapter=index,
        adapter_source=source,
        adapter_description=description,
        width=width,
        height=height,
        windowed=windowed,
        config_path=config_path,
        config_exists=config_path.is_file(),
        rendered=config.render(),
        music=with_music,
        shim_source=music.bundled_shim() if with_music else None,
        shim_target=game_dir / music.SHIM_NAME,
        reader_available=music.reader_available() if with_music else True,
        run_as_admin=music.run_as_admin_flagged(game_dir / "mc.exe") if with_music else False,
    )


def install_music(plan: Plan) -> None:
    """Copy the shim into the game directory and register it for this user.

    The copy lives next to mc.exe rather than inside the Python package so
    the registration survives the package being upgraded, moved, or run from
    a temporary environment.
    """
    if plan.music_problems:
        raise FixError("\n".join(plan.music_problems))
    assert plan.shim_source is not None and plan.shim_target is not None
    try:
        if not (plan.shim_target.is_file()
                and plan.shim_target.read_bytes() == plan.shim_source.read_bytes()):
            shutil.copy2(plan.shim_source, plan.shim_target)
    except OSError as error:
        raise FixError("Could not copy %s into the game directory (%s). "
                       "Close the game if it is running, then retry."
                       % (music.SHIM_NAME, error))
    music.register(plan.shim_target)


def apply(plan: Plan) -> Path | None:
    """Write config.cfg, backing up any existing file. Returns the backup path.

    With music requested, the shim is installed and registered first, so a
    failure there leaves the previous config (and its ``music 1``) in place.
    """
    if not plan.writable:
        raise FixError(
            "The game directory is not writable by this account.\n"
            "Run this once in an elevated PowerShell, then try again:\n\n    "
            + grant_command(plan.game_dir))
    if plan.adapter is None:
        raise FixError(
            "No display adapter offers %dx%d. Every adapter reported only other "
            "modes — a rotated display can do this. Pick a resolution the "
            "adapter lists (see `adapters`), rotate a display to landscape, or "
            "attach one that supports the mode."
            % (plan.width, plan.height))
    if plan.music:
        install_music(plan)

    backup = None
    if plan.config_exists:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = plan.config_path.with_suffix(".cfg.%s.bak" % stamp)
        shutil.copy2(plan.config_path, backup)

    plan.config_path.write_bytes(plan.rendered.encode("ascii"))
    return backup


def describe(plan: Plan) -> str:
    """A human-readable summary of the plan."""
    lines = [
        "Game directory : %s" % plan.game_dir,
        "Game version   : %s" % plan.game_version,
        "Writable       : %s" % ("yes" if plan.writable else "NO"),
        "Resolution     : %dx%d %s" % (plan.width, plan.height,
                                       "windowed" if plan.windowed else "fullscreen"),
        "Adapter source : %s" % plan.adapter_source,
    ]
    if plan.adapter is None:
        lines.append("Adapter        : none supports %dx%d" % (plan.width, plan.height))
    else:
        lines.append("Adapter        : %d%s"
                     % (plan.adapter,
                        (" (%s)" % plan.adapter_description)
                        if plan.adapter_description else ""))
    lines.append("config.cfg     : %s"
                 % ("exists, will be backed up" if plan.config_exists else "new"))
    if plan.music:
        lines.append("Music          : restore (music 0; %s -> %s, registered "
                     "per user)" % (music.SHIM_NAME, plan.shim_target))
    else:
        lines.append("Music          : off (music 1); add --music to restore it")
    for problem in plan.music_problems:
        lines.append("PROBLEM        : %s" % problem)
    for warning in plan.warnings:
        lines.append("WARNING        : %s" % warning)
    lines.append("")
    lines.append("config.cfg to write:")
    lines += ["    " + line for line in plan.rendered.replace("\r\n", "\n").rstrip().split("\n")]
    if not plan.writable:
        lines += ["", "Run this once in an elevated PowerShell first:",
                  "    " + grant_command(plan.game_dir)]
    return "\n".join(lines)
