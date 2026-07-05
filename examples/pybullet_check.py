# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Verify printphys output inside PyBullet.

Builds a one-link URDF from the analyzed part and confirms PyBullet reports the
same mass and inertia. Requires: pip install pybullet

Run: python pybullet_check.py
"""

import tempfile
from pathlib import Path

import numpy as np
import trimesh

from printphys import PrintSettings, analyze

mesh = trimesh.creation.box(extents=[40.0, 20.0, 10.0])
result = analyze(
    mesh,
    settings=PrintSettings(infill_percent=20, pattern="gyroid", wall_count=3),
    material="pla",
)

workdir = Path(tempfile.mkdtemp(prefix="printphys_pybullet_"))
mesh_path = workdir / "part.obj"
mesh.apply_scale(0.001)  # URDF meshes are in meters
mesh.export(mesh_path)

urdf = f"""<?xml version="1.0"?>
<robot name="part">
  <link name="part">
    {result.to_urdf(indent="      ")}
    <visual><geometry><mesh filename="{mesh_path.name}"/></geometry></visual>
    <collision><geometry><mesh filename="{mesh_path.name}"/></geometry></collision>
  </link>
</robot>
"""
urdf_path = workdir / "part.urdf"
urdf_path.write_text(urdf)
print(f"wrote {urdf_path}")

try:
    import pybullet as p
except ImportError:
    raise SystemExit("pip install pybullet to run the simulation check") from None

client = p.connect(p.DIRECT)
body = p.loadURDF(str(urdf_path), flags=p.URDF_USE_INERTIA_FROM_FILE)
info = p.getDynamicsInfo(body, -1)
sim_mass, sim_diag = info[0], np.array(info[2])

print(f"printphys mass: {result.props.mass:.6f} kg | pybullet mass: {sim_mass:.6f} kg")
print(f"printphys principal moments: {result.props.principal_moments()}")
print(f"pybullet local inertia diag:  {sim_diag}")
assert abs(sim_mass - result.props.mass) / result.props.mass < 1e-6
assert np.allclose(np.sort(sim_diag), result.props.principal_moments(), rtol=1e-5)
print("OK: PyBullet is simulating with the printphys inertia.")
p.disconnect(client)
