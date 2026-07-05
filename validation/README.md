# Validation case studies

Real prints, real scales, real errors. Each subfolder documents one part: its
geometry, the settings used, what `printphys` estimated, what a slicer estimated
(if available), and what a physical scale actually measured.

These are not shipped as automated tests — they depend on real hardware and
real filament — but they're the most honest accuracy record we have, and they
directly inform improvements to the backends.

STL files are **not** committed here; each write-up links to the original
source instead, so we respect the original designers' licenses and keep the
repository small.

## Cases

- [`lb04-xbox-bumper/`](lb04-xbox-bumper/) — small, wall-dominated part (CC BY-SA
  model by raffosan); printphys underestimated mass by ~6.9% at default voxel
  resolution, ~4.8% at finer resolution.

## Contributing a case

Weighed a part? Open a [calibration datapoint issue](../.github/ISSUE_TEMPLATE/calibration_datapoint.md),
or go further and add a folder here following the same structure: source/license,
settings used, a results table, and your interpretation of the gap.
