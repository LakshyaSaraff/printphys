# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Analyze a part at several infill levels and compare against the solid-CAD answer.

Run: python basic_usage.py
"""

import trimesh

from printphys import PrintSettings, analyze

# A stand-in for your STL: a 40 x 20 x 10 mm bracket-ish box.
# Replace with: mesh = "path/to/part.stl"
mesh = trimesh.creation.box(extents=[40.0, 20.0, 10.0])

print(f"{'infill':>8} {'mass (g)':>10} {'ixx (kg m^2)':>14} {'vs solid':>9}")
solid_mass = None
for infill in (100, 60, 20, 0):
    result = analyze(
        mesh,
        settings=PrintSettings(infill_percent=infill, pattern="gyroid", wall_count=3),
        material="pla",
    )
    mass_g = result.props.mass * 1000
    if solid_mass is None:
        solid_mass = mass_g
    print(f"{infill:>7}% {mass_g:>10.2f} {result.props.ixx:>14.3e} {mass_g / solid_mass:>8.0%}")

# The URDF block for the realistic print:
result = analyze(
    mesh,
    settings=PrintSettings(infill_percent=20, pattern="gyroid", wall_count=3),
    material="pla",
)
print("\nURDF <inertial> for 20% gyroid:\n")
print(result.to_urdf())
print(
    f"\nEffective density: {result.meta['effective_density_g_cm3']:.3f} g/cm^3 "
    "(assign this in your CAD exporter to get matching numbers there)"
)
