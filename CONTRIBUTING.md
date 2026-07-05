# Contributing to printphys

Thanks for helping make simulation physics of printed parts less wrong. There are
three tiers of contribution, from five minutes to a weekend:

## 1. Add a material (easiest, most wanted)

Materials are plain YAML files in `src/printphys/materials/`. Copy an existing one:

```yaml
name: pla
display_name: PLA (generic)
density_g_cm3: 1.24
cost_per_kg_usd: 20
elastic_modulus_gpa: 3.5
glass_transition_c: 60
sources:
  - "Manufacturer TDS or published test data URL"
notes: "Generic values; specific brands vary."
```

Rules:

- `density_g_cm3` is required and must come from a manufacturer TDS or measured data.
- Cite your source in `sources`. Brand-specific files are welcome
  (e.g. `pla_prusament.yaml`).

## 2. Submit a calibration datapoint

Print a part, weigh it, run:

```bash
printphys part.stl --material <mat> --infill <n> --pattern <p> --walls <w> --weighed-mass <grams>g --format json
```

Open an issue with the [calibration datapoint template](.github/ISSUE_TEMPLATE/calibration_datapoint.md)
and paste the JSON. This is how we measure and improve real-world accuracy.

## 3. Code contributions

Setup:

```bash
git clone https://github.com/LakshyaSaraff/printphys && cd printphys
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest
```

Guidelines:

- `ruff check .` and `pytest` must pass; CI runs both on Linux/macOS/Windows.
- New physics code needs a test against an analytic or independently computed value
  (see `tests/test_voxel_backend.py` for the pattern).
- Keep the core dependency set small (`numpy`, `scipy`, `trimesh`, `PyYAML`).
  Anything heavier goes behind an optional extra.
- One logical change per PR; explain *why* in the description.

Good first issues are labeled
[`good first issue`](https://github.com/LakshyaSaraff/printphys/labels/good%20first%20issue).

## Licensing of contributions

printphys is licensed under the [MIT License](LICENSE) with copyright held by
Lakshya Saraf. By submitting a contribution you agree that it is licensed to the
project under the same terms. You will be credited in the contributor history.

## Questions

Open a [discussion](https://github.com/LakshyaSaraff/printphys/discussions) — no question
is too basic.
