# Quickstart

## Install

Install the latest from source:

```bash
pip install git+https://github.com/LakshyaSaraff/printphys.git
```

Or clone it for development:

```bash
git clone https://github.com/LakshyaSaraff/printphys.git
cd printphys
pip install -e ".[dev]"
```

## CLI

The most common call — mesh plus your real slicer settings:

```bash
printphys bracket.stl --material petg --infill 30 --pattern gyroid \
    --walls 3 --layer-height 0.2 --top-layers 5 --bottom-layers 4
```

The URDF `<inertial>` block goes to **stdout** (pipe or redirect it); a human summary
goes to stderr:

```text
material:  PETG (generic) (1.27 g/cm^3)
backend:   voxel
mass:      27.331 g
com:       [0.014102, 0.000000, 0.011250] m
inertia:   ixx=6.4113e-06 iyy=9.0212e-06 izz=7.7351e-06 kg*m^2
effective density: 0.6032 g/cm^3 (use as custom material density in CAD exporters)
```

Useful variants:

```bash
printphys part.stl --format json                 # full machine-readable report
printphys part.stl --format sdf                  # Gazebo
printphys part.stl --format mjcf                 # MuJoCo
printphys part.stl --units in                    # mesh modeled in inches
printphys part.stl --patch-urdf robot.urdf --link forearm   # edit URDF in place
printphys --gcode part.gcode --material pla      # ground truth from sliced G-code
printphys part.stl --weighed-mass 27.9g          # calibrate to a real measurement
```

## Python API

```python
from printphys import analyze, PrintSettings

result = analyze(
    "bracket.stl",
    settings=PrintSettings(
        infill_percent=30,
        pattern="gyroid",
        wall_count=3,
        layer_height=0.2,
    ),
    material="petg",
)

props = result.props
print(props.mass)          # kg
print(props.com)           # (3,) meters, mesh frame
print(props.inertia)       # (3,3) kg*m^2 about the COM

print(result.to_urdf())    # paste-ready <inertial> block
print(result.to_report())  # everything as a dict
```

Analyze already-sliced G-code (most accurate, includes supports/brim):

```python
result = analyze(gcode_path="bracket.gcode", material="petg")
```

Validate against a weighed print:

```python
result = analyze("bracket.stl", material="petg",
                 settings=PrintSettings(infill_percent=30),
                 weighed_mass_kg=0.0279)
print(result.validation)  # estimation error and rescale note
```

## Custom materials

Any YAML file works in place of a bundled name — a fully documented template ships
in [`examples/custom_material.yaml`](https://github.com/LakshyaSaraff/printphys/blob/main/examples/custom_material.yaml):

```yaml
# my_cf_petg.yaml
name: cf_petg
display_name: PETG-CF (BrandX)
density_g_cm3: 1.36
sources: ["BrandX TDS v2"]
```

```bash
printphys part.stl --material my_cf_petg.yaml --infill 40
```
