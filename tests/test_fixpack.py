import pytest

from mtrevival import fixpack

from test_d3denum import REAL


@pytest.fixture
def fake_game(tmp_path):
    """A stand-in install directory with mc.exe and the real D3DEnum.txt."""
    (tmp_path / "mc.exe").write_bytes(b"MZ not really")
    (tmp_path / "D3DEnum.txt").write_text(REAL)
    return tmp_path


def test_find_install_accepts_explicit_dir(fake_game):
    assert fixpack.find_install(fake_game) == fake_game


def test_find_install_rejects_dir_without_mc_exe(tmp_path):
    with pytest.raises(fixpack.FixError, match="Could not find mc.exe"):
        fixpack.find_install(tmp_path)


def test_plan_picks_the_landscape_adapter(fake_game):
    plan = fixpack.build_plan(fake_game)
    assert plan.adapter == 1
    assert plan.adapter_source == "D3DEnum.txt"
    assert plan.ok


def test_plan_writes_a_config_carrying_both_fixes(fake_game):
    plan = fixpack.build_plan(fake_game)
    assert "SysSetup device 1\r\n" in plan.rendered
    assert "SysSetup music 1\r\n" in plan.rendered


def test_apply_creates_config(fake_game):
    plan = fixpack.build_plan(fake_game)
    backup = fixpack.apply(plan)
    assert backup is None
    assert (fake_game / "config.cfg").read_bytes() == plan.rendered.encode()


def test_apply_backs_up_an_existing_config(fake_game):
    (fake_game / "config.cfg").write_bytes(b"SysSetup device 0\r\n")
    plan = fixpack.build_plan(fake_game)
    backup = fixpack.apply(plan)
    assert backup is not None and backup.is_file()
    assert backup.read_bytes() == b"SysSetup device 0\r\n"
    assert b"device 1" in (fake_game / "config.cfg").read_bytes()


def test_apply_refuses_when_no_adapter_fits(fake_game):
    portrait_only = REAL.split("Adapter #1")[0]
    (fake_game / "D3DEnum.txt").write_text(portrait_only)
    plan = fixpack.build_plan(fake_game)
    assert plan.adapter is None
    assert not plan.ok
    with pytest.raises(fixpack.FixError, match="No display adapter offers"):
        fixpack.apply(plan)


def test_apply_refuses_when_not_writable(fake_game, monkeypatch):
    plan = fixpack.build_plan(fake_game)
    object.__setattr__(plan, "writable", False)
    with pytest.raises(fixpack.FixError, match="not writable"):
        fixpack.apply(plan)


def test_describe_mentions_the_grant_command_when_unwritable(fake_game):
    plan = fixpack.build_plan(fake_game)
    object.__setattr__(plan, "writable", False)
    text = fixpack.describe(plan)
    assert "icacls" in text
    assert str(fake_game) in text


def test_describe_lists_the_config_lines(fake_game):
    text = fixpack.describe(fake_game and fixpack.build_plan(fake_game))
    assert "SysSetup device 1" in text
    assert "Adapter        : 1" in text
