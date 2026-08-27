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

# Verified running on patch 1.2: 1920x1080 exclusive fullscreen on adapter 1.
# This is the file as it ran, with an explicit ``Window 0``. default_config()
# omits the key instead; omission was verified fullscreen at 640x480 on 1.2
# (the OBSERVED file), so both halves are observed, the seven-line 1080p file
# itself is not.
VERIFIED_1080P = ("SysSetup api D3D\r\n"
                  "SysSetup device 1\r\n"
                  "SysSetup width 1920\r\n"
                  "SysSetup height 1080\r\n"
                  "SysSetup bitdepth 32\r\n"
                  "SysSetup texbitdepth 16\r\n"
                  "SysSetup music 1\r\n"
                  "SysSetup Window 0\r\n")

# Verified running on patch 1.2: 1280x720 in a window.
VERIFIED_WINDOWED = ("SysSetup api D3D\r\n"
                     "SysSetup device 1\r\n"
                     "SysSetup width 1280\r\n"
                     "SysSetup height 720\r\n"
                     "SysSetup bitdepth 32\r\n"
                     "SysSetup texbitdepth 16\r\n"
                     "SysSetup music 1\r\n"
                     "SysSetup Window 1\r\n")


def test_parses_observed_config():
    cfg = gameconfig.parse(OBSERVED)
    assert cfg["api"] == "D3D"
    assert cfg["device"] == "1"
    assert cfg["bitdepth"] == "32"
    assert cfg["music"] == "1"


def test_round_trips_byte_identically():
    assert gameconfig.parse(OBSERVED).render() == OBSERVED
    assert gameconfig.parse(VERIFIED_WINDOWED).render() == VERIFIED_WINDOWED


def test_uses_crlf_line_endings():
    rendered = gameconfig.default_config(1).render()
    assert "\r\n" in rendered
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


def test_default_config_is_the_observed_bytes():
    assert gameconfig.default_config(1).render() == OBSERVED


def test_verified_1080p_file_round_trips():
    assert gameconfig.parse(VERIFIED_1080P).render() == VERIFIED_1080P


def test_default_config_at_1080p_is_the_verified_file_minus_window_0():
    rendered = gameconfig.default_config(1, 1920, 1080).render()
    assert rendered == VERIFIED_1080P.replace("SysSetup Window 0\r\n", "")
    assert "Window" not in rendered


def test_default_config_windowed_matches_verified_file():
    cfg = gameconfig.default_config(1, 1280, 720, windowed=True)
    assert cfg.render() == VERIFIED_WINDOWED


def test_window_key_is_absent_unless_asked_for():
    """A stock config must not carry the 1.2-only key."""
    assert "Window" not in gameconfig.default_config(1, 1920, 1080).values
    assert "Window" not in gameconfig.default_config(1).render()


def test_window_key_is_spelt_as_patch_1_2_writes_it():
    """1.0 wrote ``windowed`` (ignored); 1.2 writes ``Window`` (honoured)."""
    rendered = gameconfig.default_config(0, windowed=True).render()
    assert "SysSetup Window 1\r\n" in rendered
    assert "windowed" not in rendered


def test_render_orders_known_keys_first():
    cfg = gameconfig.Config({"music": "1", "api": "D3D", "zzz": "9"})
    lines = cfg.render().rstrip().split("\r\n")
    assert lines[0] == "SysSetup api D3D"
    assert lines[1] == "SysSetup music 1"
    assert lines[-1] == "SysSetup zzz 9"


def test_render_places_window_after_the_1_0_keys():
    """The verified windowed file has Window last; keep writing it there."""
    cfg = gameconfig.Config({"Window": "1", "music": "1", "width": "640"})
    lines = cfg.render().rstrip().split("\r\n")
    assert lines == ["SysSetup width 640", "SysSetup music 1", "SysSetup Window 1"]


def test_values_with_spaces_survive():
    cfg = gameconfig.parse("SysSetup sound Some Device Name")
    assert cfg["sound"] == "Some Device Name"
