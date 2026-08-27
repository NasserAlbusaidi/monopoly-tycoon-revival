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
   Fixed by ``SysSetup music 1``, which suppresses that path.

A third problem must be solved before either fix can persist: the game cannot
write ``config.cfg`` inside Program Files under a standard user account.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import d3denum, gameconfig

DEFAULT_INSTALL = Path(r"C:\Program Files (x86)\Infogrames\Monopoly Tycoon")
TARGET_WIDTH = 640
TARGET_HEIGHT = 480
TARGET_BPP = 32


class FixError(Exception):
    """A problem that stops the fix being applied."""


@dataclass
class Plan:
    """What the fix would do, before it does it."""

    game_dir: Path
    writable: bool
    adapter: int | None
    adapter_source: str
    adapter_description: str
    config_path: Path
    config_exists: bool
    rendered: str

    @property
    def ok(self) -> bool:
        return self.writable and self.adapter is not None


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


def build_plan(game_dir: Path) -> Plan:
    """Work out what to do without changing anything."""
    adapters, source = read_adapters(game_dir)
    index = d3denum.choose_adapter(adapters, TARGET_WIDTH, TARGET_HEIGHT, TARGET_BPP)
    if index is None:
        # Retry ignoring colour depth: some sources record modes without bpp.
        index = d3denum.choose_adapter(adapters, TARGET_WIDTH, TARGET_HEIGHT)

    description = ""
    for adapter in adapters:
        if adapter.index == index:
            description = adapter.description
            break

    config_path = game_dir / "config.cfg"
    config = gameconfig.default_config(index if index is not None else 0)
    return Plan(
        game_dir=game_dir,
        writable=is_writable(game_dir),
        adapter=index,
        adapter_source=source,
        adapter_description=description,
        config_path=config_path,
        config_exists=config_path.is_file(),
        rendered=config.render(),
    )


def apply(plan: Plan) -> Path | None:
    """Write config.cfg, backing up any existing file. Returns the backup path."""
    if not plan.writable:
        raise FixError(
            "The game directory is not writable by this account.\n"
            "Run this once in an elevated PowerShell, then try again:\n\n    "
            + grant_command(plan.game_dir))
    if plan.adapter is None:
        raise FixError(
            "No display adapter offers %dx%d. Every adapter reported only other "
            "modes — a rotated display can do this. Rotate a display to "
            "landscape, or attach one that supports 640x480."
            % (TARGET_WIDTH, TARGET_HEIGHT))

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
        "Writable       : %s" % ("yes" if plan.writable else "NO"),
        "Adapter source : %s" % plan.adapter_source,
    ]
    if plan.adapter is None:
        lines.append("Adapter        : none supports %dx%d"
                     % (TARGET_WIDTH, TARGET_HEIGHT))
    else:
        lines.append("Adapter        : %d%s"
                     % (plan.adapter,
                        (" (%s)" % plan.adapter_description)
                        if plan.adapter_description else ""))
    lines.append("config.cfg     : %s"
                 % ("exists, will be backed up" if plan.config_exists else "new"))
    lines.append("")
    lines.append("config.cfg to write:")
    lines += ["    " + line for line in plan.rendered.replace("\r\n", "\n").rstrip().split("\n")]
    if not plan.writable:
        lines += ["", "Run this once in an elevated PowerShell first:",
                  "    " + grant_command(plan.game_dir)]
    return "\n".join(lines)
