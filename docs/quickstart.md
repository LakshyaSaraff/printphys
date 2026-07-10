# Quickstart

Get from mesh to URDF `<inertial>` in a few commands.

## Install

```bash
pip install git+https://github.com/LakshyaSaraff/printphys.git
```

Development install:

```bash
git clone https://github.com/LakshyaSaraff/printphys.git
cd printphys
pip install -e ".[dev]"
```

## Your first run

```bash
printphys bracket.stl --material petg --infill 30 --walls 3
```

URDF XML goes to **stdout** (pipe or redirect it). A short summary goes to **stderr**:

```text
material:  PETG (generic) (1.27 g/cm^3)
backend:   voxel
mass:      27.331 g
com:       [0.014102, 0.000000, 0.011250] m
inertia:   ixx=6.4113e-06 iyy=9.0212e-06 izz=7.7351e-06 kg*m^2
```

Match your slicer settings with the flags you already use there:

```bash
printphys bracket.stl --material petg --infill 30 --pattern gyroid \
    --walls 3 --layer-height 0.2 --top-layers 5 --bottom-layers 4
```

## Three ways to run

| Path | Command | When to use |
| --- | --- | --- |
| **Voxel** (default) | `printphys part.stl --material pla ...` | No extra tools; quick estimates |
| **Your G-code** | `printphys --gcode part.gcode.3mf --material pla` | You already slice in Bambu/Orca/Prusa |
| **Auto-slice** | `printphys part.stl --slice --material pla ...` | Slicer CLI installed (see below) |

**URDF tip:** voxel gives COM/inertia in the **mesh frame**. G-code uses the
**printer bed** frame — fine for mass, awkward for URDF. For robot links, use
voxel and calibrate with `--weighed-mass`, or rescale voxel to a G-code mass.
See [accuracy.md](accuracy.md).

## Slicer CLI (`--slice`)

Optional. Install one slicer if you want one-command G-code accuracy:

- [PrusaSlicer](https://www.prusa3d.com/prusaslicer/) (recommended)
- [Bambu Studio](https://bambulab.com/download/studio)
- [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer/releases)

`printphys` looks for `PRINTPHYS_SLICER`, then `PATH`, then common install
folders. Or pass the binary directly:

```bash
printphys part.stl --slice --slicer-exe "D:\Bambu Studio\bambu-studio.exe" ...
```

Already slice in a GUI? Export G-code and use `--gcode` — no CLI needed.

## Useful flags

```bash
printphys part.stl --format json              # full report
printphys part.stl --format sdf               # Gazebo
printphys part.stl --format mjcf              # MuJoCo
printphys part.stl --units in                 # mesh in inches
printphys part.stl --weighed-mass 27.9g       # rescale to measured mass
printphys part.stl --patch-urdf robot.urdf --link forearm
```

## Python

```python
from printphys import analyze, PrintSettings

# mesh (voxel)
result = analyze(
    "bracket.stl",
    settings=PrintSettings(infill_percent=30, pattern="gyroid", wall_count=3),
    material="petg",
)
print(result.to_urdf())
print(result.props.mass, result.props.com, result.props.inertia)

# sliced G-code
result = analyze(gcode_path="bracket.gcode", material="petg")

# calibrate to a weighed print
result = analyze(
    "bracket.stl",
    settings=PrintSettings(infill_percent=30),
    material="petg",
    weighed_mass_kg=0.0279,
)
print(result.validation)
```

## Custom materials

Copy [`examples/custom_material.yaml`](../examples/custom_material.yaml), set your
filament density, and pass the file path:

```yaml
name: cf_petg
display_name: PETG-CF (BrandX)
density_g_cm3: 1.36
```

```bash
printphys part.stl --material my_cf_petg.yaml --infill 40
```

Bundled materials: PLA, PETG, ABS, ASA, TPU in
[`src/printphys/materials/`](../src/printphys/materials/).
