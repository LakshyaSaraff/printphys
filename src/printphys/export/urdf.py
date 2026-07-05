# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""URDF export: emit an <inertial> block or patch a link in an existing URDF."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import parse as _safe_parse

from printphys.core import MassProperties


def _fmt(value: float, precision: int) -> str:
    return f"{value:.{precision}g}"


def inertial_xml(props: MassProperties, precision: int = 9, indent: str = "  ") -> str:
    """URDF <inertial> block for a link, ready to paste.

    The URDF convention: inertia is about the COM, in the frame set by
    <origin> — which matches how MassProperties stores it (COM-centered,
    mesh-frame axes), so rpy is zero.
    """
    p = precision
    com = props.com
    lines = [
        "<inertial>",
        f'{indent}<origin xyz="{_fmt(com[0], p)} {_fmt(com[1], p)} {_fmt(com[2], p)}"'
        ' rpy="0 0 0"/>',
        f'{indent}<mass value="{_fmt(props.mass, p)}"/>',
        f'{indent}<inertia ixx="{_fmt(props.ixx, p)}" ixy="{_fmt(props.ixy, p)}"'
        f' ixz="{_fmt(props.ixz, p)}" iyy="{_fmt(props.iyy, p)}"'
        f' iyz="{_fmt(props.iyz, p)}" izz="{_fmt(props.izz, p)}"/>',
        "</inertial>",
    ]
    return "\n".join(lines)


def _inertial_element(props: MassProperties, precision: int = 9) -> ET.Element:
    p = precision
    inertial = ET.Element("inertial")
    origin = ET.SubElement(inertial, "origin")
    origin.set("xyz", " ".join(_fmt(v, p) for v in props.com))
    origin.set("rpy", "0 0 0")
    mass = ET.SubElement(inertial, "mass")
    mass.set("value", _fmt(props.mass, p))
    inertia = ET.SubElement(inertial, "inertia")
    for key in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz"):
        inertia.set(key, _fmt(getattr(props, key), p))
    return inertial


def patch_urdf(
    urdf_path: str | Path,
    link_name: str,
    props: MassProperties,
    output_path: str | Path | None = None,
    precision: int = 9,
) -> Path:
    """Replace (or insert) the <inertial> element of a named link in a URDF file.

    Writes to ``output_path`` (defaults to overwriting the input) and returns
    the path written.
    """
    urdf_path = Path(urdf_path)
    # Parse with defusedxml: URDF files may come from untrusted sources, and the
    # stdlib XML parser is vulnerable to entity-expansion ("billion laughs") DoS.
    try:
        tree = _safe_parse(str(urdf_path))
    except DefusedXmlException as exc:
        raise ValueError(
            f"refusing to parse {urdf_path}: the file uses XML DTD/entity constructs "
            "that can be abused for denial-of-service attacks"
        ) from exc
    root = tree.getroot()

    link = None
    for candidate in root.iter("link"):
        if candidate.get("name") == link_name:
            link = candidate
            break
    if link is None:
        names = [c.get("name") for c in root.iter("link")]
        raise ValueError(f"link {link_name!r} not found in {urdf_path}; links: {names}")

    for existing in link.findall("inertial"):
        link.remove(existing)
    link.insert(0, _inertial_element(props, precision))

    try:
        ET.indent(tree)  # Python >= 3.9
    except AttributeError:
        pass
    out = Path(output_path) if output_path else urdf_path
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out
