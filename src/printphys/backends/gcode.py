# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""G-code backend: ground-truth mass properties from actual extrusion paths.

Every extrusion move deposits a known volume of filament
(``delta_E * filament cross-section area``). Each move is integrated as a
uniform line segment of mass — exact first and second moments — so the result
captures walls, skins, infill pattern, supports, and brims exactly as they
will be printed. Segment cross-section self-inertia (~line_width^2) is
negligible at part scale and is not modeled.

Supported dialect: RepRap-flavor G-code as emitted by PrusaSlicer, Cura,
Bambu Studio, and OrcaSlicer (G0/G1 moves, G90/G91, M82/M83, G92, G20/G21).
Arc moves (G2/G3) are approximated by straight chords and counted in the
metadata so users can judge the impact.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from printphys.core import MassProperties, PointMassCloud
from printphys.materials import Material
from printphys.settings import PrintSettings


def analyze_gcode(
    gcode_path: str | Path,
    material: Material,
    filament_diameter_mm: float = 1.75,
) -> tuple[MassProperties, dict]:
    """Integrate mass properties from a G-code file. Returns SI units."""
    gcode_path = Path(gcode_path)
    if not gcode_path.exists():
        raise FileNotFoundError(f"G-code file not found: {gcode_path}")

    filament_area = math.pi * (filament_diameter_mm / 2.0) ** 2  # mm^2
    density = material.density_g_mm3  # g/mm^3

    cloud = PointMassCloud()
    pos = np.zeros(3)  # mm, absolute
    e_pos = 0.0
    absolute_xyz = True
    absolute_e = True
    unit_scale = 1.0  # G21 mm default; G20 switches to inches
    num_segments = 0
    num_arcs = 0
    filament_mm = 0.0

    with open(gcode_path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue
            words = line.split()
            cmd = words[0].upper()

            if cmd in ("G90",):
                absolute_xyz = True
                absolute_e = True  # G90 also affects E unless M83 follows
                continue
            if cmd in ("G91",):
                absolute_xyz = False
                absolute_e = False
                continue
            if cmd == "M82":
                absolute_e = True
                continue
            if cmd == "M83":
                absolute_e = False
                continue
            if cmd == "G20":
                unit_scale = 25.4
                continue
            if cmd == "G21":
                unit_scale = 1.0
                continue
            if cmd == "G92":
                for w in words[1:]:
                    axis, value = w[0].upper(), w[1:]
                    if axis == "E":
                        e_pos = float(value) * unit_scale
                    elif axis in "XYZ":
                        pos["XYZ".index(axis)] = float(value) * unit_scale
                continue
            if cmd not in ("G0", "G1", "G2", "G3"):
                continue

            is_arc = cmd in ("G2", "G3")
            target = pos.copy()
            e_target = e_pos
            for w in words[1:]:
                axis, rest = w[0].upper(), w[1:]
                if axis not in "XYZE" or not rest:
                    continue
                try:
                    value = float(rest) * unit_scale
                except ValueError:
                    continue
                if axis == "E":
                    e_target = value if absolute_e else e_pos + value
                else:
                    i = "XYZ".index(axis)
                    target[i] = value if absolute_xyz else pos[i] + value

            delta_e = e_target - e_pos
            if delta_e > 0:
                mass_g = delta_e * filament_area * density
                if np.allclose(target, pos):
                    # Prime/unretract in place: deposit as a point mass.
                    cloud.add_points(np.array([mass_g * 1e-3]), (pos * 1e-3)[None, :])
                else:
                    cloud.add_segment(mass_g * 1e-3, pos * 1e-3, target * 1e-3)
                    num_segments += 1
                filament_mm += delta_e
                if is_arc:
                    num_arcs += 1
            pos = target
            e_pos = e_target

    props = cloud.finalize()
    meta = {
        "backend": "gcode",
        "file": str(gcode_path),
        "filament_diameter_mm": filament_diameter_mm,
        "filament_used_mm": round(filament_mm, 1),
        "num_extrusion_segments": num_segments,
        "num_arc_moves_approximated": num_arcs,
    }
    return props, meta


def slice_mesh(
    mesh_path: str | Path,
    settings: PrintSettings,
    slicer: str = "prusaslicer",
    executable: str | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Slice a mesh with an external slicer CLI and return the G-code path.

    Requires PrusaSlicer (or a compatible fork like OrcaSlicer/BambuStudio in
    PrusaSlicer CLI mode) on PATH or given via ``executable``.
    """
    mesh_path = Path(mesh_path)
    if output_path is None:
        output_path = Path(tempfile.mkdtemp(prefix="printphys_")) / (mesh_path.stem + ".gcode")
    output_path = Path(output_path)

    if slicer != "prusaslicer":
        raise ValueError(f"unsupported slicer {slicer!r}; only 'prusaslicer' is wired up so far")
    exe = executable or "prusa-slicer-console"
    cmd = [
        exe,
        "--export-gcode",
        "--fill-density", f"{settings.infill_percent:g}%",
        "--fill-pattern", settings.pattern,
        "--perimeters", str(settings.wall_count),
        "--layer-height", f"{settings.layer_height:g}",
        "--extrusion-width", f"{settings.line_width:g}",
        "--top-solid-layers", str(settings.top_layers),
        "--bottom-solid-layers", str(settings.bottom_layers),
        "--output", str(output_path),
        str(mesh_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"slicer executable {exe!r} not found; install PrusaSlicer and ensure "
            "its console binary is on PATH, or pass executable=..."
        ) from None
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"slicer failed:\n{exc.stderr}") from exc
    return output_path
