import pytest

from mtrevival import d3denum, fixpack, music, wizard

from test_d3denum import REAL


class Script:
    """Scripted answers for ask(); collects everything said."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []
        self.output = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError("wizard asked more than scripted: %r" % prompt)
        return self.answers.pop(0)

    def say(self, text):
        self.output.append(text)

    @property
    def text(self):
        return "\n".join(self.output)


@pytest.fixture
def fake_game(tmp_path):
    (tmp_path / "mc.exe").write_bytes(b"MZ not really")
    (tmp_path / "D3DEnum.txt").write_text(REAL)
    return tmp_path


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Every machine fact the wizard touches, controllable per test."""
    shim = tmp_path / "pkg" / music.SHIM_NAME
    shim.parent.mkdir()
    shim.write_bytes(b"MZ shim")
    env = {"desktop": (1024, 768), "reader": True, "writable": True,
           "granted": [], "registered": [], "shim": shim}
    monkeypatch.setattr(wizard, "current_desktop_mode", lambda: env["desktop"])
    monkeypatch.setattr(wizard, "grant_access", lambda d: env["granted"].append(d) or env["writable"])
    monkeypatch.setattr(fixpack, "is_writable", lambda d: env["writable"])
    monkeypatch.setattr(music, "reader_available", lambda: env["reader"])
    monkeypatch.setattr(music, "bundled_shim", lambda: env["shim"])
    monkeypatch.setattr(music, "run_as_admin_flagged", lambda exe: False)
    monkeypatch.setattr(music, "is_elevated", lambda: False)
    monkeypatch.setattr(music, "register", lambda dll, classes=None: env["registered"].append(dll))
    return env


def test_defaults_apply_the_verified_choices(fake_game, machine):
    # The REAL fixture's adapter 1 tops out at 1024x768: no 1920x1080, so the
    # (landscape) desktop mode 1024x768 leads and 640x480 follows.
    s = Script("", "", "")          # resolution -> first, music -> yes, apply -> yes
    assert wizard.run(s.ask, s.say, fake_game) == 0
    written = (fake_game / "config.cfg").read_bytes()
    assert b"SysSetup width 1024\r\n" in written
    assert b"SysSetup device 1\r\n" in written
    assert b"SysSetup music 0\r\n" in written
    assert machine["registered"] == [fake_game / music.SHIM_NAME]
    assert "Done. Wrote" in s.text
    assert "as administrator" in s.text


def _adapter(*modes):
    return d3denum.Adapter(0, validated=True, modes=[(w, h, 32) for w, h in modes])


def test_choices_prefer_the_verified_1080p_then_desktop_then_original():
    adapters = [_adapter((640, 480), (1920, 1080), (2560, 1440))]
    labels = [label for label, _ in wizard.resolution_choices(adapters, (2560, 1440))]
    assert labels[0].startswith("1920x1080") and "recommended" in labels[0]
    assert labels[1].startswith("2560x1440") and "not verified" in labels[1]
    assert labels[2].startswith("640x480")
    assert len(labels) == 3


def test_choices_skip_modes_no_adapter_lists_and_duplicates():
    assert [m for _, m in wizard.resolution_choices([_adapter((640, 480))], (640, 480))] == [(640, 480)]
    assert wizard.resolution_choices([_adapter((480, 640))], (480, 640)) == []


def test_choices_ignore_adapters_the_game_did_not_validate():
    unvalidated = d3denum.Adapter(0, validated=False, modes=[(1920, 1080, 32), (640, 480, 32)])
    assert wizard.resolution_choices([unvalidated], (1920, 1080)) == []


def test_a_portrait_desktop_is_never_offered_even_when_its_adapter_lists_it():
    """The REAL fixture: portrait primary at 1440x2560 (adapter 0) plus a landscape adapter."""
    adapters = d3denum.parse(REAL)
    modes = [m for _, m in wizard.resolution_choices(adapters, (1440, 2560))]
    assert (1440, 2560) not in modes
    assert all(w > h for w, h in modes)
    assert (640, 480) in modes


