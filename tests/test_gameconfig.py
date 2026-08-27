from mtrevival import gameconfig

# The exact bytes recovered from the game's heap after it parsed a hand-written
# config.cfg, which is how the format was confirmed.
OBSERVED = ("SysSetup api D3D\r\n"
            "SysSetup device 1\r\n"
            "SysSetup width 640\r\n"
            "SysSetup height 480\r\n"
            "SysSetup bitdepth 32\r\n"
            "SysSetup texbitdepth 16\r\n"
            "SysSetup music 1\r\n")


def test_parses_observed_config():
    cfg = gameconfig.parse(OBSERVED)
    assert cfg["api"] == "D3D"
    assert cfg["device"] == "1"
    assert cfg["bitdepth"] == "32"
    assert cfg["music"] == "1"


def test_round_trips_byte_identically():
    assert gameconfig.parse(OBSERVED).render() == OBSERVED


def test_uses_crlf_line_endings():
    rendered = gameconfig.default_config(1).render()
    assert "\r\n" in rendered
    assert "\n\n" not in rendered.replace("\r\n", "\n\n\n")[:0] + ""
    for line in rendered.split("\r\n")[:-1]:
        assert not line.endswith("\r")
        assert line.startswith("SysSetup ")


def test_ignores_junk_and_blank_lines():
    cfg = gameconfig.parse("\n# a comment\nSysSetup device 2\nnonsense\n\n")
    assert cfg.values == {"device": "2"}


def test_command_matching_is_case_insensitive():
    assert gameconfig.parse("syssetup device 3")["device"] == "3"


def test_set_accepts_integers():
    cfg = gameconfig.default_config(0)
    cfg.set("device", 2)
    assert cfg["device"] == "2"
    assert "SysSetup device 2\r\n" in cfg.render()


def test_default_config_carries_both_fixes():
    """device selects a working adapter; music 1 suppresses the WMA crash."""
    cfg = gameconfig.default_config(1)
    assert cfg["device"] == "1"
    assert cfg["music"] == "1"
    assert cfg["bitdepth"] == "32"


def test_render_orders_known_keys_first():
    cfg = gameconfig.Config({"music": "1", "api": "D3D", "zzz": "9"})
    lines = cfg.render().rstrip().split("\r\n")
    assert lines[0] == "SysSetup api D3D"
    assert lines[1] == "SysSetup music 1"
    assert lines[-1] == "SysSetup zzz 9"


def test_values_with_spaces_survive():
    cfg = gameconfig.parse("SysSetup sound Some Device Name")
    assert cfg["sound"] == "Some Device Name"
