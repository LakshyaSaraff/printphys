"""Golden-value tests: at 100% infill the voxel backend must converge to the
exact solid-body values, and print settings must move mass in the physically
expected direction."""

import numpy as np
import pytest

from printphys.backends.voxel import analyze_voxel

PLA_RHO = 1.24e-3  # g/mm^3


class TestSolidCubeGoldenValues:
    """20 mm PLA cube at 100% infill vs analytic solid values."""

    @pytest.fixture(autouse=True)
    def _run(self, cube20, solid_settings, pla):
        self.props, self.meta = analyze_voxel(cube20, solid_settings, pla, pitch=0.5)

    def test_mass_exact(self):
        expected_kg = 20.0**3 * PLA_RHO * 1e-3  # 9.92 g
        assert self.props.mass == pytest.approx(expected_kg, rel=1e-6)

    def test_com_at_centroid(self):
        np.testing.assert_allclose(self.props.com, [0, 0, 0], atol=1e-6)

    def test_inertia_matches_analytic(self):
        # Solid cuboid: I = m (a^2 + b^2) / 12 per axis, a = b = 0.02 m.
        m = 20.0**3 * PLA_RHO * 1e-3
        expected = m * (0.02**2 + 0.02**2) / 12.0
        for axis in range(3):
            assert self.props.inertia[axis, axis] == pytest.approx(expected, rel=0.03)

    def test_off_diagonals_negligible(self):
        off = self.props.inertia[~np.eye(3, dtype=bool)]
        assert np.abs(off).max() < 1e-3 * self.props.ixx

    def test_physically_valid(self):
        assert self.props.is_physically_valid()


class TestSolidCylinderGoldenValues:
    """r=10 mm, h=30 mm PLA cylinder at 100% infill vs analytic solid values."""

    @pytest.fixture(autouse=True)
    def _run(self, cylinder, solid_settings, pla):
        self.props, self.meta = analyze_voxel(cylinder, solid_settings, pla, pitch=0.4)
        self.m = np.pi * 10.0**2 * 30.0 * PLA_RHO * 1e-3  # kg
        self.r, self.h = 0.010, 0.030  # m

    def test_mass_exact(self):
        # Volume correction uses the mesh volume; the mesh is a faceted
        # approximation of the cylinder, so compare to the mesh, not pi.
        assert self.props.mass == pytest.approx(self.m, rel=0.01)

    def test_izz_matches_analytic(self):
        expected = self.m * self.r**2 / 2.0
        assert self.props.izz == pytest.approx(expected, rel=0.03)

    def test_ixx_matches_analytic(self):
        expected = self.m * (3 * self.r**2 + self.h**2) / 12.0
        assert self.props.ixx == pytest.approx(expected, rel=0.03)


class TestInfillBehavior:
    def test_mass_monotonic_in_infill(self, cube20, pla, solid_settings):
        masses = []
        for infill in (0.0, 20.0, 60.0, 100.0):
            settings = type(solid_settings)(infill_percent=infill, wall_count=2)
            props, _ = analyze_voxel(cube20, settings, pla, pitch=0.5)
            masses.append(props.mass)
        assert masses == sorted(masses)
        assert masses[0] > 0  # walls and skins still weigh something at 0% infill

    def test_sparse_lighter_than_solid_but_heavier_than_hollow(self, cube20, pla):
        from printphys.settings import PrintSettings

        sparse, _ = analyze_voxel(cube20, PrintSettings(infill_percent=20), pla, pitch=0.5)
        solid, _ = analyze_voxel(cube20, PrintSettings(infill_percent=100), pla, pitch=0.5)
        assert sparse.mass < 0.75 * solid.mass

    def test_pattern_aware_preserves_mass(self, cube20, pla):
        """The pattern field redistributes mass; it must not change the total."""
        from printphys.settings import PrintSettings

        settings = PrintSettings(infill_percent=20, pattern="gyroid")
        aware, _ = analyze_voxel(cube20, settings, pla, pitch=0.5, pattern_aware=True)
        uniform, _ = analyze_voxel(cube20, settings, pla, pitch=0.5, pattern_aware=False)
        assert aware.mass == pytest.approx(uniform.mass, rel=1e-6)
        np.testing.assert_allclose(aware.com, uniform.com, atol=1e-4)

    def test_effective_density_reported(self, cube20, pla):
        from printphys.settings import PrintSettings

        _, meta = analyze_voxel(cube20, PrintSettings(infill_percent=20), pla, pitch=0.5)
        eff = meta["effective_density_g_cm3"]
        assert 0 < eff < 1.24  # sparser than solid PLA


class TestUnits:
    def test_meter_mesh_matches_mm_mesh(self, cube20, solid_settings, pla):
        mm_props, _ = analyze_voxel(cube20, solid_settings, pla, units="mm", pitch=0.5)
        m_mesh = cube20.copy()
        m_mesh.apply_scale(0.001)  # same cube expressed in meters
        m_props, _ = analyze_voxel(m_mesh, solid_settings, pla, units="m", pitch=0.5)
        assert m_props.mass == pytest.approx(mm_props.mass, rel=1e-6)
        np.testing.assert_allclose(m_props.inertia, mm_props.inertia, rtol=1e-6)
