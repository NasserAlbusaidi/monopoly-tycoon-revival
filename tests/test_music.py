import uuid

import pytest

from mtrevival import music

winreg = pytest.importorskip("winreg")


@pytest.fixture
def scratch_classes():
    """A throwaway Classes root under HKCU so tests never touch real COM keys."""
    root = r"Software\mtrevival-test\%s" % uuid.uuid4()
    yield root
    access = winreg.KEY_WRITE | winreg.KEY_WOW64_32KEY
    for subkey in (r"%s\CLSID\%s\InprocServer32" % (root, music.LEGACY_CLSID),
                   r"%s\CLSID\%s" % (root, music.LEGACY_CLSID),
                   root + r"\CLSID", root, r"Software\mtrevival-test"):
        try:
            winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, subkey, access, 0)
        except OSError:
            pass


def test_register_then_unregister_round_trips(scratch_classes, tmp_path):
    dll = tmp_path / music.SHIM_NAME
    assert music.registered_server(scratch_classes) is None
    music.register(dll, scratch_classes)
    assert music.registered_server(scratch_classes) == str(dll)
    assert music.unregister(scratch_classes)
    assert music.registered_server(scratch_classes) is None
    assert not music.unregister(scratch_classes)


def test_register_writes_the_threading_model(scratch_classes, tmp_path):
    music.register(tmp_path / music.SHIM_NAME, scratch_classes)
    subkey = r"%s\CLSID\%s\InprocServer32" % (scratch_classes, music.LEGACY_CLSID)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as key:
        assert winreg.QueryValueEx(key, "ThreadingModel")[0] == "Both"
    music.unregister(scratch_classes)


def test_registration_asks_for_the_32_bit_view(scratch_classes, tmp_path, monkeypatch):
    """The game is 32-bit; a 64-bit-view registration would be invisible to it.

    WOW64 only redirects the real ``Software\\Classes\\CLSID`` tree, so the
    scratch root cannot show two views; assert the flag every key is opened
    with instead.
    """
    seen = []
    real_create = winreg.CreateKeyEx

    def spy(key, sub_key, reserved=0, access=winreg.KEY_WRITE):
        seen.append(access)
        return real_create(key, sub_key, reserved, access)

    monkeypatch.setattr(winreg, "CreateKeyEx", spy)
    music.register(tmp_path / music.SHIM_NAME, scratch_classes)
    music.unregister(scratch_classes)
    assert len(seen) == 2
    assert all(access & winreg.KEY_WOW64_32KEY for access in seen)


def test_clsids_are_the_ones_the_game_and_windows_use():
    """Pinned from mc.exe's CoCreateInstance site and qasf.dll's registration."""
    assert music.LEGACY_CLSID == "{6B6D0800-9ADA-11D0-A520-00A0D10129C0}"
    assert music.ASF_READER_CLSID == "{187463A0-5BB7-11D3-ACBE-0080C75E246E}"


def test_bundled_shim_is_a_dll_when_present():
    shim = music.bundled_shim()
    if shim is None:
        pytest.skip("shim not built; run tools/wmsource-shim/build.ps1")
    assert shim.name == music.SHIM_NAME
    assert shim.read_bytes()[:2] == b"MZ"


def test_run_as_admin_flag_is_false_for_an_unknown_exe(tmp_path):
    assert music.run_as_admin_flagged(tmp_path / "nope.exe") is False
