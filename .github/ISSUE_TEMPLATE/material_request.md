---
name: Material request / submission
about: Request or contribute a filament material definition
labels: materials
---

**Material** (e.g. "Prusament PETG", "Bambu PLA-CF")

**Data** (fill what you have; density is the only hard requirement)

```yaml
density_g_cm3:
cost_per_kg_usd:
elastic_modulus_gpa:
glass_transition_c:
sources:
  - ""
```

Even better: open a PR adding the YAML to `src/printphys/materials/` directly.
