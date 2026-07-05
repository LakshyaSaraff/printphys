# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Voxel/shell backend: print-aware mass properties without running a slicer.

The mesh is voxelized on a regular grid. Each occupied voxel is classified:

- wall: within ``wall_count * line_width`` of the lateral surface (per-layer
  2D distance transform, matching how slicers offset perimeters),
- skin: within ``top_layers`` / ``bottom_layers`` of an up/down-facing surface
  (per-column run length, matching solid top/bottom layers),
- interior: everything else, printed at ``infill% * density``.

For gyroid/grid/lines patterns the interior density can follow the actual
pattern geometry instead of a uniform average; total mass is identical either
way (the pattern field is thresholded at the exact target volume fraction),
but COM and inertia pick up the pattern's spatial distribution.

At 100% infill every voxel is fully dense and the result converges to the
exact solid-body inertia (anchored by the test suite). Total occupied voxel
volume is rescaled to the exact mesh volume to remove surface-discretization
bias from the mass.
"""

from __future__ import annotations

import warnings

import numpy as np
import trimesh
from scipy import ndimage

from printphys.core import MassProperties, PointMassCloud, unit_scale_to_meters
from printphys.materials import Material
from printphys.settings import GEOMETRY_AWARE_PATTERNS, PrintSettings

DEFAULT_MAX_VOXELS_PER_AXIS = 192


def _choose_pitch(mesh: trimesh.Trimesh, settings: PrintSettings, max_per_axis: int) -> float:
    """Default pitch: layer height, coarsened if the part is large."""
    max_extent = float(mesh.extents.max())
    return max(settings.layer_height, max_extent / max_per_axis)


def _classify_solid(occ: np.ndarray, pitch: float, settings: PrintSettings) -> np.ndarray:
    """Boolean mask of voxels printed at full density (walls + top/bottom skin)."""
    solid = np.zeros_like(occ)

    # Lateral walls: per z-slice, distance (in-plane) to the nearest empty cell.
    if settings.wall_thickness > 0:
        n_wall = max(1, int(round(settings.wall_thickness / pitch)))
        for z in range(occ.shape[2]):
            sl = occ[:, :, z]
            if not sl.any():
                continue
            dist = ndimage.distance_transform_edt(sl)
            solid[:, :, z] |= sl & (dist <= n_wall)

    # Top/bottom skins: per xy-column, run length of occupied voxels up/down
    # to the nearest air voxel (grid boundary counts as air).
    nx, ny, nz = occ.shape
    if settings.top_thickness > 0:
        n_top = max(1, int(round(settings.top_thickness / pitch)))
        run = np.zeros((nx, ny), dtype=np.int32)
        for z in range(nz - 1, -1, -1):
            run = np.where(occ[:, :, z], run + 1, 0)
            solid[:, :, z] |= occ[:, :, z] & (run <= n_top)
    if settings.bottom_thickness > 0:
        n_bot = max(1, int(round(settings.bottom_thickness / pitch)))
        run = np.zeros((nx, ny), dtype=np.int32)
        for z in range(nz):
            run = np.where(occ[:, :, z], run + 1, 0)
            solid[:, :, z] |= occ[:, :, z] & (run <= n_bot)

    return solid


def _pattern_metric(points: np.ndarray, pattern: str, cell: float) -> np.ndarray:
    """Scalar field over interior voxel centers; *low* values are where plastic goes.

    Thresholding this metric at its q-th quantile selects exactly a fraction q
    of interior voxels, so total mass always matches infill% regardless of the
    pattern approximation quality.
    """
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    if pattern == "gyroid":
        k = 2.0 * np.pi / cell
        g = (
            np.sin(k * x) * np.cos(k * y)
            + np.sin(k * y) * np.cos(k * z)
            + np.sin(k * z) * np.cos(k * x)
        )
        return np.abs(g)  # plastic on the gyroid level-set sheet
    # Distance (in cell fractions) to the nearest lattice line.
    fx = np.abs(x / cell - np.round(x / cell))
    fy = np.abs(y / cell - np.round(y / cell))
    if pattern == "grid":
        return np.minimum(fx, fy)
    if pattern in ("lines", "rectilinear"):
        # Direction alternates every layer; approximate with layer z-parity.
        parity = np.round(z / cell).astype(int) % 2
        return np.where(parity == 0, fx, fy)
    raise ValueError(f"pattern {pattern!r} has no geometry model")


def _interior_density_field(
    points: np.ndarray,
    settings: PrintSettings,
    pitch: float,
    pattern_aware: bool,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    """Relative density (0..1, fraction of full material density) per interior voxel.

    ``weights`` are per-voxel volume-coverage factors; the field is normalized
    so the coverage-weighted mean density equals the infill fraction exactly,
    making total mass independent of the pattern model.
    """
    fill = settings.infill_fraction
    n = len(points)
    if n == 0 or fill <= 0.0:
        return np.zeros(n)
    if fill >= 1.0:
        return np.ones(n)
    if weights is None:
        weights = np.ones(n)

    use_pattern = pattern_aware and settings.pattern in GEOMETRY_AWARE_PATTERNS
    if use_pattern:
        # Approximate slicer line spacing; a grid splits material two ways.
        per_direction = 2.0 if settings.pattern == "grid" else 1.0
        cell = per_direction * settings.line_width / fill
        if settings.pattern == "gyroid":
            cell *= 2.0  # gyroid period spans two sheets per cell
        # If the pattern is finer than the voxel grid can resolve, a uniform
        # field is the more accurate model.
        if cell < 3.0 * pitch:
            use_pattern = False

    if not use_pattern:
        return np.full(n, fill)

    metric = _pattern_metric(points, settings.pattern, cell)
    threshold = np.quantile(metric, fill)
    density = (metric <= threshold).astype(float)
    # Quantile ties and coverage weighting can shift the total; renormalize so
    # the coverage-weighted interior mass matches the uniform model exactly.
    total = float((density * weights).sum())
    if total > 0:
        density *= fill * float(weights.sum()) / total
    return density


def analyze_voxel(
    mesh: trimesh.Trimesh,
    settings: PrintSettings,
    material: Material,
    units: str = "mm",
    pitch: float | None = None,
    pattern_aware: bool = True,
    max_voxels_per_axis: int = DEFAULT_MAX_VOXELS_PER_AXIS,
) -> tuple[MassProperties, dict]:
    """Compute mass properties of a printed part from its mesh and print settings.

    Args:
        mesh: the part geometry. Assumed to be in ``units`` (default mm).
        settings: print settings (infill, walls, layers...). Lengths in mm.
        material: filament material (provides density).
        units: units of the mesh coordinates: mm, cm, m, or in.
        pitch: voxel size in mm. Defaults to layer height, coarsened so no
            axis exceeds ``max_voxels_per_axis`` voxels.
        pattern_aware: model the infill pattern's geometry (gyroid/grid/lines)
            instead of a uniform interior density. Mass is identical either way.

    Returns:
        (MassProperties in SI units, metadata dict with diagnostics).
    """
    mesh = mesh.copy()
    to_mm = unit_scale_to_meters(units) * 1000.0
    if to_mm != 1.0:
        mesh.apply_scale(to_mm)

    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    watertight = mesh.is_watertight
    if not watertight:
        warnings.warn(
            "mesh is not watertight even after hole filling; volume-based "
            "corrections are disabled and results may be less accurate",
            stacklevel=2,
        )

    if pitch is None:
        pitch = _choose_pitch(mesh, settings, max_voxels_per_axis)

    surface_vg = mesh.voxelized(pitch)
    surface = np.asarray(surface_vg.matrix, dtype=bool).copy()
    vg = surface_vg.fill()
    occ = np.asarray(vg.matrix, dtype=bool).copy()
    if not occ.any():
        raise ValueError("voxelization produced an empty grid; check mesh and units")

    # Voxelization marks every voxel that *touches* the surface, dilating the
    # part by ~pitch/2 per side, which would inflate inertia by O(pitch/extent).
    # Surface voxels straddle the boundary, so on average half their volume is
    # inside the part: weight them at 0.5 coverage to cancel the dilation bias.
    coverage = np.where(surface & occ, 0.5, 1.0)

    solid = _classify_solid(occ, pitch, settings)
    interior = occ & ~solid

    # Relative density per occupied voxel (1.0 = fully dense plastic).
    rel = np.zeros(occ.shape, dtype=float)
    rel[solid] = 1.0
    interior_idx = np.argwhere(interior)
    interior_pts = vg.indices_to_points(interior_idx) if len(interior_idx) else np.zeros((0, 3))
    rel[tuple(interior_idx.T)] = _interior_density_field(
        interior_pts, settings, pitch, pattern_aware, weights=coverage[tuple(interior_idx.T)]
    )

    # Remove residual discretization bias: scale coverage-weighted voxel
    # volume to the exact mesh volume (only meaningful for watertight meshes).
    voxel_volume = pitch**3
    occ_idx = np.argwhere(occ)
    cov_occ = coverage[tuple(occ_idx.T)]
    occupied_volume = float(cov_occ.sum()) * voxel_volume
    volume_scale = (float(mesh.volume) / occupied_volume) if watertight else 1.0

    points_mm = vg.indices_to_points(occ_idx)
    rel_occ = rel[tuple(occ_idx.T)]
    masses_g = rel_occ * cov_occ * material.density_g_mm3 * voxel_volume * volume_scale

    # Accumulate in SI directly: mm -> m, g -> kg.
    cloud = PointMassCloud()
    cloud.add_points(masses_g * 1e-3, points_mm * 1e-3)
    cloud.add_cube_self_inertia(masses_g * 1e-3, pitch * 1e-3)
    props = cloud.finalize()

    solid_volume_mm3 = float(mesh.volume) if watertight else occupied_volume
    printed_volume_mm3 = float((rel_occ * cov_occ).sum()) * voxel_volume * volume_scale
    meta = {
        "backend": "voxel",
        "units": units,
        "pitch_mm": float(pitch),
        "grid_shape": list(occ.shape),
        "num_voxels_occupied": int(occ.sum()),
        "num_voxels_solid_shell": int(solid.sum()),
        "num_voxels_interior": int(interior.sum()),
        "watertight": bool(watertight),
        "pattern_aware": bool(pattern_aware and settings.pattern in GEOMETRY_AWARE_PATTERNS),
        "solid_volume_mm3": solid_volume_mm3,
        "printed_volume_mm3": printed_volume_mm3,
        "effective_density_g_cm3": (
            (props.mass * 1e3) / (solid_volume_mm3 * 1e-3) if solid_volume_mm3 > 0 else None
        ),
    }
    return props, meta
