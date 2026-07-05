# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Filament material database.

Materials are plain YAML files in this directory so that contributing a new
filament is a copy-paste PR. Users can also load their own YAML from any path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml


@dataclass
class Material:
    name: str
    display_name: str
    density_g_cm3: float
    cost_per_kg_usd: float | None = None
    elastic_modulus_gpa: float | None = None
    glass_transition_c: float | None = None
    sources: list = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.density_g_cm3 <= 0:
            raise ValueError(f"density_g_cm3 must be > 0, got {self.density_g_cm3}")

    @property
    def density_kg_m3(self) -> float:
        return self.density_g_cm3 * 1000.0

    @property
    def density_g_mm3(self) -> float:
        return self.density_g_cm3 / 1000.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "density_g_cm3": self.density_g_cm3,
            "cost_per_kg_usd": self.cost_per_kg_usd,
            "elastic_modulus_gpa": self.elastic_modulus_gpa,
        }


def _from_yaml_text(text: str, fallback_name: str) -> Material:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("material YAML must be a mapping")
    data.setdefault("name", fallback_name)
    data.setdefault("display_name", data["name"])
    known = {f for f in Material.__dataclass_fields__}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"unknown material fields: {sorted(unknown)}")
    return Material(**data)


def available_materials() -> list[str]:
    """Names of all bundled materials."""
    pkg = resources.files(__name__)
    return sorted(p.name[: -len(".yaml")] for p in pkg.iterdir() if p.name.endswith(".yaml"))


def load_material(name_or_path: str | Path | Material) -> Material:
    """Load a material by bundled name ('pla') or from a YAML file path."""
    if isinstance(name_or_path, Material):
        return name_or_path
    path = Path(name_or_path)
    if path.suffix.lower() in {".yaml", ".yml"} and path.exists():
        return _from_yaml_text(path.read_text(encoding="utf-8"), path.stem)
    name = str(name_or_path).lower()
    ref = resources.files(__name__) / f"{name}.yaml"
    try:
        text = ref.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(
            f"unknown material {name!r}; bundled materials: {available_materials()}. "
            "You can also pass a path to your own YAML file."
        ) from None
    return _from_yaml_text(text, name)
