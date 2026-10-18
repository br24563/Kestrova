"""
Chromatic aberration analysis (paraxial).

    - Longitudinal (axial) colour: shift of the paraxial image position
      between two wavelengths.
    - Lateral colour (chromatic difference of magnification): difference of
      the paraxial chief-ray heights of two wavelengths, both measured in
      the paraxial image plane of the reference wavelength.

Indices come from each material's published dispersion formula
(see :mod:`optics.materials`). All values are in SI base units.
"""

from typing import Optional

from .models import OpticalSystem
from .materials import F_LINE, D_LINE, C_LINE
from . import raytrace as rt


def image_position_at_wavelength(system: OpticalSystem, wavelength: float) -> float:
    """Paraxial image position (z, meters) at a wavelength."""
    return rt.first_order(system, wavelength).image_z


def image_height_at_wavelength(system: OpticalSystem, wavelength: float) -> float:
    """Paraxial image height (meters) in that wavelength's own image plane."""
    return rt.first_order(system, wavelength).image_height


def _chief_height_at(system: OpticalSystem, wavelength: float, z_plane: float) -> float:
    seq = rt.build_sequence(system, wavelength)
    fo = rt.first_order(system, seq=seq)
    c = fo.chief
    return c.y[-1] + c.u_after[-1] * (z_plane - seq.surfaces[-1].z)


def longitudinal_chromatic_aberration(
    system: OpticalSystem,
    wavelength_blue: float = F_LINE,
    wavelength_red: float = C_LINE,
) -> float:
    """
    Axial colour: image position at the blue wavelength minus that at the red
    wavelength, along the direction of travel (negative = blue focuses
    first, the usual under-corrected case).
    """
    seq = rt.build_sequence(system, wavelength_blue)
    d = seq.image_direction
    return (image_position_at_wavelength(system, wavelength_blue)
            - image_position_at_wavelength(system, wavelength_red)) * d


def lateral_chromatic_aberration(
    system: OpticalSystem,
    wavelength_blue: float = F_LINE,
    wavelength_red: float = C_LINE,
    reference_wavelength: float = D_LINE,
) -> float:
    """
    Lateral colour: chief-ray height at the blue wavelength minus that at the
    red wavelength, both in the reference wavelength's paraxial image plane.
    """
    z_ref = image_position_at_wavelength(system, reference_wavelength)
    return (_chief_height_at(system, wavelength_blue, z_ref)
            - _chief_height_at(system, wavelength_red, z_ref))


def chromatic_aberration_analysis(
    system: OpticalSystem,
    wavelengths: Optional[list[float]] = None,
) -> dict:
    """
    Image position and height at each wavelength plus the axial and lateral
    colour between the first and last wavelengths (default F, d, C).

    Returns keys "wavelengths", "image_positions", "image_heights", "lca",
    "tca" (lateral colour, in the middle wavelength's image plane).
    """
    if wavelengths is None:
        wavelengths = [F_LINE, D_LINE, C_LINE]
    positions = [image_position_at_wavelength(system, w) for w in wavelengths]
    heights = [image_height_at_wavelength(system, w) for w in wavelengths]
    ref = wavelengths[len(wavelengths) // 2]
    return {
        "wavelengths": wavelengths,
        "image_positions": positions,
        "image_heights": heights,
        "lca": longitudinal_chromatic_aberration(system, wavelengths[0], wavelengths[-1]),
        "tca": lateral_chromatic_aberration(system, wavelengths[0], wavelengths[-1], ref),
    }
