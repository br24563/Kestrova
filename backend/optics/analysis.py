"""
Optical analysis calculations.

This module computes the key optical properties of an optical system:
    - Effective focal length
    - Magnification
    - Image and object distances
    - F-number
    - Numerical aperture
    - RMS spot radius
    - Spot diagram points

All calculations use the paraxial (first-order) approximation.
All values are in SI base units (meters, radians).

Sign convention (optics, used in optical design software):
    - Object distance (s): NEGATIVE if object is to the LEFT of the lens.
    - Image distance (s'): NEGATIVE if image is to the LEFT of the lens.
    - Image distance (s'): POSITIVE if image is to the RIGHT of the lens.
    - Magnification: m = s' / s (negative = inverted).
"""

import math
import numpy as np
from typing import Optional

from .models import (
    OpticalSystem, ThinLens, ThickLens, AnalysisResult, RayTraceResult,
)
from .lenses import (
    RayVector, propagation_matrix, thin_lens_matrix, system_matrix,
    f_number as calc_f_number, numerical_aperture as calc_na,
)
from .rays import (
    trace_system, calculate_spot_diagram,
    calculate_paraxial_image_position, calculate_paraxial_image_height,
)
from .surfaces import lensmaker_focal_length
from .materials import refractive_index


def _lens_focal_length(comp) -> float:
    """
    Return the focal length of a lens component (thin or thick).

    For a ThickLens, the focal length is computed using the lensmaker's
    equation. For a ThinLens, it is the stored focal length.

    Args:
        comp: A ThinLens or ThickLens component.

    Returns:
        Focal length (meters).
    """
    if isinstance(comp, ThickLens):
        n = refractive_index(comp.material)
        return lensmaker_focal_length(comp.radius1, comp.radius2, comp.thickness, n)
    return comp.focal_length


# ---------------------------------------------------------------------------
# System Matrix and Effective Focal Length
# ---------------------------------------------------------------------------

def build_system_matrix(system: OpticalSystem) -> np.ndarray:
    """
    Build the ray transfer (ABCD) matrix for the lens system.

    The matrix includes only the lenses and the propagation between them,
    NOT the propagation from the object to the first lens or from the
    last lens to the image plane.

    Args:
        system: The optical system.

    Returns:
        2x2 system matrix as a NumPy array.
    """
    lenses = sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )

    if not lenses:
        return np.eye(2)

    matrices: list[np.ndarray] = []

    for i, lens in enumerate(lenses):
        # Add the lens matrix
        matrices.append(thin_lens_matrix(_lens_focal_length(lens)))

        # Add propagation to the next lens (if not the last)
        if i < len(lenses) - 1:
            d = lenses[i + 1].position - lens.position
            matrices.append(propagation_matrix(d))

    return system_matrix(matrices)


def effective_focal_length(system: OpticalSystem) -> float:
    """
    Calculate the effective focal length of the optical system.

    Uses the system matrix method: f_eff = -1 / C, where C is the
    [1, 0] element of the system matrix.

    Args:
        system: The optical system.

    Returns:
        Effective focal length (meters). Positive for a positive system.

    Examples:
        >>> # Single 50mm lens
        >>> # f_eff = 50mm
        >>> # Two 50mm lenses, 0mm apart => f_eff = 25mm
    """
    M = build_system_matrix(system)
    C = M[1, 0]

    if abs(C) < 1e-15:
        raise ValueError("System is afocal (infinite effective focal length).")

    return -1.0 / C


def back_focal_length(system: OpticalSystem) -> float:
    """
    Calculate the back focal length of the system.

    The back focal length is the distance from the last lens to the
    back focal point (where parallel rays converge).

    BFL = D / C, where M = [[A, B], [C, D]] is the system matrix.

    Args:
        system: The optical system.

    Returns:
        Back focal length (meters).
    """
    M = build_system_matrix(system)
    C = M[1, 0]
    D = M[1, 1]

    if abs(C) < 1e-15:
        raise ValueError("System is afocal: back focal length is undefined.")

    return D / C


def front_focal_length(system: OpticalSystem) -> float:
    """
    Calculate the front focal length of the system.

    The front focal length is the distance from the first lens to the
    front focal point.

    FFL = -A / C, where M = [[A, B], [C, D]] is the system matrix.

    Args:
        system: The optical system.

    Returns:
        Front focal length (meters).
    """
    M = build_system_matrix(system)
    A = M[0, 0]
    C = M[1, 0]

    if abs(C) < 1e-15:
        raise ValueError("System is afocal: front focal length is undefined.")

    return -A / C


# ---------------------------------------------------------------------------
# Magnification
# ---------------------------------------------------------------------------

def system_magnification(system: OpticalSystem) -> float:
    """
    Calculate the transverse magnification of the optical system.

    m = h_image / h_object

    A negative magnification means the image is inverted.

    Args:
        system: The optical system.

    Returns:
        Magnification (dimensionless).
    """
    obj = system.object
    image_height = calculate_paraxial_image_height(system)

    if abs(obj.height) < 1e-15:
        return 0.0

    return image_height / obj.height


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------

