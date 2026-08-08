"""
Optical materials and refractive index data.

This module provides refractive index data for common optical glasses.
For the MVP, refractive indices are given at a reference wavelength
(587.6 nm, the e-line of the Sun / Fraunhofer e-line).

In future phases, the Sellmeier equation will be used to calculate
wavelength-dependent refractive indices.

Reference wavelength: 587.6 nm (Fraunhofer e-line, helium d-line)
"""

import math

# Refractive indices at 587.6 nm (Fraunhofer e-line)
# Source: Schott Glass catalog, Ohara catalog
REFRACTIVE_INDICES: dict[str, float] = {
    "air": 1.0000,
    "N-BK7": 1.5168,       # Schott N-BK7 (borosilicate crown glass)
    "N-SF2": 1.6477,       # Schott N-SF2 (dense flint)
    "N-SF5": 1.6727,       # Schott N-SF5 (dense flint)
    "N-SF11": 1.7880,      # Schott N-SF11 (extra-dense flint)
    "N-LAFN": 1.7440,      # Schott N-LAFN (lanthanum flint)
    "N-SF10": 1.7283,      # Schott N-SF10 (dense flint)
    "N-BAF10": 1.6700,     # Schott N-BAF10 (barium flint)
    "N-LAK10": 1.6030,     # Schott N-LAK10 (lanthanum crown)
    "N-SF6": 1.7900,       # Schott N-SF6 (extra-dense flint)
    "PMMA": 1.4910,        # Polymethyl methacrylate (acrylic)
    "Polycarbonate": 1.5860,
    "FusedSilica": 1.4585,  # Fused silica (SiO2)
}

# Sellmeier coefficients for common glasses
# Sellmeier equation: n^2 = 1 + sum(B_i * lambda^2 / (lambda^2 - C_i))
# where lambda is in micrometers
SELLMEIER_COEFFICIENTS: dict[str, list[tuple[float, float]]] = {
    "N-BK7": [
        (1.03961212, 0.00600069867),
        (0.231792034, 0.00170883814),
        (1.01047410, 1039.621020),
    ],
    "N-SF11": [
        (1.71562519, 0.0129603622),
        (0.310689651, 0.0606487171),
        (1.51443002, 132.703655),
    ],
    "FusedSilica": [
        (0.69616670, 0.00467914826),
        (0.40794260, 0.0135120631),
        (0.89741331, 97.9340024),
    ],
}


def refractive_index(material: str, wavelength: float = 587.6e-9) -> float:
    """
    Get the refractive index of a material at a given wavelength.

    For the MVP, this returns the refractive index at the reference
    wavelength (587.6 nm). In future phases, the Sellmeier equation
    will be used for wavelength-dependent indices.

    Args:
        material: Material name (e.g., "N-BK7", "air").
        wavelength: Wavelength in meters (currently ignored for MVP).

    Returns:
        Refractive index (dimensionless).

    Raises:
        ValueError: If the material is not found.

    Examples:
        >>> refractive_index("N-BK7")
        1.5168
        >>> refractive_index("air")
        1.0
    """
    if material not in REFRACTIVE_INDICES:
        raise ValueError(
            f"Unknown material: '{material}'. "
            f"Known materials: {list(REFRACTIVE_INDICES.keys())}"
        )
    return REFRACTIVE_INDICES[material]


def refractive_index_sellmeier(material: str, wavelength: float) -> float:
    """
    Calculate the refractive index using the Sellmeier equation.

    Sellmeier equation: n^2 = 1 + sum(B_i * lambda^2 / (lambda^2 - C_i))

    Args:
        material: Material name with Sellmeier coefficients.
        wavelength: Wavelength in meters.

    Returns:
        Refractive index (dimensionless).

    Raises:
        ValueError: If the material has no Sellmeier coefficients.
    """
    if material not in SELLMEIER_COEFFICIENTS:
        raise ValueError(
            f"No Sellmeier coefficients for material: '{material}'. "
            f"Available: {list(SELLMEIER_COEFFICIENTS.keys())}"
        )

    # Convert wavelength from meters to micrometers
    lam_um = wavelength * 1e6
    lam_sq = lam_um ** 2

    n_sq = 1.0
    for B, C in SELLMEIER_COEFFICIENTS[material]:
        n_sq += B * lam_sq / (lam_sq - C)

    return math.sqrt(n_sq)
