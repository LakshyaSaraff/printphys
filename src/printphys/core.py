# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Rigid-body mass properties"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class MassProperties:
    """Mass properties of a rigid body in SI units.

    Attributes:
        mass: mass in kg.
        com: center of mass, (3,) array in meters, expressed in the mesh frame.
        inertia: 3x3 inertia tensor in kg*m^2, about the COM, axes aligned
            with the mesh frame.
    """

    mass: float
    com: np.ndarray
    inertia: np.ndarray

    def __post_init__(self) -> None:
        self.com = np.asarray(self.com, dtype=float).reshape(3)
        self.inertia = np.asarray(self.inertia, dtype=float).reshape(3, 3)
        if self.mass < 0:
            raise ValueError(f"mass must be non-negative, got {self.mass}")
        if not np.allclose(self.inertia, self.inertia.T, atol=1e-12):
            raise ValueError("inertia tensor must be symmetric")

    # URDF-style scalar accessors
    @property
    def ixx(self) -> float:
        return float(self.inertia[0, 0])

    @property
    def iyy(self) -> float:
        return float(self.inertia[1, 1])

    @property
    def izz(self) -> float:
        return float(self.inertia[2, 2])

    @property
    def ixy(self) -> float:
        return float(self.inertia[0, 1])

    @property
    def ixz(self) -> float:
        return float(self.inertia[0, 2])

    @property
    def iyz(self) -> float:
        return float(self.inertia[1, 2])

    def principal_moments(self) -> np.ndarray:
        """Eigenvalues of the inertia tensor, ascending."""
        return np.sort(np.linalg.eigvalsh(self.inertia))

    def is_physically_valid(self, rtol: float = 1e-6) -> bool:
        """Check positive-semidefiniteness and the triangle inequality.

        Any real rigid body satisfies Ia + Ib >= Ic for its principal moments;
        simulators (e.g. MuJoCo) reject bodies that violate this.
        """
        a, b, c = self.principal_moments()
        if a < -rtol * max(c, 1e-30):
            return False
        return a + b >= c * (1 - rtol)

    def inertia_about(self, point: np.ndarray) -> np.ndarray:
        """Inertia tensor about an arbitrary point (parallel-axis theorem)."""
        r = self.com - np.asarray(point, dtype=float).reshape(3)
        return self.inertia + self.mass * (np.dot(r, r) * np.eye(3) - np.outer(r, r))

    def rescaled_to_mass(self, target_mass: float) -> MassProperties:
        """Uniformly rescale density so total mass equals ``target_mass``.

        COM is unchanged; inertia scales linearly with mass. This is how a
        weighed-part measurement is applied.
        """
        if self.mass <= 0:
            raise ValueError("cannot rescale a zero-mass body")
        k = target_mass / self.mass
        return MassProperties(mass=target_mass, com=self.com.copy(), inertia=self.inertia * k)

    def to_dict(self) -> dict:
        return {
            "mass_kg": float(self.mass),
            "com_m": [float(v) for v in self.com],
            "inertia_kg_m2": {
                "ixx": self.ixx,
                "iyy": self.iyy,
                "izz": self.izz,
                "ixy": self.ixy,
                "ixz": self.ixz,
                "iyz": self.iyz,
            },
            "principal_moments_kg_m2": [float(v) for v in self.principal_moments()],
        }


@dataclass
class PointMassCloud:
    """Accumulator that integrates mass properties from discrete mass elements.

    Used by both backends: voxels contribute point masses plus their own cube
    self-inertia; G-code extrusion segments contribute exact line-segment moments.
    Everything is accumulated about the origin and converted at the end.
    """

    mass: float = 0.0
    first_moment: np.ndarray = field(default_factory=lambda: np.zeros(3))
    # Second moment matrix S = integral of rho * r r^T dV, about origin.
    second_moment: np.ndarray = field(default_factory=lambda: np.zeros((3, 3)))
    # Extra inertia from element self-shape (e.g. voxel cubes), frame-aligned.
    self_inertia: np.ndarray = field(default_factory=lambda: np.zeros((3, 3)))

    def add_points(self, masses: np.ndarray, positions: np.ndarray) -> None:
        """Add point masses. masses: (N,), positions: (N, 3)."""
        m = np.asarray(masses, dtype=float)
        p = np.asarray(positions, dtype=float)
        self.mass += float(m.sum())
        self.first_moment += m @ p
        self.second_moment += (p * m[:, None]).T @ p

    def add_cube_self_inertia(self, masses: np.ndarray, side: float) -> None:
        """Add the self-inertia of axis-aligned cubes of edge length ``side``."""
        total = float(np.asarray(masses, dtype=float).sum())
        self.self_inertia += np.eye(3) * (total * side * side / 6.0)

    def add_segment(self, mass: float, a: np.ndarray, b: np.ndarray) -> None:
        """Add a uniform line segment of mass from point a to point b.

        Uses the exact second moment of a line:
        E[r r^T] = (aa^T + bb^T)/3 + (ab^T + ba^T)/6
        """
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        self.mass += mass
        self.first_moment += mass * (a + b) / 2.0
        s = (np.outer(a, a) + np.outer(b, b)) / 3.0 + (np.outer(a, b) + np.outer(b, a)) / 6.0
        self.second_moment += mass * s

    def finalize(self) -> MassProperties:
        """Convert accumulated moments to MassProperties about the COM."""
        if self.mass <= 0:
            raise ValueError("no mass accumulated; is the mesh/G-code empty?")
        com = self.first_moment / self.mass
        # Shift second moment to COM: S_com = S - m * com com^T
        s_com = self.second_moment - self.mass * np.outer(com, com)
        inertia = np.trace(s_com) * np.eye(3) - s_com + self.self_inertia
        # Enforce exact symmetry against floating-point drift.
        inertia = (inertia + inertia.T) / 2.0
        return MassProperties(mass=self.mass, com=com, inertia=inertia)


# Unit conversion helpers. Meshes are usually modeled in mm; physics is SI.
_UNIT_TO_M = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}


def unit_scale_to_meters(units: str) -> float:
    try:
        return _UNIT_TO_M[units.lower()]
    except KeyError:
        raise ValueError(
            f"unknown units {units!r}; expected one of {sorted(_UNIT_TO_M)}"
        ) from None
