"""
Spherical refractive surface calculations.

Closed-form paraxial relations for a single spherical refracting surface
and the thick-lens (lensmaker's) equation. Full system tracing is in
optics.raytrace.

Sign convention (Cartesian):
    - Light travels from left to right.
    - Radius of curvature R: positive if the center of curvature is
      to the RIGHT of the surface (convex surface facing the light).
    - Radius of curvature R: negative if the center of curvature is
      to the LEFT of the surface (concave surface facing the light).
    - Object distance s: positive if object is to the LEFT of the surface.
    - Image distance s': positive if image is to the RIGHT of the surface.

All values are in SI base units (meters, radians).
"""

import math


def spherical_surface_power(radius: float, n1: float, n2: float) -> float:
    """
    Calculate the power of a spherical refractive surface.

    Power = (n2 - n1) / R

    Args:
        radius: Radius of curvature (meters). Positive if center of
                curvature is to the right of the surface.
        n1: Refractive index of the incident medium.
        n2: Refractive index of the transmitted medium.

    Returns:
        Surface power (diopters, 1/meters).

    Examples:
        >>> # Air to glass, R=100mm
        >>> spherical_surface_power(0.1, 1.0, 1.5)
        5.0
    """
    if abs(radius) < 1e-15:
        raise ValueError("Radius of curvature is zero: surface is flat.")
    return (n2 - n1) / radius


def spherical_surface_image_distance(
    radius: float, n1: float, n2: float, s: float
) -> float:
    """
    Calculate the image distance for a spherical refractive surface.

    Uses the paraxial refraction formula:
        n1/s + n2/s' = (n2 - n1) / R

    Args:
        radius: Radius of curvature (meters).
        n1: Refractive index of the incident medium.
        n2: Refractive index of the transmitted medium.
        s: Object distance (meters). Positive if object is to the left.

    Returns:
        Image distance s' (meters). Positive if image is to the right.

    Examples:
        >>> # Air to glass, R=100mm, object 400mm in front
        >>> round(spherical_surface_image_distance(0.1, 1.0, 1.5, 0.4), 6)
        0.6
    """
    if abs(radius) < 1e-15:
        # Flat surface: no refraction
        return s

    # n1/s + n2/s' = (n2 - n1) / R
    # n2/s' = (n2 - n1) / R - n1/s
    # s' = n2 / ((n2 - n1) / R - n1/s)
    inv_s_prime = (n2 - n1) / radius - n1 / s
    if abs(inv_s_prime) < 1e-15:
        raise ValueError("Image is at infinity (object at focal point).")
    return n2 / inv_s_prime


def spherical_surface_refract(
    y: float, theta: float, radius: float, n1: float, n2: float
) -> tuple[float, float]:
    """
    Apply refraction at a spherical surface (paraxial).

    For a spherical surface:
        y_new = y  (height doesn't change)
        theta_new = theta * (n1 / n2) - y * (n2 - n1) / (n2 * R)

    Args:
        y: Ray height at the surface (meters).
        theta: Ray angle in the incident medium (radians).
        radius: Radius of curvature (meters).
        n1: Refractive index of the incident medium.
        n2: Refractive index of the transmitted medium.

    Returns:
        Tuple of (new_y, new_theta) where new_theta is in the transmitted medium.
    """
    if abs(radius) < 1e-15:
        # Flat surface: only change in angle due to refractive index
        return y, theta * (n1 / n2)

    new_theta = theta * (n1 / n2) - y * (n2 - n1) / (n2 * radius)
    return y, new_theta


def lensmaker_focal_length(
    radius1: float, radius2: float, thickness: float, n: float
) -> float:
    """
    Calculate the focal length of a thick lens using the lensmaker's equation.

    1/f = (n - 1) * [1/R1 - 1/R2 + (n - 1) * t / (n * R1 * R2)]

    Args:
        radius1: Radius of curvature of the first surface (meters).
        radius2: Radius of curvature of the second surface (meters).
        thickness: Thickness of the lens (meters).
        n: Refractive index of the lens material.

    Returns:
        Focal length (meters).

    Examples:
        >>> # Symmetric biconvex lens, R1=100mm, R2=-100mm, t=10mm, n=1.5
        >>> round(lensmaker_focal_length(0.1, -0.1, 0.01, 1.5), 6)
        0.101695
    """
    if abs(radius1) < 1e-15 and abs(radius2) < 1e-15:
        raise ValueError("Both radii are zero: lens is a slab.")

    inv_f = (n - 1) * (
        1.0 / radius1 - 1.0 / radius2 + (n - 1) * thickness / (n * radius1 * radius2)
    )

    if abs(inv_f) < 1e-15:
        raise ValueError("Focal length is infinite (plano or afocal lens).")

    return 1.0 / inv_f
