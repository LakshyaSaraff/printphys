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

import io
import json
import math
import os
import shutil
import string
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

from printphys.core import MassProperties, PointMassCloud
from printphys.materials import Material
from printphys.settings import PrintSettings


def _read_gcode_text(gcode_path: Path) -> str:
    """Read G-code text from a plain file or a ``.gcode.3mf`` archive.

    Bambu Studio / OrcaSlicer export sliced plates as ``.gcode.3mf``: a zip
    with the actual G-code under ``Metadata/plate_N.gcode``.
    """
    if gcode_path.suffix.lower() == ".3mf":
        with zipfile.ZipFile(gcode_path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".gcode")]
            if not names:
                raise ValueError(f"no .gcode member found inside {gcode_path}")
            if len(names) > 1:
                names.sort()
            return zf.read(names[0]).decode("utf-8", errors="replace")
    return gcode_path.read_text(encoding="utf-8", errors="replace")


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
    # Filament pulled back by retraction moves. The following un-retract only
    # restores it to the nozzle — nothing is deposited until the debt is repaid.
    # Without this, every retract/unretract pair double-counts its filament
    # (heavily retracted prints can read >20% too heavy).
    retract_debt_mm = 0.0
    retracted_mm = 0.0
    # Slicers label toolpath regions with feature comments ("; FEATURE: ..." in
    # Bambu/Orca, ";TYPE:..." in PrusaSlicer/Cura). Machine start/end sequences
    # (filament load, purge and calibration lines) are labeled "Custom"; that
    # filament never lands in the part — and it is deposited at the bed edge,
    # so for small parts it can dominate the inertia if counted. Skip it, and
    # report a per-feature mass breakdown so skirts/brims/supports are visible.
    feature = None
    feature_mm: dict = {}
    excluded_mm = 0.0

    with io.StringIO(_read_gcode_text(gcode_path)) as fh:
        for raw in fh:
            comment = raw.strip()
            if comment.startswith(";"):
                tag = comment.lstrip(";").strip()
                upper = tag.upper()
                if upper.startswith("FEATURE:") or upper.startswith("TYPE:"):
                    feature = tag.split(":", 1)[1].strip() or None
                continue
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
            if delta_e < 0:
                retract_debt_mm += -delta_e
                retracted_mm += -delta_e
            elif delta_e > 0:
                # Repay any outstanding retraction before depositing material.
                repaid = min(retract_debt_mm, delta_e)
                retract_debt_mm -= repaid
                deposited = delta_e - repaid
                if deposited > 0 and feature == "Custom":
                    # Machine start/end macros: filament load, purge lines,
                    # flow calibration. Extruded, but not part of the part.
                    excluded_mm += deposited
                elif deposited > 0:
                    mass_g = deposited * filament_area * density
                    if np.allclose(target, pos):
                        # Prime in place: deposit as a point mass.
                        cloud.add_points(np.array([mass_g * 1e-3]), (pos * 1e-3)[None, :])
                    else:
                        cloud.add_segment(mass_g * 1e-3, pos * 1e-3, target * 1e-3)
                        num_segments += 1
                    filament_mm += deposited
                    key = feature or "unlabeled"
                    feature_mm[key] = feature_mm.get(key, 0.0) + deposited
                    if is_arc:
                        num_arcs += 1
            pos = target
            e_pos = e_target

    props = cloud.finalize()
    to_g = filament_area * density
    meta = {
        "backend": "gcode",
        "file": str(gcode_path),
        "filament_diameter_mm": filament_diameter_mm,
        "filament_used_mm": round(filament_mm, 1),
        "filament_retracted_mm": round(retracted_mm, 1),
        "machine_startup_purge_excluded_g": round(excluded_mm * to_g, 3),
        "mass_by_feature_g": {
            k: round(v * to_g, 3) for k, v in sorted(feature_mm.items())
        },
        "num_extrusion_segments": num_segments,
        "num_arc_moves_approximated": num_arcs,
    }
    return props, meta


