import pytest

from printphys.settings import PrintSettings


def test_defaults_are_valid():
    s = PrintSettings()
    assert s.infill_fraction == pytest.approx(0.2)
    assert s.wall_thickness == pytest.approx(0.8)
    assert s.top_thickness == pytest.approx(0.8)


def test_pattern_normalized_to_lowercase():
    assert PrintSettings(pattern="Gyroid").pattern == "gyroid"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"infill_percent": -1},
        {"infill_percent": 101},
        {"pattern": "spaghetti"},
        {"wall_count": -1},
        {"line_width": 0},
        {"layer_height": -0.2},
        {"top_layers": -1},
    ],
)
def test_invalid_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        PrintSettings(**kwargs)
