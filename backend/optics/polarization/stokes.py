"""
Stokes parameters for polarization analysis.

Stokes parameters provide a complete description of polarization state,
including partially polarized and unpolarized light.
"""

from typing import Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class StokesVector:
    """4-element Stokes vector."""
    S0: float  # Total intensity
    S1: float  # Horizontal vs vertical
    S2: float  # +45 vs -45
    S3: float  # Right vs left circular
    
    def __post_init__(self):
        self.vector = np.array([self.S0, self.S1, self.S2, self.S3])
    
    @property
    def intensity(self) -> float:
        """Total intensity."""
        return self.S0
    
    @property
    def dop(self) -> float:
        """Degree of polarization."""
        if self.S0 > 0:
            return np.sqrt(self.S1**2 + self.S2**2 + self.S3**2) / self.S0
        return 0.0
    
    @property
    def dolp(self) -> float:
        """Degree of linear polarization."""
        if self.S0 > 0:
            return np.sqrt(self.S1**2 + self.S2**2) / self.S0
        return 0.0
    
    @property
    def docp(self) -> float:
        """Degree of circular polarization."""
        if self.S0 > 0:
            return abs(self.S3) / self.S0
        return 0.0
    
    @property
    def azimuth(self) -> float:
        """Polarization azimuth angle."""
        return 0.5 * np.arctan2(self.S2, self.S1)
    
    @property
    def ellipticity(self) -> float:
        """Ellipticity angle."""
        linear = np.sqrt(self.S1**2 + self.S2**2)
        if linear > 0:
            return 0.5 * np.arcsin(self.S3 / (self.S0 * self.dop))
        return 0.0
    
    def is_physical(self) -> bool:
        """Check if Stokes vector is physically valid."""
        return self.S0 >= 0 and self.dop <= 1.0 + 1e-10
    
    def apply(self, matrix) -> 'StokesVector':
        """Apply Mueller matrix."""
        from .mueller import MuellerMatrix
        if isinstance(matrix, MuellerMatrix):
            result = matrix.matrix @ self.vector
            return StokesVector(result[0], result[1], result[2], result[3])
        raise TypeError(f"Expected MuellerMatrix, got {type(matrix)}")
    
    def to_jones(self):
        """Convert to Jones vector (only for fully polarized light)."""
        from .jones import JonesVector
        if abs(self.dop - 1.0) > 0.01:
            raise ValueError("Cannot convert partially polarized light to Jones vector")
        
        # Calculate Jones components
        Ex = np.sqrt((self.S0 + self.S1) / 2)
        if Ex < 1e-15:
            Ey = np.sqrt(self.S0 / 2)
            phase = np.arctan2(self.S3, self.S2)
            return JonesVector(0, Ey * np.exp(1j * phase))
        
        ratio = (self.S2 + 1j * self.S3) / (self.S0 + self.S1)
        Ey = Ex * ratio
        
        return JonesVector(Ex, Ey)


def stokes_unpolarized(intensity: float = 1.0) -> StokesVector:
    """Unpolarized light."""
    return StokesVector(intensity, 0, 0, 0)


def stokes_horizontal(intensity: float = 1.0) -> StokesVector:
    """Horizontally polarized light."""
    return StokesVector(intensity, intensity, 0, 0)


def stokes_vertical(intensity: float = 1.0) -> StokesVector:
    """Vertically polarized light."""
    return StokesVector(intensity, -intensity, 0, 0)


def stokes_linear(intensity: float = 1.0, angle: float = 0.0) -> StokesVector:
    """Linearly polarized light at given angle."""
    return StokesVector(
        intensity,
        intensity * np.cos(2 * angle),
        intensity * np.sin(2 * angle),
        0
    )


def stokes_diagonal(intensity: float = 1.0) -> StokesVector:
    """+45 degree linearly polarized light."""
    return stokes_linear(intensity, np.pi / 4)


def stokes_anti_diagonal(intensity: float = 1.0) -> StokesVector:
    """-45 degree linearly polarized light."""
    return stokes_linear(intensity, -np.pi / 4)


def stokes_right_circular(intensity: float = 1.0) -> StokesVector:
    """Right circularly polarized light."""
    return StokesVector(intensity, 0, 0, intensity)


def stokes_left_circular(intensity: float = 1.0) -> StokesVector:
    """Left circularly polarized light."""
    return StokesVector(intensity, 0, 0, -intensity)


def degree_of_polarization(S: StokesVector) -> float:
    """Calculate degree of polarization."""
    return S.dop


def degree_of_linear_polarization(S: StokesVector) -> float:
    """Calculate degree of linear polarization."""
    return S.dolp


def degree_of_circular_polarization(S: StokesVector) -> float:
    """Calculate degree of circular polarization."""
    return S.docp
