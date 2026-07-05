import numpy as np
import pytest

from printphys.core import MassProperties, PointMassCloud, unit_scale_to_meters


def test_mass_properties_validation():
    with pytest.raises(ValueError):
        MassProperties(mass=-1.0, com=np.zeros(3), inertia=np.eye(3))
    asym = np.eye(3)
    asym[0, 1] = 0.5
    with pytest.raises(ValueError):
        MassProperties(mass=1.0, com=np.zeros(3), inertia=asym)


def test_parallel_axis_theorem():
    # Point mass at origin, shifted evaluation point.
    props = MassProperties(mass=2.0, com=np.zeros(3), inertia=np.zeros((3, 3)))
    inertia = props.inertia_about([1.0, 0.0, 0.0])
    # m*d^2 about axes perpendicular to the offset, zero along it.
    assert inertia[0, 0] == pytest.approx(0.0)
    assert inertia[1, 1] == pytest.approx(2.0)
    assert inertia[2, 2] == pytest.approx(2.0)


def test_rescaled_to_mass():
    props = MassProperties(mass=2.0, com=np.array([1.0, 2.0, 3.0]), inertia=np.eye(3))
    scaled = props.rescaled_to_mass(4.0)
    assert scaled.mass == pytest.approx(4.0)
    np.testing.assert_allclose(scaled.com, props.com)
    np.testing.assert_allclose(scaled.inertia, 2.0 * np.eye(3))


def test_triangle_inequality_check():
    good = MassProperties(mass=1.0, com=np.zeros(3), inertia=np.diag([1.0, 1.0, 1.5]))
    assert good.is_physically_valid()
    # izz > ixx + iyy is impossible for a real body.
    bad = MassProperties(mass=1.0, com=np.zeros(3), inertia=np.diag([1.0, 1.0, 3.0]))
    assert not bad.is_physically_valid()


def test_segment_matches_analytic_rod():
    """A uniform rod of length L about its center: I_perp = m L^2 / 12 (exact)."""
    length, mass = 0.5, 3.0
    cloud = PointMassCloud()
    cloud.add_segment(mass, np.array([0.0, 0.0, 0.0]), np.array([length, 0.0, 0.0]))
    props = cloud.finalize()
    np.testing.assert_allclose(props.com, [length / 2, 0, 0], atol=1e-12)
    expected = mass * length**2 / 12.0
    assert props.inertia[1, 1] == pytest.approx(expected, rel=1e-12)
    assert props.inertia[2, 2] == pytest.approx(expected, rel=1e-12)
    assert props.inertia[0, 0] == pytest.approx(0.0, abs=1e-15)


def test_point_cloud_matches_two_point_analytic():
    cloud = PointMassCloud()
    cloud.add_points(np.array([1.0, 1.0]), np.array([[-1.0, 0, 0], [1.0, 0, 0]]))
    props = cloud.finalize()
    assert props.mass == pytest.approx(2.0)
    np.testing.assert_allclose(props.com, [0, 0, 0], atol=1e-12)
    assert props.inertia[1, 1] == pytest.approx(2.0)  # 2 * m * d^2


def test_unit_scale():
    assert unit_scale_to_meters("mm") == pytest.approx(0.001)
    assert unit_scale_to_meters("in") == pytest.approx(0.0254)
    with pytest.raises(ValueError):
        unit_scale_to_meters("furlong")
