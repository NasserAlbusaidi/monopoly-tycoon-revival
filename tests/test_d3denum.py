import pytest

from mtrevival import d3denum

# Trimmed from a real D3DEnum.txt written by the game on a machine with a
# portrait primary display. Adapter 0 lists only portrait modes and has no
# 640 X 480; adapter 1 does. This is the exact shape that crashed the game.
REAL = """ENUMERATING D3D DEVICES
***********************


Creating D3D8 Object

D3D8 Object Created

Number of display Adapters  :- 2

Adapter #0
nvldumd.dll
NVIDIA GeForce RTX 4080
Device Validated
Available Video Modes = 522
Vid Mode 1440 X 2560 X 32
Vid Mode 480 X 640 X 32
Vid Mode 600 X 800 X 32
Vid Mode 768 X 1024 X 32
Valid Video Modes = 46

Adapter #1
nvldumd.dll
NVIDIA GeForce RTX 4080
Device Validated
Available Video Modes = 154
Vid Mode 640 X 480 X 32
Vid Mode 800 X 600 X 32
Vid Mode 1024 X 768 X 32
Vid Mode 640 X 480 X 16
Valid Video Modes = 54
"""


def test_parses_both_adapters():
    adapters = d3denum.parse(REAL)
    assert [a.index for a in adapters] == [0, 1]
    assert all(a.description == "NVIDIA GeForce RTX 4080" for a in adapters)
    assert all(a.validated for a in adapters)


def test_parses_modes():
    adapters = d3denum.parse(REAL)
    assert (480, 640, 32) in adapters[0].modes
    assert (640, 480, 32) in adapters[1].modes
    assert len(adapters[0].modes) == 4
    assert len(adapters[1].modes) == 4


def test_declared_adapter_count():
    assert d3denum.declared_adapter_count(REAL) == 2
    assert d3denum.declared_adapter_count("no such line") is None


def test_adapter_zero_lacks_the_mode_the_game_wants():
    """The whole crash in one assertion."""
    adapters = d3denum.parse(REAL)
    assert not adapters[0].supports(640, 480)
    assert adapters[1].supports(640, 480)


def test_portrait_detection():
    adapters = d3denum.parse(REAL)
    assert adapters[0].is_portrait
    assert not adapters[1].is_portrait


def test_choose_adapter_skips_the_portrait_one():
    adapters = d3denum.parse(REAL)
    assert d3denum.choose_adapter(adapters, 640, 480, 32) == 1


def test_choose_adapter_prefers_adapter_zero_when_it_fits():
    adapters = d3denum.parse(REAL)
    adapters[0].modes.append((640, 480, 32))
    assert d3denum.choose_adapter(adapters, 640, 480, 32) == 0


def test_choose_adapter_returns_none_when_nothing_fits():
    adapters = d3denum.parse(REAL)
    assert d3denum.choose_adapter(adapters, 12345, 999, 32) is None


def test_choose_adapter_ignores_unvalidated_devices():
    adapters = d3denum.parse(REAL.replace("Device Validated", "Device is Not Valid"))
    assert d3denum.choose_adapter(adapters, 640, 480, 32) is None


def test_bpp_is_optional():
    adapters = d3denum.parse(REAL)
    assert adapters[1].supports(640, 480, 16)
    assert adapters[1].supports(640, 480, None)
    assert not adapters[1].supports(800, 600, 16)


def test_empty_input_yields_no_adapters():
    assert d3denum.parse("") == []
