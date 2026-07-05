import pytest

from printphys.materials import Material, available_materials, load_material


def test_bundled_materials_present():
    names = available_materials()
    for expected in ("pla", "petg", "abs", "asa", "tpu"):
        assert expected in names


def test_load_pla():
    pla = load_material("pla")
    assert pla.density_g_cm3 == pytest.approx(1.24)
    assert pla.density_kg_m3 == pytest.approx(1240.0)
    assert pla.density_g_mm3 == pytest.approx(0.00124)


def test_all_bundled_materials_load_and_validate():
    for name in available_materials():
        mat = load_material(name)
        assert mat.density_g_cm3 > 0
        assert mat.sources, f"{name} must cite a source"


def test_unknown_material_lists_options():
    with pytest.raises(ValueError, match="pla"):
        load_material("unobtainium")


def test_load_from_custom_yaml(tmp_path):
    f = tmp_path / "custom.yaml"
    f.write_text("density_g_cm3: 2.5\nname: custom\ndisplay_name: Custom\n")
    mat = load_material(f)
    assert mat.density_g_cm3 == pytest.approx(2.5)


def test_material_passthrough():
    mat = Material(name="x", display_name="X", density_g_cm3=1.0)
    assert load_material(mat) is mat


def test_unknown_field_rejected(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("density_g_cm3: 1.0\nvolume: 3\n")
    with pytest.raises(ValueError, match="unknown material fields"):
        load_material(f)
