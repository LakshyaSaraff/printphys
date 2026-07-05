# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""High-level entry point: mesh + settings + material -> full analysis result."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import trimesh

from printphys.core import MassProperties
from printphys.materials import Material, load_material
from printphys.settings import PrintSettings


@dataclass
class AnalysisResult:
    """Everything printphys knows about the part, ready for export."""

    props: MassProperties
    material: Material
    settings: PrintSettings | None
    meta: dict = field(default_factory=dict)
    validation: dict | None = None

    def with_weighed_mass(self, weighed_mass_kg: float) -> AnalysisResult:
        """Rescale to a measured mass and record the estimation error."""
        estimated = self.props.mass
        error = (estimated - weighed_mass_kg) / weighed_mass_kg
        return AnalysisResult(
            props=self.props.rescaled_to_mass(weighed_mass_kg),
            material=self.material,
            settings=self.settings,
            meta=dict(self.meta),
            validation={
                "weighed_mass_kg": weighed_mass_kg,
                "estimated_mass_kg": estimated,
                "estimate_error_percent": round(100.0 * error, 2),
                "note": "outputs rescaled to the weighed mass",
            },
        )

    def to_report(self) -> dict:
        report = {
            "printphys": _version(),
            "mass_properties": self.props.to_dict(),
            "material": self.material.to_dict(),
            "settings": self.settings.to_dict() if self.settings else None,
            "backend": self.meta,
        }
        if self.validation:
            report["validation"] = self.validation
        return report

    def to_urdf(self, **kwargs) -> str:
        from printphys.export.urdf import inertial_xml

        return inertial_xml(self.props, **kwargs)

    def to_sdf(self, **kwargs) -> str:
        from printphys.export.sdf import inertial_xml

        return inertial_xml(self.props, **kwargs)

    def to_mjcf(self, **kwargs) -> str:
        from printphys.export.mjcf import inertial_xml

        return inertial_xml(self.props, **kwargs)


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("printphys")
    except Exception:
        return "unknown"


def load_mesh(path: str | Path) -> trimesh.Trimesh:
    mesh = trimesh.load(str(path), force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise ValueError(f"could not load a triangle mesh from {path}")
    return mesh


def analyze(
    mesh_path: str | Path | trimesh.Trimesh | None = None,
    settings: PrintSettings | None = None,
    material: str | Material = "pla",
    gcode_path: str | Path | None = None,
    units: str = "mm",
    pitch: float | None = None,
    pattern_aware: bool = True,
    weighed_mass_kg: float | None = None,
    filament_diameter_mm: float = 1.75,
) -> AnalysisResult:
    """Analyze a printed part and return mass properties plus diagnostics.

    Provide either ``mesh_path`` (voxel backend, uses ``settings``) or
    ``gcode_path`` (G-code backend, ground truth for a sliced print).
    """
    mat = load_material(material)

    if gcode_path is not None:
        from printphys.backends.gcode import analyze_gcode

        props, meta = analyze_gcode(gcode_path, mat, filament_diameter_mm=filament_diameter_mm)
        result = AnalysisResult(props=props, material=mat, settings=settings, meta=meta)
    elif mesh_path is not None:
        from printphys.backends.voxel import analyze_voxel

        settings = settings or PrintSettings()
        mesh = mesh_path if isinstance(mesh_path, trimesh.Trimesh) else load_mesh(mesh_path)
        props, meta = analyze_voxel(
            mesh, settings, mat, units=units, pitch=pitch, pattern_aware=pattern_aware
        )
        result = AnalysisResult(props=props, material=mat, settings=settings, meta=meta)
    else:
        raise ValueError("provide mesh_path or gcode_path")

    if weighed_mass_kg is not None:
        result = result.with_weighed_mass(weighed_mass_kg)
    return result