# ---------------------------------------------------------------------------
# Slicer CLI integration: slice an STL with whatever slicer the user has
# installed, then feed the result to the G-code backend.
#
# Two CLI families are supported:
#   - "prusa":  PrusaSlicer / SuperSlicer / Slic3r — settings passed as flags.
#   - "bambu":  Bambu Studio / OrcaSlicer — settings passed as preset JSONs;
#               output is a .gcode.3mf-style archive (analyze_gcode reads it).
# ---------------------------------------------------------------------------

_PRUSA_EXES = (
    "prusa-slicer-console",
    "prusa-slicer",
    "superslicer-console",
    "superslicer",
)
_BAMBU_EXES = ("bambu-studio", "bambustudio", "orca-slicer", "orcaslicer")

# Common Windows install locations, tried on every existing drive root and
# under Program Files. GUI installers rarely add these to PATH.
_WINDOWS_RELATIVE_CANDIDATES = (
    r"Prusa3D\PrusaSlicer\prusa-slicer-console.exe",
    r"PrusaSlicer\prusa-slicer-console.exe",
    r"SuperSlicer\superslicer-console.exe",
    r"Bambu Studio\bambu-studio.exe",
    r"BambuStudio\bambu-studio.exe",
    r"OrcaSlicer\orca-slicer.exe",
)

# printphys pattern names -> slicer enum values, where they differ.
_PRUSA_PATTERNS = {"lines": "line", "uniform": "grid"}
_BAMBU_PATTERNS = {"lines": "line", "rectilinear": "zig-zag", "uniform": "grid"}


def _slicer_family(executable: str | Path) -> str:
    name = Path(executable).name.lower()
    if "bambu" in name or "orca" in name:
        return "bambu"
    return "prusa"


def find_slicer() -> tuple[str, str] | None:
    """Locate an installed slicer CLI. Returns ``(family, executable)`` or None.

    Search order: the ``PRINTPHYS_SLICER`` environment variable, then PATH,
    then (on Windows) common install directories on all drives.
    """
    env = os.environ.get("PRINTPHYS_SLICER")
    if env:
        return (_slicer_family(env), env)
    for exe in _PRUSA_EXES + _BAMBU_EXES:
        found = shutil.which(exe)
        if found:
            return (_slicer_family(found), found)
    if sys.platform == "win32":
        roots = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        roots += [
            f"{letter}:\\" for letter in string.ascii_uppercase
            if os.path.exists(f"{letter}:\\")
        ]
        for root in roots:
            for rel in _WINDOWS_RELATIVE_CANDIDATES:
                candidate = os.path.join(root, rel)
                if os.path.isfile(candidate):
                    return (_slicer_family(candidate), candidate)
    return None


