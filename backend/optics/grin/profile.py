"""
GRIN profile definitions.

Defines various gradient index profiles for optical materials.
"""

from typing import Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class GRINProfile:
    """Base class for GRIN profiles."""
    n0: float  # Base refractive index

    def index(self, *args) -> float:
        """Calculate refractive index at given position."""
        raise NotImplementedError

    def gradient(self, *args) -> np.ndarray:
        """Calculate index gradient at given position."""
        raise NotImplementedError


@dataclass
class AxialGRIN(GRINProfile):
    """
    Axial GRIN profile.

    n(z) = n0 + n1*z + n2*z^2 + ...

    Used for flat-surface lenses and lightpipe correction.
    """
    coefficients: list[float] = None  # [n0, n1, n2, ...]

    def __post_init__(self):
        if self.coefficients is None:
            self.coefficients = [self.n0, 0.0, 0.0]

    def index(self, x: float = 0, y: float = 0, z: float = 0) -> float:
        """Index at axial position z (x, y ignored)."""
        n = 0.0
        for i, c in enumerate(self.coefficients):
            n += c * z**i
        return n

    def gradient(self, x: float = 0, y: float = 0, z: float = 0) -> np.ndarray:
        """Gradient (0, 0, dn/dz)."""
        dn_dz = 0.0
        for i in range(1, len(self.coefficients)):
            dn_dz += i * self.coefficients[i] * z**(i-1)
        return np.array([0, 0, dn_dz])


@dataclass
class RadialGRIN(GRINProfile):
    """
    Radial GRIN profile.

    n(r) = n0 * (1 - g^2*r^2/2)   (parabolic profile, paraxial form)

    Used for GRIN rod lenses and graded-index fibres. ``g`` is in inverse
    length units consistent with the positions used (1/m for meters).
    """
    g: float  # gradient constant

    def index(self, x: float = 0, y: float = 0, z: float = 0) -> float:
        """Calculate index at radial position."""
        r_sq = x**2 + y**2
        return self.n0 * (1 - (self.g**2 * r_sq) / 2)

    def gradient(self, x: float = 0, y: float = 0, z: float = 0) -> np.ndarray:
        """Calculate gradient."""
        r_sq = x**2 + y**2
        factor = -self.n0 * self.g**2
        return np.array([factor * x, factor * y, 0])

    @property
    def pitch(self) -> float:
        """Calculate pitch (period of ray oscillation)."""
        return 2 * np.pi / self.g

    def ray_path(self, r0: float, theta0: float, length: float, num_points: int = 100):
        """Paraxial (sinusoidal) meridional ray path; theta0 inside the medium."""
        z = np.linspace(0, length, num_points)
        r = r0 * np.cos(self.g * z) + (theta0 / self.g) * np.sin(self.g * z)
        return z, r


@dataclass
class GRIN3D(GRINProfile):
    """
    3D GRIN profile.

    n(x,y,z) = n0 + Gx*x + Gy*y + Gz*z + higher order terms
    """
    gradient_vector: np.ndarray = None  # [Gx, Gy, Gz]

    def __post_init__(self):
        if self.gradient_vector is None:
            self.gradient_vector = np.zeros(3)

    def index(self, x: float = 0, y: float = 0, z: float = 0) -> float:
        """Calculate index at position."""
        pos = np.array([x, y, z])
        return self.n0 + np.dot(self.gradient_vector, pos)

    def gradient(self, x: float = 0, y: float = 0, z: float = 0) -> np.ndarray:
        """Return constant gradient."""
        return self.gradient_vector.copy()
