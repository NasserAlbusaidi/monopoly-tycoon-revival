"""Read and write Monopoly Tycoon's ``config.cfg``.

The file is a list of console commands, one per line, CRLF-terminated::

    SysSetup api D3D
    SysSetup device 1
    SysSetup width 640

Verified by reading the game's process memory after it parsed a file written by
hand: the exact bytes appeared on the heap, and ``device`` changed which adapter
``CreateDevice`` targeted.

Not every key is honoured on every code path. ``device``, ``bitdepth 32`` and
``music`` were observed taking effect; ``windowed 1`` and ``bitdepth 16`` were
observed being ignored. Treat any key as unproven until you watch it work.
"""

from __future__ import annotations

from dataclasses import dataclass

# Key spellings exactly as the game's own format strings write them.
KEY_ORDER = ["api", "device", "width", "height", "bitdepth", "texbitdepth",
             "windowed", "Texdetail", "sound", "music", "shware", "avail"]

LINE_ENDING = "\r\n"
COMMAND = "SysSetup"


@dataclass
class Config:
    """The SysSetup settings, preserving the order they should be written in."""

    values: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.values[key]

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def set(self, key: str, value) -> None:
        self.values[key] = str(value)

    def render(self) -> str:
        """Serialise back to the game's format, CRLF-terminated."""
        known = [k for k in KEY_ORDER if k in self.values]
        extra = [k for k in self.values if k not in KEY_ORDER]
        lines = ["%s %s %s" % (COMMAND, k, self.values[k]) for k in known + extra]
        return LINE_ENDING.join(lines) + LINE_ENDING


def parse(text: str) -> Config:
    """Parse ``config.cfg`` text. Unrecognised lines are ignored."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        parts = raw.strip().split(None, 2)
        if len(parts) == 3 and parts[0].lower() == COMMAND.lower():
            values[parts[1]] = parts[2]
    return Config(values)


def default_config(device: int) -> Config:
    """The configuration verified to run the game on Windows 11.

    ``music 1`` suppresses the WMA playback path, which crashes because the
    Windows Media DirectShow source filter no longer ships with Windows.
    ``bitdepth 32`` matches the format the game actually selects; the 16-bit
    path asks for D3DFMT_R5G6B5, which modern drivers do not offer fullscreen.
    """
    return Config({
        "api": "D3D",
        "device": str(device),
        "width": "640",
        "height": "480",
        "bitdepth": "32",
        "texbitdepth": "16",
        "music": "1",
    })