def object_distance(system: OpticalSystem) -> float:
    """
    Calculate the object distance from the first lens.

    Sign convention (optics):
        - Returns NEGATIVE if the object is to the LEFT of the first lens.
        - Returns POSITIVE if the object is to the RIGHT of the first lens.

    Args:
        system: The optical system.

    Returns:
        Object distance (meters). Negative if object is to the left
        of the first lens.
    """
    lenses = sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )
    if not lenses:
        return 0.0

    first_lens = lenses[0]
    return system.object.position - first_lens.position


def image_distance(system: OpticalSystem) -> float:
    """
    Calculate the image distance from the last lens.

    Sign convention (optics):
        - Returns POSITIVE if the image is to the RIGHT of the last lens.
        - Returns NEGATIVE if the image is to the LEFT of the last lens.

    Args:
        system: The optical system.

    Returns:
        Image distance (meters). Positive if image is to the right
        of the last lens.
    """
    lenses = sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )
    if not lenses:
        return 0.0

    last_lens = lenses[-1]
    image_pos = calculate_paraxial_image_position(system)
    return image_pos - last_lens.position


def working_distance(system: OpticalSystem) -> float:
    """
    Calculate the working distance (from last lens to image plane).

    Args:
        system: The optical system.

    Returns:
        Working distance (meters).
    """
    lenses = sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )
    if not lenses:
        return 0.0

    last_lens = lenses[-1]
    return system.image_plane.position - last_lens.position


# ---------------------------------------------------------------------------
# F-number and Numerical Aperture
# ---------------------------------------------------------------------------

def system_f_number(system: OpticalSystem) -> float:
    """
    Calculate the F-number of the optical system.

    F/# = f_eff / D

    where f_eff is the effective focal length and D is the aperture
    diameter of the first lens.

    Args:
        system: The optical system.

    Returns:
        F-number (dimensionless).
    """
    f_eff = effective_focal_length(system)

    lenses = sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )
    if not lenses:
        return float('inf')

    first_lens = lenses[0]
    D = first_lens.aperture_diameter

    if D == 0:
        return float('inf')

    return calc_f_number(f_eff, D)


def system_numerical_aperture(system: OpticalSystem) -> float:
    """
    Calculate the numerical aperture of the optical system.

    NA = n * sin(theta)

    where theta is the half-angle of the cone of light at the first lens,
    and n is the refractive index of the medium (air = 1.0).

    Args:
        system: The optical system.

    Returns:
        Numerical aperture (dimensionless).
    """
    lenses = sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )
    if not lenses:
        return 0.0

    first_lens = lenses[0]
    D = first_lens.aperture_diameter
    s = object_distance(system)

    if abs(s) < 1e-15:
        return 0.0

    # Half-angle: theta = arctan(D/2 / |s|)
    # Use absolute value of s since it's a geometric angle
    theta = math.atan(D / 2.0 / abs(s))
    n = refractive_index("air")

    return calc_na(n, theta)


# ---------------------------------------------------------------------------
# Full Analysis
# ---------------------------------------------------------------------------

def analyze_system(
    system: OpticalSystem,
    num_rays: Optional[int] = None,
    aperture_fraction: Optional[float] = None,
) -> AnalysisResult:
    """
    Perform a full optical analysis of the system.

    This function calculates all key optical properties and returns
    them as an AnalysisResult.

    Args:
        system: The optical system.
        num_rays: Number of rays to trace for spot diagram.
        aperture_fraction: Fraction of aperture to use.

    Returns:
        AnalysisResult with all calculated properties.
    """
    # Trace rays for spot diagram
    trace_result = trace_system(system, num_rays, aperture_fraction)

    # Calculate spot diagram
    spot_heights, rms_spot = calculate_spot_diagram(
        trace_result.ray_paths,
        trace_result.image_position,
    )

    # Calculate properties
    f_eff = effective_focal_length(system)
    mag = system_magnification(system)
    img_dist = image_distance(system)
    obj_dist = object_distance(system)
    f_num = system_f_number(system)
    na = system_numerical_aperture(system)

    lenses = sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )
    aperture_diam = lenses[0].aperture_diameter if lenses else 0.0
    wd = working_distance(system)

    # Determine if image is real
    # Image is real if it's on the opposite side of the last lens from the object
    # In optics convention: image is real if s' > 0 (to the right of the last lens)
    is_real = img_dist > 0

    # Image is inverted if magnification is negative
    is_inverted = mag < 0

    return AnalysisResult(
        effective_focal_length=f_eff,
        magnification=mag,
        image_distance=img_dist,
        object_distance=obj_dist,
        f_number=f_num,
        numerical_aperture=na,
        aperture_diameter=aperture_diam,
        working_distance=wd,
        rms_spot_radius=rms_spot,
        spot_points=[[y, trace_result.image_position] for y in spot_heights],
        is_image_real=is_real,
        is_image_inverted=is_inverted,
    )