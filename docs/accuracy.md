# Accuracy methodology

`printphys` is only useful if you can trust its numbers, so this page spells out
exactly how each backend computes mass properties, what is approximated, and what
errors to expect.

## The problem being solved

For a rigid body, a simulator needs mass \(m\), center of mass, and the inertia
tensor \(I = \int \rho(\mathbf{r}) (\lVert\mathbf{r}\rVert^2 E - \mathbf{r}\mathbf{r}^T)\,dV\).
For a printed part the density field \(\rho(\mathbf{r})\) is **not uniform**: walls,
top/bottom skins, and solid features are fully dense; the interior is infill at a
fraction of material density. Assigning solid density in CAD gets the mass wrong by
up to ~2-3x and distorts the inertia distribution (infill parts carry relatively
more mass near their surface, where walls are).

## Voxel backend (default)

1. The mesh (assumed watertight; holes are auto-filled where possible) is voxelized
   on a regular grid. Pitch defaults to the layer height, coarsened so no axis
   exceeds 192 voxels.
2. Voxels that straddle the surface are volume-weighted at 0.5 to cancel the
   half-pitch dilation bias of voxelization; the coverage-weighted total volume is
   then rescaled to the exact mesh volume, so **mass is exact** (given the density
   and settings).
3. Classification mirrors what a slicer does:
    - **Walls**: per-layer 2D distance transform; voxels within
      `wall_count x line_width` of the lateral boundary are fully dense.
    - **Skins**: per-column run length; voxels within `top_layers`/`bottom_layers`
      of an up/down-facing surface are fully dense.
    - **Interior**: relative density `infill%`, either uniform or modulated by a
      geometric model of the pattern (gyroid level-set, grid/line lattices). The
      pattern field is quantile-thresholded and renormalized, so it changes the
      *distribution* of mass, never the total.
4. Mass, COM, and inertia are integrated over the voxel field, including each
   voxel's own cube inertia \(m s^2/6\).

**Anchor**: at 100% infill the entire grid is fully dense and the result must match
the exact solid-body inertia of the mesh. The test suite pins a 20 mm cube and a
cylinder against analytic formulas to within 3% at default resolution (the residual
is surface discretization; it shrinks with `--pitch`).

**Expected real-world error**: a few percent on mass for clean prints (slicers
deviate from nominal infill; first-layer squish, brims and wipe towers are not
modeled). COM/inertia errors are dominated by the same effects and are typically
smaller in relative terms because they are normalized by mass.

## G-code backend (`--gcode`)

Each `G1` extrusion move deposits `deltaE x filament cross-section` of material.
Every move is integrated as a uniform **line segment** with exact first and second
moments (\(E[\mathbf{r}\mathbf{r}^T] = \tfrac{1}{3}(\mathbf{a}\mathbf{a}^T +
\mathbf{b}\mathbf{b}^T) + \tfrac{1}{6}(\mathbf{a}\mathbf{b}^T + \mathbf{b}\mathbf{a}^T)\)).
This captures walls, skins, infill pattern, supports, and brims exactly as the
printer will lay them down — it is the ground truth for the *plan* of your print.

Approximations: arc moves (G2/G3) are treated as straight chords (counted in the
report metadata); the finite cross-section of each bead (~0.4 mm) contributes
negligible self-inertia at part scale and is ignored.

Remaining gap to reality: extrusion multiplier/flow calibration, moisture content
of filament, and density tolerance of the filament itself (+-2-4%).

## Closing the loop with a scale

The single best accuracy upgrade costs nothing: weigh the printed part.

```bash
printphys part.stl --material pla --infill 20 --weighed-mass 38.4g
```

All outputs are rescaled so mass matches the measurement (COM unchanged, inertia
scales linearly), and the report records how far off the estimate was. Density
errors — the dominant real-world error source — cancel exactly under this rescaling.

If you weigh parts, please submit the datapoints via the calibration issue
template; aggregated measurements guide model improvements.

## Known limitations

- Supports, brims, rafts, and wipe towers: not modeled by the voxel backend
  (use the G-code backend, or weigh the part after removing supports).
- Variable/adaptive layer height and modifier meshes: voxel backend assumes uniform
  settings over the part.
- Non-watertight meshes: hole filling is attempted; if it fails, volume corrections
  are disabled and a warning is emitted.
- Multi-material prints: single density per analysis for now.
