# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""printphys: accurate URDF physics for 3D-printed parts."""

__author__ = "Lakshya Saraf"
__copyright__ = "Copyright (c) 2026 Lakshya Saraf"
__license__ = "MIT"

from printphys.analyze import AnalysisResult, analyze, load_mesh
from printphys.core import MassProperties
from printphys.materials import Material, available_materials, load_material
from printphys.settings import PrintSettings

__all__ = [
    "AnalysisResult",
    "MassProperties",
    "Material",
    "PrintSettings",
    "analyze",
    "available_materials",
    "load_material",
    "load_mesh",
]
