"""Slicer CLI integration: detection and command construction (no real slicer
needed — subprocess calls are never made in these tests)."""

import pytest

from printphys.backends import gcode as g
from printphys.settings import PrintSettings


@pytest.fixture
def settings():
    return PrintSettings(
        infill_percent=15, pattern="grid", wall_count=3,
        line_width=0.42, layer_height=0.2, top_layers=5, bottom_layers=3,
    )


def test_family_classification():
    assert g._slicer_family(r"C:\x\prusa-slicer-console.exe") == "prusa"
    assert g._slicer_family("superslicer") == "prusa"
    assert g._slicer_family(r"D:\Bambu Studio\bambu-studio.exe") == "bambu"
    assert g._slicer_family("orca-slicer") == "bambu"


def test_env_var_wins(monkeypatch):
    monkeypatch.setenv("PRINTPHYS_SLICER", r"D:\somewhere\orca-slicer.exe")
    family, exe = g.find_slicer()
    assert family == "bambu"
    assert exe.endswith("orca-slicer.exe")


def test_prusa_command_flags(settings, tmp_path):
    cmd = g._prusa_slice_cmd("prusa-slicer-console", tmp_path / "p.stl", settings, tmp_path / "p.gcode")
    joined = " ".join(str(c) for c in cmd)
    assert "--fill-density 15%" in joined
    assert "--perimeters 3" in joined
    assert "--fill-pattern grid" in joined
    assert "--top-solid-layers 5" in joined


def test_prusa_pattern_mapping(tmp_path):
    s = PrintSettings(pattern="lines")
    cmd = g._prusa_slice_cmd("prusa-slicer", tmp_path / "p.stl", s, tmp_path / "p.gcode")
    assert cmd[cmd.index("--fill-pattern") + 1] == "line"


def test_bambu_override_preset(settings):
    preset = g._bambu_override_preset(settings, "0.20mm Standard @BBL A1", "Bambu Lab A1 0.4 nozzle")
    # The CLI rejects presets without type/name/from metadata, and a user
    # process preset must declare printer compatibility.
    assert preset["type"] == "process"
    assert preset["from"] == "User"
    assert preset["inherits"] == "0.20mm Standard @BBL A1"
    assert preset["compatible_printers"] == ["Bambu Lab A1 0.4 nozzle"]
    assert preset["wall_loops"] == "3"
    assert preset["sparse_infill_density"] == "15%"


def test_bambu_pattern_mapping():
    s = PrintSettings(pattern="rectilinear")
    preset = g._bambu_override_preset(s, "proc", "mach")
    assert preset["sparse_infill_pattern"] == "zig-zag"


def test_slice_mesh_missing_mesh(tmp_path):
    with pytest.raises(FileNotFoundError, match="mesh file not found"):
        g.slice_mesh(tmp_path / "nope.stl", PrintSettings())


def test_slice_mesh_no_slicer_message(tmp_path, monkeypatch):
    mesh = tmp_path / "part.stl"
    mesh.write_bytes(b"solid x\nendsolid x\n")
    monkeypatch.setattr(g, "find_slicer", lambda: None)
    with pytest.raises(FileNotFoundError, match="no slicer CLI found"):
        g.slice_mesh(mesh, PrintSettings())
