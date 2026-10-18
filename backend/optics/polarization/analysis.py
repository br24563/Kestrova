"""
Polarization analysis tools.

Provides:
- Polarization ray tracing
- Polarization aberration analysis
- Pupil polarization maps
"""

from typing import Optional, Tuple
from dataclasses import dataclass
import numpy as np
from .jones import JonesVector, JonesMatrix, jones_identity
from .stokes import StokesVector


@dataclass
class PolarizationTrace:
    """Result of polarization ray tracing."""

    wavelength: float
    pupil_x: float
    pupil_y: float
    jones_vector: JonesVector
    transmitted_power: float
    phase: float


def _element_at(element, px, py):
    """An element may be a JonesMatrix or a function (px, py) -> JonesMatrix."""
    return element(px, py) if callable(element) else element


def polarization_aberrance(
    system_elements: list,
    wavelength: float = 550e-9,
    num_rays: int = 100,
    pupil_size: float = 1.0,
    seed: Optional[int] = 0,
    input_state: Optional[JonesVector] = None,
) -> list[PolarizationTrace]:
    """
    Calculate polarization aberrations through optical system.

    Args:
        system_elements: JonesMatrix elements, or functions (px, py) ->
            JonesMatrix for pupil-dependent elements (constant matrices give
            a uniform result over the pupil)
        wavelength: Wavelength (m)
        num_rays: Number of pupil sample points
        pupil_size: Pupil radius (normalized)

    Returns:
        List of polarization trace results
    """
    results = []
    rng = np.random.default_rng(seed)
    for i in range(num_rays):
        # uniform random pupil point
        r = np.sqrt(rng.uniform(0, 1)) * pupil_size
        theta = rng.uniform(0, 2 * np.pi)
        px = r * np.cos(theta)
        py = r * np.sin(theta)
        jones = input_state or JonesVector.horizontal()
        for element in system_elements:
            jones = _element_at(element, px, py) @ jones

        results.append(
            PolarizationTrace(
                wavelength=wavelength,
                pupil_x=px,
                pupil_y=py,
                jones_vector=jones,
                transmitted_power=jones.intensity,
                phase=jones.phase_difference,
            )
        )

    return results


def pupil_polarization_map(
    system_elements: list,
    wavelength: float = 550e-9,
    grid_size: int = 20,
    pupil_size: float = 1.0,
) -> dict:
    """
    Calculate polarization map over pupil.

    Args:
        system_elements: List of Jones matrices
        wavelength: Wavelength
        grid_size: Grid resolution
        pupil_size: Pupil radius

    Returns:
        Dictionary with polarization maps
    """
    x = np.linspace(-pupil_size, pupil_size, grid_size)
    y = np.linspace(-pupil_size, pupil_size, grid_size)
    X, Y = np.meshgrid(x, y)

    # Initialize maps
    intensity_map = np.zeros((grid_size, grid_size))
    phase_map = np.zeros((grid_size, grid_size))
    azimuth_map = np.zeros((grid_size, grid_size))
    ellipticity_map = np.zeros((grid_size, grid_size))
    dop_map = np.zeros((grid_size, grid_size))

    for i in range(grid_size):
        for j in range(grid_size):
            # Check if within pupil
            r = np.sqrt(X[i, j] ** 2 + Y[i, j] ** 2)
            if r > pupil_size:
                continue

            jones = JonesVector.horizontal()
            for element in system_elements:
                jones = _element_at(element, X[i, j], Y[i, j]) @ jones

            # Store results
            intensity_map[i, j] = jones.intensity
            phase_map[i, j] = jones.phase_difference
            azimuth_map[i, j] = jones.azimuth
            ellipticity_map[i, j] = jones.ellipticity

            # Degree of polarization
            stokes = jones.to_stokes()
            dop_map[i, j] = stokes.dop

    return {
        "x": x,
        "y": y,
        "intensity": intensity_map,
        "phase": phase_map,
        "azimuth": azimuth_map,
        "ellipticity": ellipticity_map,
        "dop": dop_map,
    }


def diattenuation_map(
    jones_matrix_func,
    grid_size: int = 20,
    pupil_size: float = 1.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calculate diattenuation map.

    Diattenuation is the polarization-dependent transmission.

    Args:
        jones_matrix_func: Function that takes (px, py) and returns JonesMatrix
        grid_size: Grid resolution
        pupil_size: Pupil radius

    Returns:
        (x, y, diattenuation_map)
    """
    x = np.linspace(-pupil_size, pupil_size, grid_size)
    y = np.linspace(-pupil_size, pupil_size, grid_size)
    X, Y = np.meshgrid(x, y)

    diattenuation = np.zeros((grid_size, grid_size))

    for i in range(grid_size):
        for j in range(grid_size):
            r = np.sqrt(X[i, j] ** 2 + Y[i, j] ** 2)
            if r > pupil_size:
                continue

            # Get Jones matrix at this pupil point
            J = jones_matrix_func(X[i, j], Y[i, j])

            # D = (Tmax - Tmin)/(Tmax + Tmin), the extreme intensity
            # transmittances being the squared singular values of J.
            sv = np.linalg.svd(J.matrix, compute_uv=False)
            tmax, tmin = sv[0] ** 2, sv[-1] ** 2
            if tmax + tmin > 0:
                diattenuation[i, j] = (tmax - tmin) / (tmax + tmin)

    return x, y, diattenuation


def retardance_map(
    jones_matrix_func,
    grid_size: int = 20,
    pupil_size: float = 1.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calculate retardance map.

    Retardance is the phase difference between the eigenpolarizations (exact
    for homogeneous elements, whose eigenvectors are orthogonal).

    Args:
        jones_matrix_func: Function that takes (px, py) and returns JonesMatrix
        grid_size: Grid resolution
        pupil_size: Pupil radius

    Returns:
        (x, y, retardance_map)
    """
    x = np.linspace(-pupil_size, pupil_size, grid_size)
    y = np.linspace(-pupil_size, pupil_size, grid_size)
    X, Y = np.meshgrid(x, y)

    retardance = np.zeros((grid_size, grid_size))

    for i in range(grid_size):
        for j in range(grid_size):
            r = np.sqrt(X[i, j] ** 2 + Y[i, j] ** 2)
            if r > pupil_size:
                continue

            # Get Jones matrix
            J = jones_matrix_func(X[i, j], Y[i, j])

            # Retardance of a homogeneous element: phase difference of the
            # eigenvalues, in [0, pi].
            ev = np.linalg.eigvals(J.matrix)
            if abs(ev[0]) > 1e-15 and abs(ev[1]) > 1e-15:
                retardance[i, j] = abs(np.angle(ev[0] / ev[1]))

    return x, y, retardance
