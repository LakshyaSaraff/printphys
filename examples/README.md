# Examples

- `custom_material.yaml` — documented template for defining your own filament;
  pass its path anywhere a material name is accepted (`--material my.yaml`).
- `basic_usage.py` — generate a part, analyze it at several infill levels, and
  print URDF snippets. Run with `python basic_usage.py`.
- `pybullet_check.py` — drop the analyzed part into PyBullet and verify the
  simulated dynamics use your inertia (requires `pip install pybullet`).

No STL files are shipped; every example generates its geometry with `trimesh` so the
examples stay reproducible and the repo stays small. Substitute your own mesh path
anywhere a generated mesh is used.
