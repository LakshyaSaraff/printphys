# printphys

**Accurate URDF physics for 3D-printed parts.**

[![CI](https://github.com/LakshyaSaraff/printphys/actions/workflows/ci.yml/badge.svg)](https://github.com/LakshyaSaraff/printphys/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CAD assumes solid plastic. Real prints are walls, skins, and sparse infill.
`printphys` takes your mesh and print settings and returns mass, center of mass,
and inertia — as a paste-ready URDF `<inertial>` block (SDF and MJCF too).

## Install

```bash
pip install git+https://github.com/LakshyaSaraff/printphys.git
```

## Usage

Pick the path that matches your setup:

```bash
# 1. No slicer — fast estimate from the mesh (default)
printphys part.stl --material pla --infill 20 --walls 3

# 2. You already slice in Bambu/Orca/Prusa — analyze that G-code
printphys --gcode part.gcode.3mf --material pla

# 3. Slicer CLI installed — slice + analyze in one step
printphys part.stl --slice --material pla --infill 20 --walls 3
```

Output (stdout):

```xml
<inertial>
  <origin xyz="0.012021 0.000000 0.015000" rpy="0 0 0"/>
  <mass value="0.042137"/>
  <inertia ixx="1.94e-05" ixy="0.0" ixz="0.0" iyy="2.31e-05" iyz="0.0" izz="1.12e-05"/>
</inertial>
```

Python:

```python
from printphys import analyze, PrintSettings

result = analyze("part.stl", settings=PrintSettings(infill_percent=20, wall_count=3), material="pla")
print(result.to_urdf())
```

Other formats: `--format json|sdf|mjcf`. Patch a URDF in place:
`--patch-urdf robot.urdf --link forearm`.

## Backends

| | Voxel (default) | G-code (`--gcode` / `--slice`) |
| --- | --- | --- |
| Needs | mesh + settings | sliced toolpaths |
| Mass accuracy | good; ~5–15% low on complex parts | matches slicer (validated vs Bambu Studio) |
| Frame | mesh — ready for URDF | printer bed |
| Best for | quick estimates, setting sweeps | final numbers |

- **Voxel** — voxelizes the mesh; walls/skins at sub-voxel precision, infill by pattern.
- **G-code** — integrates every extrusion move; captures seams, gap fill, supports.

For URDF links, prefer voxel (mesh frame) and calibrate mass with `--weighed-mass 38.4g`,
or use G-code mass to rescale. Details: [docs/accuracy.md](docs/accuracy.md).

## Slicer CLI (optional)

`printphys` does not bundle a slicer. Use `--slice` only if you want one-command
G-code accuracy and are fine installing a slicer yourself:

- [PrusaSlicer](https://www.prusa3d.com/prusaslicer/) (recommended)
- [Bambu Studio](https://bambulab.com/download/studio)
- [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer/releases)

Auto-detect: `PRINTPHYS_SLICER` → `PATH` → common install folders. Or point
directly:

```bash
printphys part.stl --slice --slicer-exe "D:\Bambu Studio\bambu-studio.exe" ...
```

Already sliced in a GUI? Skip the CLI — export G-code and use `--gcode` instead.

## Calibrate

Weigh the printed part:

```bash
printphys part.stl --material pla --infill 20 --weighed-mass 38.4g
```

Rescales output to the measured mass and reports the estimate error. Case studies:
[`validation/`](validation/).

## Materials

PLA, PETG, ABS, ASA, and TPU ship in [`src/printphys/materials/`](src/printphys/materials/).
Custom filament: copy [`examples/custom_material.yaml`](examples/custom_material.yaml)
and pass `--material my_filament.yaml`.

## Contributing

Issues and PRs welcome — material YAMLs and weigh-and-compare datapoints are
especially useful. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — Copyright (c) 2026 Lakshya Saraf. See [LICENSE](LICENSE).
