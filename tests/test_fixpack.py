import hashlib

import pytest

from mtrevival import fixpack, music

from test_d3denum import REAL

FAKE_EXE = b"MZ not really"
FAKE_SHIM = b"MZ shim"


@pytest.fixture
def music_env(tmp_path, monkeypatch):
    """Isolate every machine fact music.py reads: no real registry, no real DLL.

    Returns a dict the tests mutate to simulate the machine, plus the list
    of registrations that apply() performed.
    """
    shim = tmp_path / "package-bin" / music.SHIM_NAME
    shim.parent.mkdir()
    shim.write_bytes(FAKE_SHIM)
    env = {"shim": shim, "reader": True, "admin": False, "elevated": False,
           "registered": [], "register_error": None}

    def register(dll, classes=None):
        if env["register_error"]:
            raise env["register_error"]
        env["registered"].append(dll)

    monkeypatch.setattr(music, "bundled_shim", lambda: env["shim"])
    monkeypatch.setattr(music, "reader_available", lambda: env["reader"])
    monkeypatch.setattr(music, "run_as_admin_flagged", lambda exe: env["admin"])
    monkeypatch.setattr(music, "is_elevated", lambda: env["elevated"])
    monkeypatch.setattr(music, "register", register)
    return env


@pytest.fixture
def fake_game(tmp_path):
    """A stand-in install directory with mc.exe and the real D3DEnum.txt."""
    (tmp_path / "mc.exe").write_bytes(FAKE_EXE)
    (tmp_path / "D3DEnum.txt").write_text(REAL)
    return tmp_path


@pytest.fixture
def fake_game_1_2(fake_game, monkeypatch):
    """The same install, with mc.exe registered as the patch 1.2 build."""
    digest = hashlib.md5(FAKE_EXE).hexdigest()
    monkeypatch.setitem(fixpack.KNOWN_BUILDS, digest, "1.2")
    return fake_game


@pytest.fixture
def fake_game_1_0(fake_game, monkeypatch):
    """The same install, with mc.exe registered as the unpatched 1.0 build."""
    digest = hashlib.md5(FAKE_EXE).hexdigest()
    monkeypatch.setitem(fixpack.KNOWN_BUILDS, digest, "1.0")
    return fake_game


def test_find_install_accepts_explicit_dir(fake_game):
    assert fixpack.find_install(fake_game) == fake_game


def test_find_install_rejects_dir_without_mc_exe(tmp_path):
    with pytest.raises(fixpack.FixError, match="Could not find mc.exe"):
        fixpack.find_install(tmp_path)


def test_game_version_is_unknown_for_an_unrecognised_exe(fake_game):
    assert fixpack.game_version(fake_game) == "unknown"


def test_game_version_recognises_a_registered_build(fake_game_1_2):
    assert fixpack.game_version(fake_game_1_2) == "1.2"


def test_known_builds_carry_both_shipped_versions():
    assert set(fixpack.KNOWN_BUILDS.values()) == {"1.0", "1.2"}


def test_plan_picks_the_landscape_adapter(fake_game):
    plan = fixpack.build_plan(fake_game)
    assert plan.adapter == 1
    assert plan.adapter_source == "D3DEnum.txt"
    assert plan.ok


def test_plan_writes_a_config_carrying_both_fixes(fake_game):
    plan = fixpack.build_plan(fake_game)
    assert "SysSetup device 1\r\n" in plan.rendered
    assert "SysSetup music 1\r\n" in plan.rendered


def test_plan_defaults_to_640x480_fullscreen(fake_game):
    plan = fixpack.build_plan(fake_game)
    assert (plan.width, plan.height, plan.windowed) == (640, 480, False)
    assert "SysSetup width 640\r\n" in plan.rendered
    assert "SysSetup height 480\r\n" in plan.rendered
    assert "Window" not in plan.rendered


def test_plan_honours_a_requested_resolution(fake_game):
    plan = fixpack.build_plan(fake_game, 800, 600)
    assert plan.adapter == 1
    assert "SysSetup width 800\r\n" in plan.rendered
    assert "SysSetup height 600\r\n" in plan.rendered


def test_plan_refuses_a_resolution_no_adapter_lists(fake_game):
    """The fixture's adapter 1 tops out at 1024x768."""
    plan = fixpack.build_plan(fake_game, 1920, 1080)
    assert plan.adapter is None
    assert not plan.ok
    with pytest.raises(fixpack.FixError, match="No display adapter offers 1920x1080"):
        fixpack.apply(plan)


def test_plan_windowed_writes_the_window_key(fake_game_1_2):
    plan = fixpack.build_plan(fake_game_1_2, 1024, 768, windowed=True)
    assert plan.windowed
    assert plan.rendered.endswith("SysSetup music 1\r\nSysSetup Window 1\r\n")
    assert plan.warnings == []


def test_plan_windowed_on_1_0_warns_but_proceeds(fake_game_1_0):
    """1.0 was observed ignoring the key, so the warning may say so."""
    plan = fixpack.build_plan(fake_game_1_0, windowed=True)
    assert plan.game_version == "1.0"
    assert plan.ok
    assert "SysSetup Window 1\r\n" in plan.rendered
    assert len(plan.warnings) == 1
    assert "game version here is 1.0" in plan.warnings[0]
    assert "ignores the Window key" in plan.warnings[0]
    assert "WARNING" in fixpack.describe(plan)


def test_plan_windowed_on_unknown_build_warns_without_predicting(fake_game):
    """Nothing is observed about an unrecognised build; say only that."""
    plan = fixpack.build_plan(fake_game, windowed=True)
    assert plan.game_version == "unknown"
    assert plan.ok
    assert len(plan.warnings) == 1
    assert "not a build this tool recognises" in plan.warnings[0]
    assert "unproven" in plan.warnings[0]
    assert "ignores" not in plan.warnings[0]


