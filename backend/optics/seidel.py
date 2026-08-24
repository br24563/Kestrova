"""
Seidel (third-order) monochromatic aberration analysis.

The paraxial tracer produces zero third-order aberrations by definition,
so this module uses the exact real-ray tracer (``real_rays.py``) to
measure the five monochromatic Seidel aberrations directly from ray
intercepts:

    - Spherical aberration (SA): longitudinal and transverse
    - Coma
    - Astigmatism
    - Field curvature (Petzval + sagittal/tangential)
    - Distortion

Method
------
For each aberration we trace a small set of real rays and compare their
behavior to the paraxial prediction:

    - **Spherical aberration**: an on-axis marginal ray (aperture edge)
      crosses the axis at a different z than the paraxial image. The
      longitudinal SA is that z difference; the transverse SA is the
      ray height at the paraxial image plane.
    - **Coma**: for an off-axis object, the image height varies with
      aperture height. Coma is measured as the difference between the
      real image height of an upper marginal ray and the paraxial image
      height, normalized by the aperture.
    - **Astigmatism**: for an off-axis object, the tangential (meridional)
      and sagittal rays focus at different z positions. Astigmatism is
      the difference between those two focal positions.
    - **Field curvature**: the average of the sagittal and tangential
      focal positions minus the paraxial image position.
    - **Distortion**: the difference between the real image height of the
      chief ray and the paraxial image height, relative to the paraxial
      image height.

All values are in SI base units (meters, radians).
"""

import math
from typing import Optional

from .models import OpticalSystem, Ray
from .rays import calculate_paraxial_image_position, calculate_paraxial_image_height
from .real_rays import (
    trace_real_ray, real_intercept_at_plane, real_axis_crossing,
    real_ray_crossing,
)


# ---------------------------------------------------------------------------
# Ray helpers
# ---------------------------------------------------------------------------

def _make_ray(system: OpticalSystem, y: float, theta: float) -> Ray:
    """Create a ray starting at the object with the given height/angle."""
    return Ray(
        y=y,
        theta=theta,
        z=system.object.position,
        wavelength=system.analysis_settings.wavelength,
        ray_type="fill",
    )


def _first_lens_aperture(system: OpticalSystem) -> float:
    """Return the aperture diameter of the first lens (or 0 if none)."""
    from .models import ThinLens, ThickLens
    lenses = [
        c for c in system.components
        if isinstance(c, (ThinLens, ThickLens))
    ]
    if not lenses:
        return 0.0
    first = min(lenses, key=lambda l: l.position)
    return getattr(first, "aperture_diameter", 0.0)


def _object_to_lens_angle(system: OpticalSystem, y_at_lens: float, obj_y: float) -> float:
    """Angle (radians) from an object point to a point on the first lens."""
    from .models import ThinLens, ThickLens
    lenses = [
        c for c in system.components
        if isinstance(c, (ThinLens, ThickLens))
    ]
    if not lenses:
        return 0.0
    first = min(lenses, key=lambda l: l.position)
    d = first.position - system.object.position
    if abs(d) < 1e-15:
        return 0.0
    return math.atan((y_at_lens - obj_y) / d)


# ---------------------------------------------------------------------------
# Spherical Aberration
# ---------------------------------------------------------------------------

def spherical_aberration(system: OpticalSystem) -> dict:
    """
    Measure longitudinal and transverse spherical aberration.

    Traces an on-axis marginal ray (through the aperture edge) and
    compares its axis crossing to the paraxial image position.

    Returns:
        Dict with:
            - "longitudinal": z difference (m) between marginal ray axis
              crossing and paraxial image (positive = marginal focuses
              closer to the lens, i.e. under-corrected)
            - "transverse": ray height (m) of the marginal ray at the
              paraxial image plane
    """
    D = _first_lens_aperture(system)
    if D <= 0:
        return {"longitudinal": 0.0, "transverse": 0.0}

    paraxial_z = calculate_paraxial_image_position(system)

    # On-axis marginal ray through the top of the aperture
    theta = _object_to_lens_angle(system, D / 2.0, 0.0)
    ray = _make_ray(system, 0.0, theta)
    path = trace_real_ray(system, ray)

    axis_z = real_axis_crossing(path)
    if axis_z is None:
        axis_z = paraxial_z

    transverse = real_intercept_at_plane(path, paraxial_z)

    return {
        "longitudinal": paraxial_z - axis_z,
        "transverse": transverse,
    }


# ---------------------------------------------------------------------------
# Coma
# ---------------------------------------------------------------------------

