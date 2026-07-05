# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""SDF (Gazebo) <inertial> export."""

from __future__ import annotations

from printphys.core import MassProperties


def _fmt(value: float, precision: int) -> str:
    return f"{value:.{precision}g}"


def inertial_xml(props: MassProperties, precision: int = 9, indent: str = "  ") -> str:
    """SDF <inertial> block. Pose places the inertial frame at the COM."""
    p = precision
    i = indent
    com = props.com
    return "\n".join(
        [
            "<inertial>",
            f"{i}<pose>{_fmt(com[0], p)} {_fmt(com[1], p)} {_fmt(com[2], p)} 0 0 0</pose>",
            f"{i}<mass>{_fmt(props.mass, p)}</mass>",
            f"{i}<inertia>",
            f"{i}{i}<ixx>{_fmt(props.ixx, p)}</ixx>",
            f"{i}{i}<ixy>{_fmt(props.ixy, p)}</ixy>",
            f"{i}{i}<ixz>{_fmt(props.ixz, p)}</ixz>",
            f"{i}{i}<iyy>{_fmt(props.iyy, p)}</iyy>",
            f"{i}{i}<iyz>{_fmt(props.iyz, p)}</iyz>",
            f"{i}{i}<izz>{_fmt(props.izz, p)}</izz>",
            f"{i}</inertia>",
            "</inertial>",
        ]
    )