def test_portrait_only_setup_stops_with_advice(fake_game, machine):
    (fake_game / "D3DEnum.txt").write_text(REAL.split("Adapter #1")[0])
    s = Script()
    assert wizard.run(s.ask, s.say, fake_game) == 1
    assert "rotate" in s.text.lower()
    assert not (fake_game / "config.cfg").exists()


def test_declining_music_writes_music_1(fake_game, machine):
    s = Script("", "n", "")
    assert wizard.run(s.ask, s.say, fake_game) == 0
    assert b"SysSetup music 1\r\n" in (fake_game / "config.cfg").read_bytes()
    assert machine["registered"] == []


def test_no_windows_media_means_no_music_question(fake_game, machine):
    machine["reader"] = False
    s = Script("", "")               # resolution, apply — no music prompt
    assert wizard.run(s.ask, s.say, fake_game) == 0
    assert "Media Feature Pack" in s.text
    assert b"SysSetup music 1\r\n" in (fake_game / "config.cfg").read_bytes()


def test_unwritable_folder_triggers_the_elevated_grant(fake_game, machine, monkeypatch):
    machine["writable"] = False

    def grant(d):
        machine["granted"].append(d)
        machine["writable"] = True
        return True

    monkeypatch.setattr(wizard, "grant_access", grant)
    s = Script("", "", "")
    assert wizard.run(s.ask, s.say, fake_game) == 0
    assert machine["granted"] == [fake_game]
    assert "Windows will ask you to allow it" in s.text


def test_declined_uac_prints_the_manual_command(fake_game, machine):
    machine["writable"] = False
    s = Script()
    assert wizard.run(s.ask, s.say, fake_game) == 1
    assert "icacls" in s.text


def test_menu_rejects_nonsense_then_accepts_a_number(fake_game, machine):
    s = Script("9", "x", "2", "", "")
    assert wizard.run(s.ask, s.say, fake_game) == 0
    assert s.text.count("Type a number") == 2
    assert b"SysSetup width 640\r\n" in (fake_game / "config.cfg").read_bytes()


def test_apply_can_be_declined(fake_game, machine):
    s = Script("", "", "n")
    assert wizard.run(s.ask, s.say, fake_game) == 0
    assert not (fake_game / "config.cfg").exists()
    assert "Nothing changed" in s.text


def test_missing_install_asks_for_the_folder(tmp_path, fake_game, machine, monkeypatch):
    monkeypatch.setattr(fixpack, "DEFAULT_INSTALL", tmp_path / "nowhere")
    monkeypatch.setattr(fixpack, "find_install",
                        lambda explicit=None: _find(explicit))

    def _find(explicit):
        if explicit is None or not (explicit / "mc.exe").is_file():
            raise fixpack.FixError("Could not find mc.exe")
        return explicit.resolve()

    s = Script(str(tmp_path / "wrong"), '"%s"' % fake_game, "", "", "")
    assert wizard.run(s.ask, s.say, None) == 0
    assert (fake_game / "config.cfg").exists()


def test_missing_install_blank_answer_quits(tmp_path, machine, monkeypatch):
    monkeypatch.setattr(fixpack, "find_install",
                        lambda explicit=None: (_ for _ in ()).throw(fixpack.FixError("no")))
    s = Script("")
    assert wizard.run(s.ask, s.say, None) == 2
    assert "Install it from your CD first" in s.text


def test_bare_invocation_routes_to_the_wizard(monkeypatch):
    from mtrevival import __main__ as cli
    called = []
    monkeypatch.setattr(wizard, "main_interactive", lambda: called.append(True) or 0)
    assert cli.main([]) == 0
    assert called == [True]


def test_wizard_subcommand_passes_game_dir(fake_game, monkeypatch):
    from mtrevival import __main__ as cli
    seen = []
    monkeypatch.setattr(wizard, "run", lambda game_dir=None, **kw: seen.append(game_dir) or 0)
    assert cli.main(["wizard", "--game-dir", str(fake_game)]) == 0
    assert seen == [fake_game]
