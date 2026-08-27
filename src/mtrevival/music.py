"""Restore the WMA soundtrack.

The game plays music through a DirectShow graph whose source filter is the
2001 "Windows Media Source Filter", CLSID ``{6B6D0800-...}`` from
``dxmasf.dll``. Modern Windows ships neither that class nor a registration
for it, so the game's ``CoCreateInstance`` fails and, with music enabled, the
game dereferences the null result. ``SysSetup music 1`` only avoids the path.

``wmsource-shim.dll`` (source in ``tools/wmsource-shim``) answers that CLSID
by aggregating the filter that replaced it, the WM ASF Reader, and adapting
the two things the game needs: a fresh reader per ``Load`` (the reader refuses
a second one) and ``FindPin(L"Stream 1")`` mapped onto the reader's output
pin. See ``docs/music.md``.

Registration is per user, in the 32-bit view of ``HKCU\\Software\\Classes``
(the game is a 32-bit process), so no elevation is needed and nothing outside
the user's profile changes. An elevated process ignores per-user COM classes,
so the game must not be run as administrator.
"""

from __future__ import annotations

from pathlib import Path

LEGACY_CLSID = "{6B6D0800-9ADA-11D0-A520-00A0D10129C0}"
ASF_READER_CLSID = "{187463A0-5BB7-11D3-ACBE-0080C75E246E}"
SHIM_NAME = "wmsource-shim.dll"
CLASSES = r"Software\Classes"
DESCRIPTION = "Windows Media Source Filter (mtrevival wmsource-shim)"
LAYERS = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"


def bundled_shim() -> Path | None:
    """The shim DLL shipped inside this package, or None if it was not built."""
    path = Path(__file__).with_name("bin") / SHIM_NAME
    return path if path.is_file() else None


def _winreg():
    try:
        import winreg
    except ImportError:  # not Windows
        return None
    return winreg


def _read_value(hive_name: str, subkey: str, name: str,
                view_32bit: bool = True) -> str | None:
    winreg = _winreg()
    if winreg is None:
        return None
    access = winreg.KEY_READ | (winreg.KEY_WOW64_32KEY if view_32bit
                                else winreg.KEY_WOW64_64KEY)
    try:
        with winreg.OpenKey(getattr(winreg, hive_name), subkey, 0, access) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value)


def reader_available() -> bool:
    """True if the WM ASF Reader is registered for 32-bit processes.

    It is part of Windows Media, which N editions lack until the Media
    Feature Pack is installed. Without it the shim cannot play anything.
    """
    subkey = r"%s\CLSID\%s\InprocServer32" % (CLASSES, ASF_READER_CLSID)
    return _read_value("HKEY_LOCAL_MACHINE", subkey, "") is not None


def registered_server(classes: str = CLASSES) -> str | None:
    """Path of the DLL currently registered for the legacy CLSID, per user."""
    subkey = r"%s\CLSID\%s\InprocServer32" % (classes, LEGACY_CLSID)
    return _read_value("HKEY_CURRENT_USER", subkey, "")


def register(dll: Path, classes: str = CLASSES) -> None:
    """Register ``dll`` as the in-process server for the legacy CLSID, per user."""
    winreg = _winreg()
    if winreg is None:
        raise OSError("COM registration needs Windows")
    access = winreg.KEY_WRITE | winreg.KEY_WOW64_32KEY
    clsid = r"%s\CLSID\%s" % (classes, LEGACY_CLSID)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, clsid, 0, access) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, DESCRIPTION)
        with winreg.CreateKeyEx(key, "InprocServer32", 0, access) as server:
            winreg.SetValueEx(server, "", 0, winreg.REG_SZ, str(dll))
            winreg.SetValueEx(server, "ThreadingModel", 0, winreg.REG_SZ, "Both")


def unregister(classes: str = CLASSES) -> bool:
    """Remove the per-user registration. Returns True if there was one.

    Only the two keys ``register`` creates are deleted. If something else
    added subkeys under the CLSID, that key is left in place rather than
    torn down blindly, and the InprocServer32 removal alone already unhooks
    the class.
    """
    winreg = _winreg()
    if winreg is None:
        return False
    access = winreg.KEY_WRITE | winreg.KEY_WOW64_32KEY
    clsid = r"%s\CLSID\%s" % (classes, LEGACY_CLSID)
    removed = False
    for subkey in (clsid + r"\InprocServer32", clsid):
        try:
            winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, subkey, access, 0)
            removed = True
        except FileNotFoundError:
            pass
        except PermissionError:  # key has other subkeys; leave it
            break
    return removed


def run_as_admin_flagged(exe: Path) -> bool:
    """True if Windows is set to run ``exe`` elevated (compatibility tab).

    Elevated processes do not see per-user COM registrations, so the shim
    would be invisible to the game and music would crash it again. The
    Layers key is read in the 64-bit view so a 32-bit Python sees the same
    machine-wide entry the shell wrote.
    """
    for hive in ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"):
        value = _read_value(hive, LAYERS, str(exe), view_32bit=False)
        if value and "RUNASADMIN" in value.upper():
            return True
    return False


def is_elevated() -> bool:
    """True if this process runs with an elevated token.

    Registration goes into the running account's HKCU. From a shell elevated
    as a different account it would land in the wrong hive.
    """
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False
