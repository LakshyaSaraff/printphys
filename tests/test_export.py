import xml.etree.ElementTree as ET

import numpy as np
import pytest

from printphys.core import MassProperties
from printphys.export.mjcf import inertial_xml as mjcf_inertial
from printphys.export.sdf import inertial_xml as sdf_inertial
from printphys.export.urdf import inertial_xml as urdf_inertial
from printphys.export.urdf import patch_urdf


@pytest.fixture
def props():
    return MassProperties(
        mass=0.042,
        com=np.array([0.01, 0.02, 0.03]),
        inertia=np.array(
            [
                [1.9e-5, -1e-7, 2e-7],
                [-1e-7, 2.3e-5, -3e-7],
                [2e-7, -3e-7, 1.1e-5],
            ]
        ),
    )


def test_urdf_snippet_is_valid_xml(props):
    el = ET.fromstring(urdf_inertial(props))
    assert el.tag == "inertial"
    assert float(el.find("mass").get("value")) == pytest.approx(0.042)
    inertia = el.find("inertia")
    assert float(inertia.get("ixx")) == pytest.approx(1.9e-5)
    assert float(inertia.get("iyz")) == pytest.approx(-3e-7)
    xyz = [float(v) for v in el.find("origin").get("xyz").split()]
    np.testing.assert_allclose(xyz, [0.01, 0.02, 0.03])


def test_sdf_snippet_is_valid_xml(props):
    el = ET.fromstring(sdf_inertial(props))
    assert el.tag == "inertial"
    assert float(el.find("mass").text) == pytest.approx(0.042)
    assert float(el.find("inertia/izz").text) == pytest.approx(1.1e-5)


def test_mjcf_snippet_is_valid_xml(props):
    el = ET.fromstring(mjcf_inertial(props))
    assert el.tag == "inertial"
    full = [float(v) for v in el.get("fullinertia").split()]
    # MuJoCo order: ixx iyy izz ixy ixz iyz
    np.testing.assert_allclose(full, [1.9e-5, 2.3e-5, 1.1e-5, -1e-7, 2e-7, -3e-7])


MINI_URDF = """<?xml version="1.0"?>
<robot name="bot">
  <link name="base"/>
  <link name="arm">
    <inertial>
      <origin xyz="0 0 0" rpy="0 0 0"/>
      <mass value="99"/>
      <inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/>
    </inertial>
    <visual><geometry><box size="0.1 0.1 0.1"/></geometry></visual>
  </link>
</robot>
"""


def test_patch_urdf_replaces_inertial(tmp_path, props):
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(MINI_URDF)
    patch_urdf(urdf, "arm", props)

    root = ET.parse(urdf).getroot()
    arm = next(link for link in root.iter("link") if link.get("name") == "arm")
    inertials = arm.findall("inertial")
    assert len(inertials) == 1
    assert float(inertials[0].find("mass").get("value")) == pytest.approx(0.042)
    # Other content untouched.
    assert arm.find("visual") is not None


def test_patch_urdf_inserts_when_missing(tmp_path, props):
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(MINI_URDF)
    patch_urdf(urdf, "base", props, output_path=tmp_path / "out.urdf")

    root = ET.parse(tmp_path / "out.urdf").getroot()
    base = next(link for link in root.iter("link") if link.get("name") == "base")
    assert base.find("inertial") is not None


def test_patch_urdf_unknown_link(tmp_path, props):
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(MINI_URDF)
    with pytest.raises(ValueError, match="'leg' not found"):
        patch_urdf(urdf, "leg", props)


# "Billion laughs" entity-expansion payload: parsing this with the stdlib XML
# parser would balloon into gigabytes of memory. patch_urdf must refuse it.
MALICIOUS_URDF = """<?xml version="1.0"?>
<!DOCTYPE robot [
  <!ENTITY a "aaaaaaaaaa">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<robot name="&c;">
  <link name="arm"/>
</robot>
"""


def test_patch_urdf_rejects_entity_expansion(tmp_path, props):
    urdf = tmp_path / "evil.urdf"
    urdf.write_text(MALICIOUS_URDF)
    with pytest.raises(ValueError, match="denial-of-service"):
        patch_urdf(urdf, "arm", props)