def _run_slicer(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise FileNotFoundError(f"slicer executable {cmd[0]!r} not found") from None
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or (proc.stdout or "").strip()[-2000:]
        raise RuntimeError(f"slicer failed (exit {proc.returncode}):\n{detail}")


def _prusa_slice_cmd(
    exe: str, mesh_path: Path, settings: PrintSettings, output_path: Path
) -> list[str]:
    pattern = _PRUSA_PATTERNS.get(settings.pattern, settings.pattern)
    return [
        exe,
        "--export-gcode",
        "--fill-density", f"{settings.infill_percent:g}%",
        "--fill-pattern", pattern,
        "--perimeters", str(settings.wall_count),
        "--layer-height", f"{settings.layer_height:g}",
        "--extrusion-width", f"{settings.line_width:g}",
        "--top-solid-layers", str(settings.top_layers),
        "--bottom-solid-layers", str(settings.bottom_layers),
        "--output", str(output_path),
        str(mesh_path),
    ]


# Default Bambu system presets used for slicing. Any 0.4 mm printer works for
# mass purposes; printphys settings override the mass-relevant fields below.
_BAMBU_MACHINE = "Bambu Lab A1 0.4 nozzle"
_BAMBU_PROCESS = "0.20mm Standard @BBL A1"
_BAMBU_FILAMENT = "Generic PLA @BBL A1"


def _bambu_override_preset(settings: PrintSettings, process_name: str, machine_name: str) -> dict:
    """A user process preset overriding the mass-relevant settings.

    Bambu/Orca CLIs reject bare key-value JSON: presets need type/name/from
    metadata, and a user preset must declare printer compatibility.
    """
    pattern = _BAMBU_PATTERNS.get(settings.pattern, settings.pattern)
    return {
        "type": "process",
        "name": "printphys-overrides",
        "from": "User",
        "inherits": process_name,
        "compatible_printers": [machine_name],
        "wall_loops": str(settings.wall_count),
        "sparse_infill_density": f"{settings.infill_percent:g}%",
        "sparse_infill_pattern": pattern,
        "layer_height": f"{settings.layer_height:g}",
        "top_shell_layers": str(settings.top_layers),
        "bottom_shell_layers": str(settings.bottom_layers),
        "line_width": f"{settings.line_width:g}",
    }


def _slice_bambu(exe: str, mesh_path: Path, settings: PrintSettings, workdir: Path) -> Path:
    profiles = Path(exe).parent / "resources" / "profiles" / "BBL"
    machine = profiles / "machine" / f"{_BAMBU_MACHINE}.json"
    process = profiles / "process" / f"{_BAMBU_PROCESS}.json"
    filament = profiles / "filament" / f"{_BAMBU_FILAMENT}.json"
    missing = [p for p in (machine, process, filament) if not p.is_file()]
    if missing:
        raise RuntimeError(
            f"Bambu/Orca system profiles not found next to {exe} "
            f"(looked for {missing[0]}); use a PrusaSlicer-family CLI instead "
            "or set PRINTPHYS_SLICER to a slicer with bundled BBL profiles"
        )
    # The override preset *replaces* the system process preset (inheriting it
    # by name) — the CLI rejects two process configs loaded side by side.
    override = workdir / "printphys_overrides.json"
    override.write_text(
        json.dumps(_bambu_override_preset(settings, _BAMBU_PROCESS, _BAMBU_MACHINE))
    )
    output = workdir / (mesh_path.stem + ".gcode.3mf")
    cmd = [
        exe,
        "--load-settings", f"{machine};{override}",
        "--load-filaments", str(filament),
        "--slice", "0",
        "--export-3mf", output.name,
        "--outputdir", str(workdir),
        str(mesh_path),
    ]
    _run_slicer(cmd)
    if not output.exists():
        raise RuntimeError(f"slicer reported success but {output} was not created")
    return output


def slice_mesh(
    mesh_path: str | Path,
    settings: PrintSettings,
    executable: str | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Slice a mesh with an installed slicer CLI and return the sliced file path.

    Auto-detects PrusaSlicer, SuperSlicer, Bambu Studio, or OrcaSlicer (see
    ``find_slicer``); pass ``executable`` to use a specific binary. The
    returned path is a ``.gcode`` (Prusa family) or ``.gcode.3mf``-style
    archive (Bambu family) — ``analyze_gcode`` accepts either.
    """
    mesh_path = Path(mesh_path).resolve()
    if not mesh_path.exists():
        raise FileNotFoundError(f"mesh file not found: {mesh_path}")

    if executable is not None:
        family, exe = _slicer_family(executable), executable
    else:
        detected = find_slicer()
        if detected is None:
            raise FileNotFoundError(
                "no slicer CLI found. Install PrusaSlicer (recommended), Bambu "
                "Studio, or OrcaSlicer, and either add its console binary to "
                "PATH, set the PRINTPHYS_SLICER environment variable, or pass "
                "--slicer-exe. See the README section 'Connecting a slicer CLI'."
            )
        family, exe = detected

    workdir = Path(tempfile.mkdtemp(prefix="printphys_"))
    if family == "bambu":
        result = _slice_bambu(exe, mesh_path, settings, workdir)
    else:
        result = Path(output_path) if output_path else workdir / (mesh_path.stem + ".gcode")
        _run_slicer(_prusa_slice_cmd(exe, mesh_path, settings, result))
        if not result.exists():
            raise RuntimeError(f"slicer reported success but {result} was not created")
    if output_path is not None and family == "bambu":
        output_path = Path(output_path)
        shutil.move(str(result), output_path)
        result = output_path
    return result
