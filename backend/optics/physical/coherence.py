from dataclasses import dataclass

"""
Coherence modeling.

Implements:
- Temporal coherence
- Spatial coherence
- Interference patterns
- Fringe visibility
"""

from typing import Optional, Tuple
import numpy as np


@dataclass
class TemporalCoherence:
    """Temporal coherence properties."""

    wavelength: float = 550e-9  # m
    bandwidth: float = 1e-9  # m (spectral width)

    @property
    def coherence_length(self) -> float:
        """Coherence length."""
        return self.wavelength**2 / self.bandwidth  # L_c = lambda^2 / delta-lambda

    @property
    def coherence_time(self) -> float:
        """Coherence time."""
        return self.coherence_length / 299792458.0

    def degree_of_coherence(self, path_difference: float) -> float:
        """Degree of temporal coherence."""
        # Lorentzian line of FWHM delta-nu = c delta-lambda / lambda^2:
        # |gamma| = exp(-pi delta-nu |tau|) = exp(-pi |OPD| / L_c)
        return float(np.exp(-np.pi * abs(path_difference) / self.coherence_length))


@dataclass
class SpatialCoherence:
    """Spatial coherence properties."""

    wavelength: float = 550e-9  # m
    source_size: float = 1e-3  # m
    distance: float = 1.0  # m

    @property
    def coherence_width(self) -> float:
        """Coherence width."""
        # distance to the first zero of the coherence of a uniform circular
        # source of diameter source_size: 1.22 lambda z / D
        return 1.22 * self.wavelength * self.distance / self.source_size

    def degree_of_coherence(self, separation: float) -> float:
        """Degree of spatial coherence."""
        # van Cittert-Zernike theorem, uniform circular source of diameter D:
        # |mu| = |2 J1(v) / v|, v = pi D s / (lambda z)
        from scipy.special import j1

        v = (
            np.pi
            * self.source_size
            * abs(separation)
            / (self.wavelength * self.distance)
        )
        return 1.0 if v < 1e-12 else float(abs(2.0 * j1(v) / v))


def interference_pattern(
    wavelength: float,
    slit_separation: float,
    screen_distance: float,
    screen_width: float,
    num_points: int = 1000,
    intensity1: float = 1.0,
    intensity2: float = 1.0,
    path_difference: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate double-slit interference pattern.

    Args:
        wavelength: Wavelength (m)
        slit_separation: Slit separation (m)
        screen_distance: Distance to screen (m)
        screen_width: Width of screen (m)
        num_points: Number of points
        intensity1: Intensity from slit 1
        intensity2: Intensity from slit 2
        path_difference: Additional path difference (m)

    Returns:
        (positions, intensities)
    """
    x = np.linspace(-screen_width / 2, screen_width / 2, num_points)

    # Phase difference
    d = slit_separation
    L = screen_distance
    k = 2 * np.pi / wavelength

    # Path difference from geometry
    path_diff = d * np.sin(np.arctan2(x, L)) + path_difference
    phase_diff = k * path_diff

    # Interference pattern
    I1 = intensity1
    I2 = intensity2
    coherence = 1.0  # Assume fully coherent

    intensity = I1 + I2 + 2 * np.sqrt(I1 * I2) * coherence * np.cos(phase_diff)

    return x, intensity


def fringe_visibility(
    intensity_max: float,
    intensity_min: float,
) -> float:
    """
    Calculate fringe visibility.

    Args:
        intensity_max: Maximum intensity
        intensity_min: Minimum intensity

    Returns:
        Fringe visibility (0-1)
    """
    if intensity_max + intensity_min < 1e-15:
        return 0.0
    return (intensity_max - intensity_min) / (intensity_max + intensity_min)


def michelson_interferometer(
    wavelength: float,
    mirror_displacement: float,
    beam_diameter: float = 10e-3,
    num_points: int = 1000,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate Michelson interferometer pattern.

    Args:
        wavelength: Wavelength (m)
        mirror_displacement: Mirror displacement from equal path (m)
        beam_diameter: Beam diameter (m)
        num_points: Number of points

    Returns:
        (positions, intensities)
    """
    x = np.linspace(-beam_diameter / 2, beam_diameter / 2, num_points)

    # Path difference varies across beam due to tilt
    path_diff = 2 * mirror_displacement
    phase = 2 * np.pi * path_diff / wavelength

    # Uniform intensity across beam
    intensity = 2 * (1 + np.cos(phase)) * np.ones_like(x)

    return x, intensity


def fabry_perot_interferometer(
    wavelength: float,
    mirror_separation: float,
    reflectivity: float = 0.9,
    num_points: int = 1000,
    wavelength_range: float = 10e-9,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate Fabry-Perot interferometer transmission.

    Args:
        wavelength: Center wavelength (m)
        mirror_separation: Mirror separation (m)
        reflectivity: Mirror reflectivity
        num_points: Number of points
        wavelength_range: Wavelength scan range (m)

    Returns:
        (wavelengths, transmission)
    """
    wavelengths = np.linspace(
        wavelength - wavelength_range / 2, wavelength + wavelength_range / 2, num_points
    )

    # Phase difference
    phase = 2 * np.pi * 2 * mirror_separation / wavelengths

    # Finesse
    F = 4 * reflectivity / (1 - reflectivity) ** 2

    # Airy function
    transmission = 1 / (1 + F * np.sin(phase / 2) ** 2)

    return wavelengths, transmission