@pytest.mark.parametrize("fixture", ["fake_game", "fake_game_1_0", "fake_game_1_2"])
def test_fullscreen_plans_never_warn(fixture, request):
    plan = fixpack.build_plan(request.getfixturevalue(fixture), 800, 600)
    assert plan.warnings == []
    assert "WARNING" not in fixpack.describe(plan)


def test_plan_without_music_keeps_music_1_and_touches_no_registry(fake_game, music_env):
    plan = fixpack.build_plan(fake_game)
    assert not plan.music
    assert "SysSetup music 1\r\n" in plan.rendered
    assert plan.music_problems == []
    fixpack.apply(plan)
    assert music_env["registered"] == []
    assert not (fake_game / music.SHIM_NAME).exists()
    assert "add --music" in fixpack.describe(plan)


def test_plan_with_music_writes_music_0_and_names_the_shim(fake_game, music_env):
    plan = fixpack.build_plan(fake_game, with_music=True)
    assert plan.music and plan.ok
    assert "SysSetup music 0\r\n" in plan.rendered
    assert plan.shim_source == music_env["shim"]
    assert plan.shim_target == fake_game / music.SHIM_NAME
    text = fixpack.describe(plan)
    assert "Music          : restore" in text
    assert str(plan.shim_target) in text


def test_apply_with_music_installs_the_shim_before_writing_config(fake_game, music_env):
    plan = fixpack.build_plan(fake_game, with_music=True)
    fixpack.apply(plan)
    assert (fake_game / music.SHIM_NAME).read_bytes() == FAKE_SHIM
    assert music_env["registered"] == [fake_game / music.SHIM_NAME]
    assert b"SysSetup music 0\r\n" in (fake_game / "config.cfg").read_bytes()


def test_apply_with_music_refreshes_a_stale_shim_copy(fake_game, music_env):
    (fake_game / music.SHIM_NAME).write_bytes(b"MZ old")
    fixpack.apply(fixpack.build_plan(fake_game, with_music=True))
    assert (fake_game / music.SHIM_NAME).read_bytes() == FAKE_SHIM


def test_music_refused_without_a_bundled_shim(fake_game, music_env):
    music_env["shim"] = None
    plan = fixpack.build_plan(fake_game, with_music=True)
    assert not plan.ok
    assert any("not bundled" in p for p in plan.music_problems)
    assert "PROBLEM" in fixpack.describe(plan)
    with pytest.raises(fixpack.FixError, match="not bundled"):
        fixpack.apply(plan)
    assert not (fake_game / "config.cfg").exists()
    assert music_env["registered"] == []


def test_music_refused_without_the_asf_reader(fake_game, music_env):
    music_env["reader"] = False
    plan = fixpack.build_plan(fake_game, with_music=True)
    assert not plan.ok
    assert any("Media Feature Pack" in p for p in plan.music_problems)
    with pytest.raises(fixpack.FixError, match="WM ASF Reader"):
        fixpack.apply(plan)
    assert not (fake_game / "config.cfg").exists()


def test_music_warns_when_the_game_runs_elevated(fake_game, music_env):
    music_env["admin"] = True
    plan = fixpack.build_plan(fake_game, with_music=True)
    assert plan.ok
    assert any("run as administrator" in w for w in plan.warnings)
    assert "WARNING" in fixpack.describe(plan)
    assert fixpack.build_plan(fake_game).warnings == []


def test_music_warns_when_the_tool_itself_is_elevated(fake_game, music_env):
    music_env["elevated"] = True
    plan = fixpack.build_plan(fake_game, with_music=True)
    assert plan.ok
    assert any("shell is elevated" in w for w in plan.warnings)
    assert fixpack.build_plan(fake_game).warnings == []


def test_registration_failure_is_a_fix_error_not_a_traceback(fake_game, music_env):
    music_env["register_error"] = PermissionError("access denied")
    with pytest.raises(fixpack.FixError, match="Could not register"):
        fixpack.apply(fixpack.build_plan(fake_game, with_music=True))
    assert not (fake_game / "config.cfg").exists()


def test_relative_game_dir_registers_an_absolute_path(fake_game, music_env, monkeypatch):
    """The registry path must not depend on where the shell happened to be."""
    monkeypatch.chdir(fake_game.parent)
    relative = fixpack.find_install(pytest.importorskip("pathlib").Path(fake_game.name))
    assert relative.is_absolute()
    plan = fixpack.build_plan(relative, with_music=True)
    fixpack.apply(plan)
    assert music_env["registered"] == [fake_game / music.SHIM_NAME]
    assert music_env["registered"][0].is_absolute()


def test_music_problems_leave_config_untouched_when_it_exists(fake_game, music_env):
    (fake_game / "config.cfg").write_bytes(b"SysSetup music 1\r\n")
    music_env["reader"] = False
    with pytest.raises(fixpack.FixError):
        fixpack.apply(fixpack.build_plan(fake_game, with_music=True))
    assert (fake_game / "config.cfg").read_bytes() == b"SysSetup music 1\r\n"


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


def test_apply_refuses_when_not_writable(fake_game):
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
    text = fixpack.describe(fixpack.build_plan(fake_game))
    assert "SysSetup device 1" in text
    assert "Adapter        : 1" in text
    assert "Game version   : unknown" in text
    assert "Resolution     : 640x480 fullscreen" in text


def test_describe_shows_windowed_resolution(fake_game_1_2):
    text = fixpack.describe(fixpack.build_plan(fake_game_1_2, 800, 600, windowed=True))
    assert "Resolution     : 800x600 windowed" in text
    assert "Game version   : 1.2" in text
