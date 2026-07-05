# printphys

**Accurate URDF physics for 3D-printed parts.**

[![CI](https://github.com/LakshyaSaraff/printphys/actions/workflows/ci.yml/badge.svg)](https://github.com/LakshyaSaraff/printphys/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CAD tools compute inertia assuming your part is a solid block of plastic. A 3D-printed
part is not: it is dense walls and skins around sparse infill. `printphys` takes your
mesh plus your **actual print settings** (material, infill %, pattern, wall count,
layer height) and produces mass, center of mass, and the full inertia tensor — as a
ready-to-paste URDF `<inertial>` block (SDF and MJCF too).

## Quickstart

```bash
pip install git+https://github.com/LakshyaSaraff/printphys.git

printphys part.stl --material pla --infill 20 --pattern gyroid --walls 3
```

Output:

```xml
<inertial>
  <origin xyz="0.012021 0.000000 0.015000" rpy="0 0 0"/>
  <mass value="0.042137"/>
  <inertia ixx="1.94e-05" ixy="0.0" ixz="0.0" iyy="2.31e-05" iyz="0.0" izz="1.12e-05"/>
</inertial>
```

Or from Python:

```python
from printphys import analyze, PrintSettings

result = analyze(
    "part.stl",
    settings=PrintSettings(infill_percent=20, pattern="gyroid", wall_count=3),
    material="pla",
)
print(result.props.mass, result.props.com, result.props.inertia)
print(result.to_urdf())
```

## How it works

Two backends, one interface:

- **Voxel backend (default, zero extra tools).** The mesh is voxelized; voxels within
  the wall thickness of the surface and within the top/bottom skin layers get full
  material density, the interior gets `infill% x density` (optionally modulated by the
  actual infill pattern geometry for gyroid/grid/lines). Mass, COM, and inertia are
  integrated over the voxel field.
- **G-code backend (high accuracy).** Point `printphys` at a G-code file you already
  sliced (`--gcode part.gcode`) and every extrusion move is integrated as a mass
  element. This is ground truth for your actual print — walls, skins, infill, supports
  and all.

At 100% infill the voxel backend converges to the exact solid-body inertia, which is
anchored by the test suite. See [docs/accuracy.md](docs/accuracy.md) for methodology
and error characteristics.

## Validate against reality

Weigh your printed part and pass it in:

```bash
printphys part.stl --material pla --infill 20 --weighed-mass 38.4g
```

`printphys` rescales all outputs to match the measured mass and reports how far off
the estimate was. If you do this, consider submitting the datapoint via the
[calibration issue template](.github/ISSUE_TEMPLATE/calibration_datapoint.md) — it
helps everyone. See [`validation/`](validation/) for real print-and-weigh case studies.

## More outputs

```bash
printphys part.stl --material petg --infill 30 --format sdf     # Gazebo SDF
printphys part.stl --material petg --infill 30 --format mjcf    # MuJoCo MJCF
printphys part.stl --material petg --infill 30 --format json    # full report
printphys part.stl --material pla  --infill 20 \
    --patch-urdf robot.urdf --link forearm                      # patch in place
```

The JSON report also includes the **effective density** (printed mass / solid CAD
volume) so you can plug it back into SolidWorks/Fusion/Onshape exporters.

## Materials

Materials live as plain YAML files in
[`src/printphys/materials/`](src/printphys/materials/). PLA, PETG, ABS, ASA, and TPU
ship out of the box.

You can also use your own material without touching the package: copy
[`examples/custom_material.yaml`](examples/custom_material.yaml), fill in your
filament's data, and pass the file path anywhere a material name is accepted:

```bash
printphys part.stl --material my_filament.yaml --infill 20
```

To share a material with everyone, add the YAML via a PR — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- **v0.1** — voxel backend, PLA/PETG/ABS materials, URDF export, CLI
- **v0.2** — G-code backend, pattern-aware density fields, SDF/MJCF export
- **v0.3** — collision-mesh simplification
- **Later** — web UI (drag-and-drop)

## Contributing

Issues and PRs welcome — the lowest-barrier contribution is a material YAML or a
calibration datapoint (weigh a part, report the error). See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License and credit

Copyright (c) 2026 **Lakshya Saraf** — author and developer of printphys.

Licensed under the [MIT License](LICENSE): free to use, modify, distribute, and
build upon, including commercially. The only condition is that the copyright
notice and license text are retained in copies.
