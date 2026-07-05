import pytest
import trimesh

from printphys.materials import load_material
from printphys.settings import PrintSettings


@pytest.fixture
def pla():
    return load_material("pla")


@pytest.fixture
def solid_settings():
    """100% infill: the part is a solid block; results must match analytic values."""
    return PrintSettings(infill_percent=100.0, wall_count=2, layer_height=0.2)


@pytest.fixture
def cube20():
    """20 mm cube centered at the origin."""
    return trimesh.creation.box(extents=[20.0, 20.0, 20.0])


@pytest.fixture
def cylinder():
    """r=10 mm, h=30 mm cylinder, axis along z, centered at the origin."""
    return trimesh.creation.cylinder(radius=10.0, height=30.0)
