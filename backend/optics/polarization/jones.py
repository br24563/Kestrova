"""
Jones calculus for polarization analysis.

Jones calculus uses 2x2 complex matrices to represent polarization
state and optical elements. Valid for fully polarized (coherent) light.
"""

from typing import Union
from dataclasses import dataclass
import numpy as np


@dataclass
class JonesVector:
    """2-element complex vector representing polarization state."""
    Ex: complex  # x-component of electric field
    Ey: complex  # y-component of electric field
    
    def __post_init__(self):
        self.vector = np.array([self.Ex, self.Ey], dtype=complex)
    
    @property
    def intensity(self) -> float:
        """Total intensity."""
        return abs(self.Ex)**2 + abs(self.Ey)**2
    
    @property
    def phase_difference(self) -> float:
        """Phase difference between components."""
        return np.angle(self.Ey) - np.angle(self.Ex)
    
    @property
    def azimuth(self) -> float:
        """Polarization azimuth angle."""
        return 0.5 * np.arctan2(2 * (self.Ex.conjugate() * self.Ey).real,
                                abs(self.Ex)**2 - abs(self.Ey)**2)
    
    @property
    def ellipticity(self) -> float:
        """Ellipticity angle."""
        S = self.to_stokes()
        if S.S0 > 0:
            return 0.5 * np.arcsin(S.S3 / S.S0)
        return 0.0
    
    def to_stokes(self):
        """Convert to Stokes vector."""
        from .stokes import StokesVector
        S0 = abs(self.Ex)**2 + abs(self.Ey)**2
        S1 = abs(self.Ex)**2 - abs(self.Ey)**2
        S2 = 2 * (self.Ex.conjugate() * self.Ey).real
        S3 = 2 * (self.Ex.conjugate() * self.Ey).imag
        return StokesVector(S0, S1, S2, S3)
    
    def apply(self, matrix: 'JonesMatrix') -> 'JonesVector':
        """Apply Jones matrix to this vector."""
        result = matrix.matrix @ self.vector
        return JonesVector(result[0], result[1])
    
    @classmethod
    def horizontal(cls) -> 'JonesVector':
        """Horizontal polarization."""
        return cls(1, 0)
    
    @classmethod
    def vertical(cls) -> 'JonesVector':
        """Vertical polarization."""
        return cls(0, 1)
    
    @classmethod
    def diagonal(cls) -> 'JonesVector':
        """+45 degree polarization."""
        return cls(1/np.sqrt(2), 1/np.sqrt(2))
    
    @classmethod
    def anti_diagonal(cls) -> 'JonesVector':
        """-45 degree polarization."""
        return cls(1/np.sqrt(2), -1/np.sqrt(2))
    
    @classmethod
    def right_circular(cls) -> 'JonesVector':
        """Right circular polarization."""
        return cls(1/np.sqrt(2), -1j/np.sqrt(2))
    
    @classmethod
    def left_circular(cls) -> 'JonesVector':
        """Left circular polarization."""
        return cls(1/np.sqrt(2), 1j/np.sqrt(2))


@dataclass
class JonesMatrix:
    """2x2 complex matrix representing optical element."""
    matrix: np.ndarray
    
    def __post_init__(self):
        if self.matrix.shape != (2, 2):
            raise ValueError("Jones matrix must be 2x2")
        self.matrix = self.matrix.astype(complex)
    
    def __matmul__(self, other: Union['JonesMatrix', JonesVector]):
        """Matrix multiplication."""
        if isinstance(other, JonesMatrix):
            return JonesMatrix(self.matrix @ other.matrix)
        elif isinstance(other, JonesVector):
            return other.apply(self)
        else:
            raise TypeError(f"Cannot multiply JonesMatrix with {type(other)}")
    
    @property
    def determinant(self) -> complex:
        """Matrix determinant."""
        return np.linalg.det(self.matrix)
    
    @property
    def is_unitary(self) -> bool:
        """Check if matrix is unitary (lossless)."""
        product = self.matrix @ self.matrix.conj().T
        return np.allclose(product, np.eye(2), atol=1e-10)
    
    @classmethod
    def from_elements(cls, a: complex, b: complex, c: complex, d: complex) -> 'JonesMatrix':
        """Create from matrix elements."""
        return cls(np.array([[a, b], [c, d]]))


def jones_identity() -> JonesMatrix:
    """Identity matrix (no change)."""
    return JonesMatrix(np.eye(2, dtype=complex))


def jones_linear_polarizer(angle: float = 0.0) -> JonesMatrix:
    """
    Linear polarizer at given angle.
    
    Args:
        angle: Transmission axis angle in radians
    """
    c = np.cos(angle)
    s = np.sin(angle)
    return JonesMatrix(np.array([[c**2, s*c], [s*c, s**2]]))


def jones_wave_plate(retardance: float, fast_axis: float = 0.0) -> JonesMatrix:
    """
    Wave plate (retarder).
    
    Args:
        retardance: Phase retardance in radians
        fast_axis: Fast axis angle in radians
    """
    # Phase factors
    phi = retardance / 2
    delta = retardance
    
    # Rotation to fast axis frame
    c = np.cos(fast_axis)
    s = np.sin(fast_axis)
    
    # Jones matrix for wave plate
    J = np.array([
        [np.exp(-1j*phi) * c**2 + np.exp(1j*phi) * s**2,
         (np.exp(-1j*phi) - np.exp(1j*phi)) * s * c],
        [(np.exp(-1j*phi) - np.exp(1j*phi)) * s * c,
         np.exp(-1j*phi) * s**2 + np.exp(1j*phi) * c**2]
    ])
    
    return JonesMatrix(J)


def jones_quarter_wave(fast_axis: float = 0.0) -> JonesMatrix:
    """Quarter-wave plate."""
    return jones_wave_plate(np.pi / 2, fast_axis)


def jones_half_wave(fast_axis: float = 0.0) -> JonesMatrix:
    """Half-wave plate."""
    return jones_wave_plate(np.pi, fast_axis)


def jones_rotator(angle: float) -> JonesMatrix:
    """Polarization rotator."""
    c = np.cos(angle)
    s = np.sin(angle)
    return JonesMatrix(np.array([[c, -s], [s, c]]))