def coma(system: OpticalSystem) -> float:
    """
    Measure coma for an off-axis object.

    Coma is the variation of image height with aperture. We trace the
    upper and lower marginal rays (through the top and bottom of the
    aperture) and compare their image heights. Spherical aberration is
    symmetric (identical for both marginal rays), so it cancels in the
    difference, isolating the coma contribution.

    Returns:
        Coma magnitude (meters) at the paraxial image plane.
    """
    D = _first_lens_aperture(system)
    if D <= 0:
        return 0.0

    obj_h = system.object.height
    paraxial_z = calculate_paraxial_image_position(system)

    # Upper marginal ray: object top through aperture top
    theta_up = _object_to_lens_angle(system, D / 2.0, obj_h)
    ray_up = _make_ray(system, obj_h, theta_up)
    path_up = trace_real_ray(system, ray_up)
    real_h_up = real_intercept_at_plane(path_up, paraxial_z)

    # Lower marginal ray: object top through aperture bottom
    theta_lo = _object_to_lens_angle(system, -D / 2.0, obj_h)
    ray_lo = _make_ray(system, obj_h, theta_lo)
    path_lo = trace_real_ray(system, ray_lo)
    real_h_lo = real_intercept_at_plane(path_lo, paraxial_z)

    # Coma is the deviation of the mean marginal-ray height from the
    # paraxial image height. Spherical aberration is symmetric (equal and
    # opposite for the two marginal rays) and cancels in the mean; the
    # residual is the coma contribution.
    paraxial_h = calculate_paraxial_image_height(system)
    return (real_h_up + real_h_lo) / 2.0 - paraxial_h


# ---------------------------------------------------------------------------
# Astigmatism & Field Curvature
# ---------------------------------------------------------------------------

def astigmatism_and_field_curvature(system: OpticalSystem) -> dict:
    """
    Measure astigmatism and field curvature for an off-axis object.

    For an off-axis object, the tangential (meridional) rays focus at a
    different z than the sagittal rays. We approximate:

        - tangential focus: axis crossing of the upper marginal ray
        - sagittal focus: axis crossing of a ray through the aperture
          center but at the object height (chief-like)

    Returns:
        Dict with:
            - "astigmatism": tangential focus - sagittal focus (m)
            - "field_curvature": (tangential + sagittal)/2 - paraxial (m)
            - "tangential_focus": z of tangential focus (m)
            - "sagittal_focus": z of sagittal focus (m)
    """
    D = _first_lens_aperture(system)
    if D <= 0:
        return {
            "astigmatism": 0.0,
            "field_curvature": 0.0,
            "tangential_focus": 0.0,
            "sagittal_focus": 0.0,
        }

    obj_h = system.object.height
    paraxial_z = calculate_paraxial_image_position(system)

    # Tangential: upper marginal ray from object top through aperture top
    theta_t = _object_to_lens_angle(system, D / 2.0, obj_h)
    ray_t = _make_ray(system, obj_h, theta_t)
    path_t = trace_real_ray(system, ray_t)
    tang_focus = real_axis_crossing(path_t)

    # Sagittal: chief-like ray from object top through aperture center
    theta_s = _object_to_lens_angle(system, 0.0, obj_h)
    ray_s = _make_ray(system, obj_h, theta_s)
    path_s = trace_real_ray(system, ray_s)
    sag_focus = real_axis_crossing(path_s)

    if tang_focus is None:
        tang_focus = paraxial_z
    if sag_focus is None:
        sag_focus = paraxial_z

    return {
        "astigmatism": tang_focus - sag_focus,
        "field_curvature": (tang_focus + sag_focus) / 2.0 - paraxial_z,
        "tangential_focus": tang_focus,
        "sagittal_focus": sag_focus,
    }


# ---------------------------------------------------------------------------
# Distortion
# ---------------------------------------------------------------------------

def distortion(system: OpticalSystem) -> float:
    """
    Measure distortion for an off-axis object.

    Distortion is the relative difference between the real image height
    of the chief ray and the paraxial image height.

    Returns:
        Distortion as a fraction (dimensionless). Positive = pincushion,
        negative = barrel.
    """
    D = _first_lens_aperture(system)
    if D <= 0:
        return 0.0

    obj_h = system.object.height
    paraxial_h = calculate_paraxial_image_height(system)
    paraxial_z = calculate_paraxial_image_position(system)

    # Chief ray: from object top through aperture center
    theta = _object_to_lens_angle(system, 0.0, obj_h)
    ray = _make_ray(system, obj_h, theta)
    path = trace_real_ray(system, ray)
    real_h = real_intercept_at_plane(path, paraxial_z)

    if abs(paraxial_h) < 1e-15:
        return 0.0
    return (real_h - paraxial_h) / paraxial_h


# ---------------------------------------------------------------------------
# Full Seidel analysis
# ---------------------------------------------------------------------------

def seidel_analysis(system: OpticalSystem) -> dict:
    """
    Perform a full Seidel (third-order) monochromatic aberration analysis.

    Returns:
        Dict with keys:
            - "spherical_aberration": dict (longitudinal, transverse)
            - "coma": float (meters)
            - "astigmatism": float (meters)
            - "field_curvature": float (meters)
            - "distortion": float (dimensionless fraction)
            - "paraxial_image_position": float (meters)
            - "paraxial_image_height": float (meters)
    """
    sa = spherical_aberration(system)
    afc = astigmatism_and_field_curvature(system)

    return {
        "spherical_aberration": sa,
        "coma": coma(system),
        "astigmatism": afc["astigmatism"],
        "field_curvature": afc["field_curvature"],
        "distortion": distortion(system),
        "paraxial_image_position": calculate_paraxial_image_position(system),
        "paraxial_image_height": calculate_paraxial_image_height(system),
    }