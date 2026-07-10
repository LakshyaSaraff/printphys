# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Voxel/shell backend: print-aware mass properties without running a slicer.

The mesh is voxelized on a regular grid. Each occupied voxel receives a
*fractional* solid-shell content (0..1 of its material):

- wall: material within ``wall_count * line_width`` of the lateral surface
  (per-layer 2D distance transform, matching how slicers offset perimeters),
- skin: material within ``top_layers`` / ``bottom_layers`` of an up/down-facing
  surface (per-column run length, matching solid top/bottom layers),
- interior: the remaining material, printed at ``infill% * density``.

The shell is computed at sub-voxel resolution: each voxel knows the depth band
its material occupies below the part surface, and only the part of that band
inside the wall/skin thickness counts as solid. This keeps shell mass accurate
even when the voxel pitch is *larger* than the wall thickness — critical for
thin-walled parts, whose printed mass is dominated by perimeters and skins
rather than infill.

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

# trimesh's "subdivide" voxelizer splits every triangle until edges are shorter
# than the pitch, so a mesh with large flat triangles voxelized at a fine pitch
# can transiently explode to tens of millions of faces and exhaust memory.
# Budget for the estimated post-subdivision face count; the pitch is coarsened
# to stay within it. Thanks to the sub-voxel shell model, a coarser pitch no
# longer degrades wall/skin mass.
SUBDIVIDE_FACE_BUDGET = 2_000_000


def _choose_pitch(mesh: trimesh.Trimesh, settings: PrintSettings, max_per_axis: int) -> float:
    """Default pitch: layer height, coarsened if the part is large."""
    max_extent = float(mesh.extents.max())
    return max(settings.layer_height, max_extent / max_per_axis)


def _memory_safe_pitch(mesh: trimesh.Trimesh, pitch: float) -> float:
    """Coarsen the pitch if voxelization would exhaust memory.

    Estimates the number of faces trimesh's subdivide voxelizer will create
    (each face splits until its longest edge is below the pitch, i.e. roughly
    ``(edge / pitch)**2`` pieces) and coarsens the pitch so the total stays
    within ``SUBDIVIDE_FACE_BUDGET``.
    """
    tri = mesh.triangles
    edge = np.linalg.norm(np.diff(tri[:, [0, 1, 2, 0]], axis=1), axis=2)
    approx_faces = float(np.sum(np.ceil(edge.max(axis=1) / pitch) ** 2))
    if approx_faces <= SUBDIVIDE_FACE_BUDGET:
        return pitch
    safe = pitch * float(np.sqrt(approx_faces / SUBDIVIDE_FACE_BUDGET))
    warnings.warn(
        f"voxel pitch coarsened from {pitch:.3g} mm to {safe:.3g} mm to keep "
        "voxelization within memory limits (mesh has large faces); mass is "
        "unaffected, inertia resolution is slightly reduced",
        stacklevel=2,
    )
    return safe


def _depth_band(index: np.ndarray, at_surface: np.ndarray, pitch: float) -> tuple:
    """Depth interval (mm below the part surface) spanned by a voxel's material.

    ``index`` is the 1-based distance from the surface in voxels (EDT ring or
    skin run length). Surface-straddling voxels hold material in [0, pitch/2]
    (the boundary passes through their center — the same assumption behind the
    0.5 coverage weighting); deeper voxels are shifted by that half-voxel.
    """
    lo = np.where(at_surface & (index <= 1), 0.0, (index - 1.5) * pitch)
    hi = np.where(at_surface & (index <= 1), 0.5 * pitch, (index - 0.5) * pitch)
    return np.clip(lo, 0.0, None), np.clip(hi, 0.0, None)


def _band_overlap(lo: np.ndarray, hi: np.ndarray, thickness: float) -> np.ndarray:
    """Length of [lo, hi] that falls inside the solid band [0, thickness]."""
    return np.clip(np.minimum(hi, thickness) - lo, 0.0, None)


def _solid_fraction(
    occ: np.ndarray, surface: np.ndarray, pitch: float, settings: PrintSettings
) -> np.ndarray:
    """Fraction (0..1) of each occupied voxel's *material* that is solid shell.

    Walls and skins are resolved at sub-voxel precision: each voxel contributes
    the exact overlap of its depth band with the wall/skin thickness, so shell
    mass is (to first order) independent of the voxel pitch. A voxel pitch
    coarser than the wall no longer erases the wall.
    """
    nx, ny, nz = occ.shape
    surf = surface & occ
    # Material thickness represented by a voxel: half for surface voxels
    # (they straddle the boundary; matches the 0.5 coverage weighting).
    material = np.where(surf, 0.5 * pitch, pitch)
    solid_mm = np.zeros(occ.shape, dtype=float)

    # Lateral walls: per z-slice, in-plane EDT to the nearest empty cell.
    if settings.wall_thickness > 0:
        for z in range(nz):
            sl = occ[:, :, z]
            if not sl.any():
                continue
            dist = ndimage.distance_transform_edt(sl)
            lo, hi = _depth_band(dist, surf[:, :, z], pitch)
            solid_mm[:, :, z] += np.where(sl, _band_overlap(lo, hi, settings.wall_thickness), 0.0)

    # Top/bottom skins: per xy-column, run length of occupied voxels up/down
    # to the nearest air voxel (grid boundary counts as air).
    if settings.top_thickness > 0:
        run = np.zeros((nx, ny), dtype=np.int32)
        for z in range(nz - 1, -1, -1):
            run = np.where(occ[:, :, z], run + 1, 0)
            lo, hi = _depth_band(run, surf[:, :, z], pitch)
            solid_mm[:, :, z] += np.where(
                occ[:, :, z], _band_overlap(lo, hi, settings.top_thickness), 0.0
            )
    if settings.bottom_thickness > 0:
        run = np.zeros((nx, ny), dtype=np.int32)
        for z in range(nz):
            run = np.where(occ[:, :, z], run + 1, 0)
            lo, hi = _depth_band(run, surf[:, :, z], pitch)
            solid_mm[:, :, z] += np.where(
                occ[:, :, z], _band_overlap(lo, hi, settings.bottom_thickness), 0.0
            )

    with np.errstate(invalid="ignore"):
        frac = np.clip(solid_mm / material, 0.0, 1.0)
    frac[~occ] = 0.0
    return frac


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
    pitch = _memory_safe_pitch(mesh, pitch)

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

    solid_frac = _solid_fraction(occ, surface, pitch, settings)
    interior = occ & (solid_frac < 1.0)

    # Relative density per occupied voxel (1.0 = fully dense plastic): the
    # solid-shell fraction at full density plus the remaining material at the
    # interior (infill) density.
    rel = solid_frac.copy()
    interior_idx = np.argwhere(interior)
    interior_pts = vg.indices_to_points(interior_idx) if len(interior_idx) else np.zeros((0, 3))
    if len(interior_idx):
        idx = tuple(interior_idx.T)
        interior_material = 1.0 - solid_frac[idx]
        density = _interior_density_field(
            interior_pts, settings, pitch, pattern_aware,
            weights=coverage[idx] * interior_material,
        )
        rel[idx] += interior_material * density

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
        # Equivalent fully-solid voxel count of the shell (walls + skins).
        "num_voxels_solid_shell": int(round(float((solid_frac[tuple(occ_idx.T)] * cov_occ).sum()))),
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
