"""Parser for Monopoly Tycoon's own ``D3DEnum.txt``.

The game writes this file when it enumerates Direct3D 8 adapters. It is the
authoritative record of what *the game* sees, which is what matters when
choosing an adapter index for ``config.cfg`` — it can differ from what Windows
reports, and a rotated display shows portrait modes here.

Example of the format::

    Number of display Adapters  :- 2

    Adapter #0
    nvldumd.dll
    NVIDIA GeForce RTX 4080
    Device Validated
    Available Video Modes = 522
    Vid Mode 480 X 640 X 32
    Valid Video Modes = 46
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ADAPTER = re.compile(r"^Adapter #(\d+)\s*$")
_MODE = re.compile(r"^Vid Mode\s+(\d+)\s+X\s+(\d+)\s+X\s+(\d+)\s*$")
_COUNT = re.compile(r"^Number of display Adapters\s*:-\s*(\d+)\s*$")


@dataclass
class Adapter:
    """One Direct3D 8 adapter as the game enumerated it."""

    index: int
    description: str = ""
    validated: bool = False
    modes: list[tuple[int, int, int]] = field(default_factory=list)

    def supports(self, width: int, height: int, bpp: int | None = None) -> bool:
        """True if this adapter offers the given mode."""
        for w, h, b in self.modes:
            if w == width and h == height and (bpp is None or b == bpp):
                return True
        return False

    @property
    def is_portrait(self) -> bool:
        """True if every mode is taller than it is wide (a rotated display)."""
        return bool(self.modes) and all(h > w for w, h, _ in self.modes)


def parse(text: str) -> list[Adapter]:
    """Parse the contents of ``D3DEnum.txt`` into a list of adapters."""
    adapters: list[Adapter] = []
    current: Adapter | None = None
    # A description is the first non-empty line after the DLL name line.
    lines_since_header = 0

    for raw in text.splitlines():
        line = raw.strip()

        m = _ADAPTER.match(line)
        if m:
            current = Adapter(index=int(m.group(1)))
            adapters.append(current)
            lines_since_header = 0
            continue

        if current is None:
            continue

        m = _MODE.match(line)
        if m:
            current.modes.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
            continue

        if line == "Device Validated":
            current.validated = True
            continue
        if line == "Device is Not Valid":
            current.validated = False
            continue

        if line:
            lines_since_header += 1
            # line 1 is the driver DLL, line 2 is the human-readable description
            if lines_since_header == 2 and not current.description:
                current.description = line

    return adapters


def declared_adapter_count(text: str) -> int | None:
    """The adapter count the game printed, or None if the line is absent."""
    for raw in text.splitlines():
        m = _COUNT.match(raw.strip())
        if m:
            return int(m.group(1))
    return None


def choose_adapter(adapters: list[Adapter], width: int, height: int,
                   bpp: int | None = None) -> int | None:
    """Pick the lowest-numbered validated adapter that supports the mode.

    Returns the adapter index for ``SysSetup device``, or None when no adapter
    offers the mode. Adapter 0 is preferred when it qualifies, because that is
    what the game uses by default and it keeps the config closest to stock.
    """
    for adapter in sorted(adapters, key=lambda a: a.index):
        if adapter.validated and adapter.supports(width, height, bpp):
            return adapter.index
    return None
