import argparse

import pytest

from mtrevival import __main__ as cli

from test_d3denum import REAL


@pytest.fixture
def fake_game(tmp_path):
    (tmp_path / "mc.exe").write_bytes(b"MZ not really")
    (tmp_path / "D3DEnum.txt").write_text(REAL)
    return tmp_path


def test_resolution_parses_wxh():
    assert cli.resolution("1920x1080") == (1920, 1080)
    assert cli.resolution(" 800X600 ") == (800, 600)


@pytest.mark.parametrize("bad", ["1920", "1920*1080", "x", "1920x", "1920x1080x32"])
def test_resolution_rejects_other_shapes(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.resolution(bad)


def test_check_defaults_to_640x480(fake_game, capsys):
    assert cli.main(["check", "--game-dir", str(fake_game)]) == 0
    out = capsys.readouterr().out
    assert "Resolution     : 640x480 fullscreen" in out
    assert "SysSetup width 640" in out
    assert not (fake_game / "config.cfg").exists()


def test_check_passes_resolution_and_windowed_through(fake_game, capsys):
    rc = cli.main(["check", "--game-dir", str(fake_game),
                   "--resolution", "800x600", "--windowed"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Resolution     : 800x600 windowed" in out
    assert "SysSetup width 800" in out
    assert "SysSetup Window 1" in out


def test_check_fails_for_an_unlisted_resolution(fake_game, capsys):
    rc = cli.main(["check", "--game-dir", str(fake_game), "--resolution", "1920x1080"])
    assert rc == 1
    assert "none supports 1920x1080" in capsys.readouterr().out


def test_fix_writes_the_requested_resolution(fake_game, capsys):
    rc = cli.main(["fix", "--game-dir", str(fake_game), "--resolution", "1024x768"])
    assert rc == 0
    written = (fake_game / "config.cfg").read_bytes()
    assert b"SysSetup width 1024\r\n" in written
    assert b"SysSetup height 768\r\n" in written
    assert b"SysSetup device 1\r\n" in written


def test_adapters_reports_fit_for_the_requested_resolution(fake_game, capsys):
    assert cli.main(["adapters", "--game-dir", str(fake_game), "--resolution", "800x600"]) == 0
    lines = {line.split()[1]: line for line in capsys.readouterr().out.splitlines()
             if line.strip().startswith("adapter ")}
    assert "no 800x600" in lines["0"] and "[portrait]" in lines["0"]
    assert "OK 800x600" in lines["1"] and "[portrait]" not in lines["1"]


def test_adapters_does_not_take_windowed(fake_game, capsys):
    with pytest.raises(SystemExit):
        cli.main(["adapters", "--game-dir", str(fake_game), "--windowed"])
    assert "unrecognized arguments: --windowed" in capsys.readouterr().err


def test_check_without_music_says_how_to_get_it(fake_game, capsys):
    assert cli.main(["check", "--game-dir", str(fake_game)]) == 0
    out = capsys.readouterr().out
    assert "Music          : off (music 1); add --music" in out
    assert "SysSetup music 1" in out


def _isolate_music(monkeypatch, shim, registered):
    from mtrevival import music
    monkeypatch.setattr(music, "bundled_shim", lambda: shim)
    monkeypatch.setattr(music, "reader_available", lambda: True)
    monkeypatch.setattr(music, "run_as_admin_flagged", lambda exe: False)
    monkeypatch.setattr(music, "is_elevated", lambda: False)
    monkeypatch.setattr(music, "register", lambda dll, classes=None: registered.append(dll))


def test_fix_with_music_installs_and_registers(fake_game, tmp_path, monkeypatch, capsys):
    from mtrevival import music
    shim = tmp_path / "package" / music.SHIM_NAME   # not the install path: copy must happen
    shim.parent.mkdir()
    shim.write_bytes(b"MZ shim")
    registered = []
    _isolate_music(monkeypatch, shim, registered)
    rc = cli.main(["fix", "--game-dir", str(fake_game), "--music"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert registered == [fake_game / music.SHIM_NAME]
    assert (fake_game / music.SHIM_NAME).read_bytes() == b"MZ shim"
    assert "registered it for this user" in out
    assert b"SysSetup music 0\r\n" in (fake_game / "config.cfg").read_bytes()


def test_check_with_music_exits_1_when_it_cannot_be_applied(fake_game, monkeypatch, capsys):
    _isolate_music(monkeypatch, None, [])
    assert cli.main(["check", "--game-dir", str(fake_game), "--music"]) == 1
    assert "PROBLEM" in capsys.readouterr().out


def test_adapters_does_not_take_music(fake_game, capsys):
    with pytest.raises(SystemExit):
        cli.main(["adapters", "--game-dir", str(fake_game), "--music"])
    assert "unrecognized arguments: --music" in capsys.readouterr().err


def test_missing_install_exits_2(tmp_path, capsys):
    assert cli.main(["check", "--game-dir", str(tmp_path)]) == 2
    assert "Could not find mc.exe" in capsys.readouterr().err
