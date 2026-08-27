"""Windows display enumeration, used only when ``D3DEnum.txt`` is absent.

``D3DEnum.txt`` is preferred because it records what the *game* sees. This
module is the fallback for a first run, before the game has ever started.

Caveat worth knowing: Direct3D 8 adapter ordering is not guaranteed to match
``EnumDisplayDevices`` ordering. In practice both follow the desktop device
order, with the primary display first, but a config produced from this fallback
should be re-derived from ``D3DEnum.txt`` once the game has run once.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .d3denum import Adapter

ENUM_CURRENT_SETTINGS = -1
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class _POINTL(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPosition", _POINTL),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


def enumerate_adapters() -> list[Adapter]:
    """Enumerate attached displays and their modes, in desktop device order."""
    user32 = ctypes.windll.user32
    adapters: list[Adapter] = []
    index = 0
    device_number = 0

    while True:
        dev = DISPLAY_DEVICEW()
        dev.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not user32.EnumDisplayDevicesW(None, device_number, ctypes.byref(dev), 0):
            break
        device_number += 1
        if not dev.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            continue

        adapter = Adapter(index=index, description=dev.DeviceString, validated=True)
        index += 1

        mode_number = 0
        seen: set[tuple[int, int, int]] = set()
        while True:
            dm = DEVMODEW()
            dm.dmSize = ctypes.sizeof(DEVMODEW)
            if not user32.EnumDisplaySettingsW(dev.DeviceName, mode_number,
                                               ctypes.byref(dm)):
                break
            mode_number += 1
            entry = (int(dm.dmPelsWidth), int(dm.dmPelsHeight), int(dm.dmBitsPerPel))
            if entry not in seen:
                seen.add(entry)
                adapter.modes.append(entry)

        # Primary display sorts first, matching how D3D8 numbers adapters.
        adapters.append((0 if dev.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE else 1,
                         adapter))

    adapters.sort(key=lambda pair: pair[0])
    result = []
    for i, (_, adapter) in enumerate(adapters):
        adapter.index = i
        result.append(adapter)
    return result
