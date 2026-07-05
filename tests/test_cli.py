import json
import xml.etree.ElementTree as ET

import pytest
import trimesh

from printphys.cli import main, parse_mass_to_kg


@pytest.fixture
def stl(tmp_path):
    path = tmp_path / "cube.stl"
    trimesh.creation.box(extents=[10.0, 10.0, 10.0]).export(path)
    return str(path)


@pytest.mark.parametrize(
    ("text", "kg"),
    [("42.1g", 0.0421), ("42.1", 0.0421), ("0.0421kg", 0.0421), ("500mg", 0.0005)],
)
def test_parse_mass(text, kg):
    assert parse_mass_to_kg(text) == pytest.approx(kg)


def test_parse_mass_rejects_garbage():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        parse_mass_to_kg("heavy")


def test_cli_urdf_output(stl, capsys):
    rc = main([stl, "--material", "pla", "--infill", "20", "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out
    el = ET.fromstring(out)
    assert el.tag == "inertial"
    assert float(el.find("mass").get("value")) > 0


def test_cli_json_report_with_weighed_mass(stl, capsys):
    rc = main(
        [stl, "--material", "petg", "--infill", "30", "--format", "json",
         "--weighed-mass", "1.5g", "--quiet"]
    )
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mass_properties"]["mass_kg"] == pytest.approx(1.5e-3)
    assert "estimate_error_percent" in report["validation"]
    assert report["backend"]["effective_density_g_cm3"] > 0


def test_cli_output_file(stl, tmp_path, capsys):
    out_file = tmp_path / "inertial.xml"
    rc = main([stl, "--format", "sdf", "-o", str(out_file), "--quiet"])
    assert rc == 0
    assert ET.fromstring(out_file.read_text()).tag == "inertial"


def test_cli_patch_urdf(stl, tmp_path):
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(
        '<robot name="r"><link name="part"/></robot>'
    )
    rc = main([stl, "--patch-urdf", str(urdf), "--link", "part", "--quiet", "-o",
               str(tmp_path / "sink.xml")])
    assert rc == 0
    root = ET.parse(urdf).getroot()
    assert root.find("link/inertial") is not None


def test_cli_unknown_material_is_clean_error(stl, capsys):
    rc = main([stl, "--material", "vibranium", "--quiet"])
    assert rc == 1
    assert "unknown material" in capsys.readouterr().err


def test_cli_requires_input():
    with pytest.raises(SystemExit):
        main(["--material", "pla"])
