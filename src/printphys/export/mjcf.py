# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""MJCF (MuJoCo) <inertial> export."""

from __future__ import annotations

from printphys.core import MassProperties


def _fmt(value: float, precision: int) -> str:
    return f"{value:.{precision}g}"


def inertial_xml(props: MassProperties, precision: int = 9) -> str:
    """MJCF <inertial> element using fullinertia (about COM, body frame axes).

    MuJoCo's fullinertia order is: ixx iyy izz ixy ixz iyz.
    """
    p = precision
    pos = " ".join(_fmt(v, p) for v in props.com)
    full = " ".join(
        _fmt(v, p)
        for v in (props.ixx, props.iyy, props.izz, props.ixy, props.ixz, props.iyz)
    )
    return f'<inertial pos="{pos}" mass="{_fmt(props.mass, p)}" fullinertia="{full}"/>'
