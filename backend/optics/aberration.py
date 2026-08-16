"""
Chromatic aberration analysis.

This module analyzes how the image position and height vary with
wavelength (chromatic aberration). It builds on the wavelength-dependent
refractive index (Sellmeier equation) to compute:

    - Longitudinal chromatic aberration (LCA): variation of image
      position with wavelength.
    - Lateral chromatic aberration (TCA): variation of image height
      with wavelength.

All values are in SI base units (meters, radians).
"""

from typing import Optional

from .models import OpticalSystem
from .rays import (
    calculate_paraxial_image_position, calculate_paraxial_image_height,
)


# Standard wavelengths for chromatic analysis (meters)
# F line (blue), d line (green/yellow), C line (red)
F_LINE = 486.1e-9
D_LINE = 587.6e-9
C_LINE = 656.3e-9


def image_position_at_wavelength(
    system: OpticalSystem, wavelength: float
) -> float:
    """
    Calculate the paraxial image position at a specific wavelength.

    Args:
        system: The optical system.
        wavelength: Wavelength in meters.

    Returns:
        Image position along the z-axis (meters).
    """
    return calculate_paraxial_image_position(system, wavelength)


def image_height_at_wavelength(
    system: OpticalSystem, wavelength: float
) -> float:
    """
    Calculate the paraxial image height at a specific wavelength.

    Args:
        system: The optical system.
        wavelength: Wavelength in meters.

    Returns:
        Image height (meters).
    """
    return calculate_paraxial_image_height(system, wavelength)


def longitudinal_chromatic_aberration(
    system: OpticalSystem,
    wavelength_blue: float = F_LINE,
    wavelength_red: float = C_LINE,
) -> float:
    """
    Calculate the longitudinal chromatic aberration (LCA).

    LCA is the difference in image position between the blue and red
    wavelengths. A positive value means blue focuses closer to the lens
    than red (normal dispersion).

    Args:
        system: The optical system.
        wavelength_blue: Blue wavelength (meters).
        wavelength_red: Red wavelength (meters).

    Returns:
        LCA in meters (image position at blue minus image position at red).
    """
    pos_blue = image_position_at_wavelength(system, wavelength_blue)
    pos_red = image_position_at_wavelength(system, wavelength_red)
    return pos_blue - pos_red


def lateral_chromatic_aberration(
    system: OpticalSystem,
    wavelength_blue: float = F_LINE,
    wavelength_red: float = C_LINE,
) -> float:
    """
    Calculate the lateral chromatic aberration (TCA).

    TCA is the difference in image height between the blue and red
    wavelengths. A nonzero value means different colors form images at
    different heights (color fringing).

    Args:
        system: The optical system.
        wavelength_blue: Blue wavelength (meters).
        wavelength_red: Red wavelength (meters).

    Returns:
        TCA in meters (image height at blue minus image height at red).
    """
    height_blue = image_height_at_wavelength(system, wavelength_blue)
    height_red = image_height_at_wavelength(system, wavelength_red)
    return height_blue - height_red


def chromatic_aberration_analysis(
    system: OpticalSystem,
    wavelengths: Optional[list[float]] = None,
) -> dict:
    """
    Perform a full chromatic aberration analysis.

    Computes the image position and height at each wavelength, plus the
    longitudinal and lateral chromatic aberration between the extreme
    wavelengths.

    Args:
        system: The optical system.
        wavelengths: List of wavelengths in meters. If None, uses the
            standard F, d, C lines.

    Returns:
        Dict with keys:
            - "wavelengths": list of wavelengths (meters)
            - "image_positions": list of image positions (meters)
            - "image_heights": list of image heights (meters)
            - "lca": longitudinal chromatic aberration (meters)
            - "tca": lateral chromatic aberration (meters)
    """
    if wavelengths is None:
        wavelengths = [F_LINE, D_LINE, C_LINE]

    positions = [image_position_at_wavelength(system, w) for w in wavelengths]
    heights = [image_height_at_wavelength(system, w) for w in wavelengths]

    lca = positions[0] - positions[-1]
    tca = heights[0] - heights[-1]

    return {
        "wavelengths": wavelengths,
        "image_positions": positions,
        "image_heights": heights,
        "lca": lca,
        "tca": tca,
    }