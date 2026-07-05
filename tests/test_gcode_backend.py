"""The G-code backend against hand-computable toy G-code."""

import math

import numpy as np
import pytest

from printphys.backends.gcode import analyze_gcode
from printphys.materials import load_material

FILAMENT_D = 1.75
AREA = math.pi * (FILAMENT_D / 2) ** 2  # mm^2


def write(tmp_path, text):
    path = tmp_path / "part.gcode"
    path.write_text(text)
    return path


@pytest.fixture
def pla():
    return load_material("pla")


def test_single_segment_mass_and_com(tmp_path, pla):
    # One 100 mm line along X at y=0, z=0.2, extruding E=5 mm of filament.
    path = write(
        tmp_path,
        """
G21
G90
M82
G92 E0
G1 X0 Y0 Z0.2 F9000
G1 X100 Y0 E5
""",
    )
    props, meta = analyze_gcode(path, pla, filament_diameter_mm=FILAMENT_D)
    expected_mass = 5.0 * AREA * pla.density_g_mm3 * 1e-3  # kg
    assert props.mass == pytest.approx(expected_mass, rel=1e-9)
    np.testing.assert_allclose(props.com, [0.050, 0.0, 0.0002], atol=1e-12)
    # Rod of length 0.1 m: I about COM perpendicular to rod = m L^2 / 12.
    assert props.iyy == pytest.approx(expected_mass * 0.1**2 / 12, rel=1e-6)
    assert meta["num_extrusion_segments"] == 1
    assert meta["filament_used_mm"] == pytest.approx(5.0)


def test_relative_extrusion_m83(tmp_path, pla):
    path = write(
        tmp_path,
        """
G90
M83
G1 X0 Y0 Z0.2
G1 X10 E1
G1 X20 E1
""",
    )
    props, _ = analyze_gcode(path, pla)
    expected = 2.0 * AREA * pla.density_g_mm3 * 1e-3
    assert props.mass == pytest.approx(expected, rel=1e-9)
    np.testing.assert_allclose(props.com[0], 0.010, atol=1e-12)


def test_g92_reset_not_counted_as_extrusion(tmp_path, pla):
    path = write(
        tmp_path,
        """
G90
M82
G92 E0
G1 X0 Y0 Z0.2
G1 X10 E1
G92 E0
G1 X20 E1
""",
    )
    props, _ = analyze_gcode(path, pla)
    expected = 2.0 * AREA * pla.density_g_mm3 * 1e-3
    assert props.mass == pytest.approx(expected, rel=1e-9)


def test_retraction_ignored(tmp_path, pla):
    path = write(
        tmp_path,
        """
G90
M82
G92 E0
G1 X0 Y0 Z0.2
G1 X10 E1
G1 E0.5
G1 X20
G1 E1.0
G1 X30 E2.0
""",
    )
    props, _ = analyze_gcode(path, pla)
    # Deposited: 1.0 (first move) + 0.5 (unretract prime) + 1.0 (last move).
    expected = 2.5 * AREA * pla.density_g_mm3 * 1e-3
    assert props.mass == pytest.approx(expected, rel=1e-9)


def test_comments_and_unknown_commands_skipped(tmp_path, pla):
    path = write(
        tmp_path,
        """
; header comment
M104 S210
G90
M82
G92 E0
G1 X0 Y0 Z0.2 ; move to start
G1 X50 E2 ; extrude
M107
""",
    )
    props, _ = analyze_gcode(path, pla)
    expected = 2.0 * AREA * pla.density_g_mm3 * 1e-3
    assert props.mass == pytest.approx(expected, rel=1e-9)


def test_square_perimeter_symmetry(tmp_path, pla):
    # Symmetric 20x20 square perimeter: COM at its center, ixx == iyy.
    path = write(
        tmp_path,
        """
G90
M83
G1 X0 Y0 Z0.2
G1 X20 E1
G1 Y20 E1
G1 X0 E1
G1 Y0 E1
""",
    )
    props, _ = analyze_gcode(path, pla)
    np.testing.assert_allclose(props.com[:2], [0.010, 0.010], atol=1e-12)
    assert props.ixx == pytest.approx(props.iyy, rel=1e-9)
    assert props.is_physically_valid()


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        analyze_gcode("does_not_exist.gcode", load_material("pla"))
