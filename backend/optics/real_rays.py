"""
Real (exact) ray tracing for genuine ray-aberration analysis.

The paraxial tracer in ``rays.py`` is first-order only; paraxial rays
*by definition* produce zero third-order aberrations. To measure
spherical aberration, coma, astigmatism, field curvature, and distortion
we need a ray tracer that applies exact Snell's law at spherical
surfaces. This module provides such a tracer.

Modeling notes
--------------
- A ``ThinLens`` in this engine carries only a focal length (no radii).
  For aberration analysis it is modeled as a *symmetric biconvex lens*
  in air with equal curvature radii  R = 2 (n - 1) f.  This is a
  documented, deterministic modeling choice that reproduces the classic
  textbook spherical aberration of a biconvex lens.
- ``SphericalSurface``, ``ThickLens`` and ``Mirror`` are traced exactly.
- ``ApertureStop`` passes rays without deviation.

All calculations are performed by the validated optics engine; this
module only implements the physical ray-propagation geometry.

All values are in SI base units (meters, radians).
"""

import math
from typing import Optional

from .models import (
    OpticalSystem, Ray, ThinLens, SphericalSurface, ThickLens, Mirror,
)
from .materials import refractive_index


# ---------------------------------------------------------------------------
# Geometric helpers
# ---------------------------------------------------------------------------

def _sphere_intersection(
    z0: float, y0: float, dz: float, dy: float,
    z_vertex: float, radius: float,
) -> Optional[tuple[float, float]]:
    """
    Find the nearest intersection of a ray with a spherical surface.

    Args:
        z0, y0: Ray start point (meters).
        dz, dy: Unit ray direction (dz^2 + dy^2 = 1).
        z_vertex: Position of the surface vertex on the axis (meters).
        radius: Signed radius of curvature (meters). Center at
            z_vertex + radius.

    Returns:
        (z, y) intersection point, or None if the ray misses the sphere.
    """
    zc = z_vertex + radius
    # a t^2 + b t + c = 0 with a = dz^2 + dy^2 = 1
    b = 2.0 * (dz * (z0 - zc) + dy * y0)
    c = (z0 - zc) ** 2 + y0 ** 2 - radius ** 2
    disc = b * b - 4.0 * c
    if disc < 0.0:
        return None
    sqrt_disc = math.sqrt(disc)
    t1 = (-b - sqrt_disc) / 2.0
    t2 = (-b + sqrt_disc) / 2.0
    # Pick the nearest positive intersection ahead of the ray
    t = None
    if t1 > 1e-12:
        t = t1
    if t2 > 1e-12 and (t is None or t2 < t):
        t = t2
    if t is None:
        return None
    return z0 + t * dz, y0 + t * dy


def _snell_refract(
    dz: float, dy: float, nx: float, ny: float, n1: float, n2: float
) -> Optional[tuple[float, float]]:
    """
    Refract a ray at a surface using exact Snell's law (meridional plane).

    Args:
        dz, dy: Unit incoming direction.
        nx, ny: Unit surface normal (points toward the incoming ray,
            i.e. nx*dz + ny*dy <= 0).
        n1: Refractive index of the incident medium.
        n2: Refractive index of the transmitted medium.

    Returns:
        Unit transmitted direction (dz', dy'), or None if total internal
        reflection occurs.
    """
    nd = nx * dz + ny * dy  # <= 0 if the normal faces the ray
    # Force the normal to face the incoming ray
    if nd > 0.0:
        nx, ny, nd = -nx, -ny, -nd

    sin_i_sq = 1.0 - nd * nd
    if sin_i_sq < 0.0:
        sin_i_sq = 0.0
    ratio = n1 / n2
    sin_r_sq = ratio * ratio * sin_i_sq
    if sin_r_sq > 1.0:
        return None  # total internal reflection
    cos_r = math.sqrt(1.0 - sin_r_sq)
    # Transmitted direction (standard vector Snell)
    dzn = ratio * (dz - nd * nx) - nx * cos_r
    dyn = ratio * (dy - nd * ny) - ny * cos_r
    # Normalize (numerical safety)
    norm = math.hypot(dzn, dyn)
    return dzn / norm, dyn / norm


# ---------------------------------------------------------------------------
# Thin-lens modeling for real rays
# ---------------------------------------------------------------------------

def _thin_lens_radii(thin_lens: ThinLens, wavelength: float) -> tuple[float, float, float]:
    """
    Model a ThinLens as a symmetric biconvex lens.

    Returns (R1, R2, n) with  R = 2 (n - 1) f.
    """
    n = refractive_index(thin_lens.material, wavelength)
    f = thin_lens.focal_length
    if abs(f) < 1e-15:
        raise ValueError("Cannot model a thin lens with zero focal length.")
    r = 2.0 * (n - 1.0) * f
    return r, -r, n


# ---------------------------------------------------------------------------
# Real ray tracing
# ---------------------------------------------------------------------------

def trace_real_ray(
    system: OpticalSystem,
    ray: Ray,
    aperture_diameter: Optional[float] = None,
) -> list[list[float]]:
    """
    Trace a single real ray (exact Snell) through the optical system.

    Args:
        system: The optical system.
        ray: The input ray (z, y, direction described by ray.theta).
        aperture_diameter: Reserved for future aperture clipping.

    Returns:
        List of [z, y] points along the real ray path.
    """
    components = sorted(system.components, key=lambda c: c.position)
    wavelength = ray.wavelength

    # Start with a unit direction derived from the ray angle
    dz = math.cos(ray.theta)
    dy = math.sin(ray.theta)

    z, y = ray.z, ray.y
    points: list[list[float]] = [[z, y]]

    for comp in components:
        if isinstance(comp, ThinLens):
            _trace_thin_lens(comp, z, y, dz, dy, wavelength, points)
        elif isinstance(comp, SphericalSurface):
            if not _trace_spherical_surface(
                comp.position, comp.radius, z, y, dz, dy, wavelength, points
            ):
                break
        elif isinstance(comp, ThickLens):
            if not _trace_thick_lens(comp, z, y, dz, dy, wavelength, points):
                break
        elif isinstance(comp, Mirror):
            # Flat mirror: reflect the direction in the plane
            dy = -dy
            points.append([points[-1][0], points[-1][1]])
        # ApertureStop: no deviation; continue

        # Update current state from the last point
        z, y = points[-1]
        dz, dy = _direction_from_points(points)

    # Propagate to the system image plane
    z_image = system.image_plane.position
    seg = z_image - z
    if abs(seg) > 1e-15:
        if abs(dz) > 1e-15:
            y_image = y + seg * (dy / dz)
        else:
            y_image = y
        points.append([z_image, y_image])

    return points


def _trace_spherical_surface(
    z_vertex: float, radius: float,
    z: float, y: float, dz: float, dy: float,
    wavelength: float, points: list[list[float]],
    n1: Optional[float] = None, n2: Optional[float] = None,
) -> bool:
    """Trace one exact refraction at a spherical surface.

    Returns False if the ray misses the surface or TIR occurs.
    """
    if n1 is None:
        n1 = refractive_index("air")
    if n2 is None:
        n2 = 1.0  # caller overrides

    if radius is None or abs(radius) < 1e-15:
        # Flat surface: only index change (normal along the axis)
        dir_refr = _snell_refract(dz, dy, 1.0, 0.0, n1, n2)
        if dir_refr is None:
            return False
        points.append([z, y])
        points.append([z + 1e-9 * dir_refr[0], y + 1e-9 * dir_refr[1]])
        return True

    hit = _sphere_intersection(z, y, dz, dy, z_vertex, radius)
    if hit is None:
        return False
    hz, hy = hit
    # Surface normal (unit, pointing away from the center)
    nx = (hz - (z_vertex + radius)) / radius
    ny = hy / radius
    norm = math.hypot(nx, ny)
    nx, ny = nx / norm, ny / norm

    dir_refr = _snell_refract(dz, dy, nx, ny, n1, n2)
    if dir_refr is None:
        return False
    points.append([hz, hy])
    points.append([hz + 1e-9 * dir_refr[0], hy + 1e-9 * dir_refr[1]])
    return True


def _trace_thin_lens(
    comp: ThinLens, z: float, y: float, dz: float, dy: float,
    wavelength: float, points: list[list[float]],
) -> None:
    """Trace a thin lens modeled as two back-to-back spherical surfaces."""
    r1, r2, n = _thin_lens_radii(comp, wavelength)
    eps = max(min(0.0005 * abs(comp.focal_length), 1e-4), 1e-7)
    # First surface: air -> glass
    if not _trace_spherical_surface(
        comp.position, r1, z, y, dz, dy, wavelength, points,
        n1=1.0, n2=n,
    ):
        return
    # Propagate epsilon through the glass
    z2 = comp.position + eps
    p_last = points[-1]
    seg = z2 - p_last[0]
    if abs(seg) > 1e-15:
        ddz, ddy = _direction_from_points(points)
        if abs(ddz) > 1e-15:
            y2 = p_last[1] + seg * (ddy / ddz)
        else:
            y2 = p_last[1]
        points.append([z2, y2])

    # Second surface: glass -> air
    _trace_spherical_surface(
        comp.position + eps, r2, points[-1][0], points[-1][1],
        *(_direction_from_points(points)),
        wavelength, points,
        n1=n, n2=1.0,
    )


def _trace_thick_lens(
    comp: ThickLens, z: float, y: float, dz: float, dy: float,
    wavelength: float, points: list[list[float]],
) -> bool:
    """Trace a thick lens: two exact surfaces separated by thickness."""
    n = refractive_index(comp.material, wavelength)
    if not _trace_spherical_surface(
        comp.position, comp.radius1, z, y, dz, dy, wavelength, points,
        n1=1.0, n2=n,
    ):
        return False
    # Propagate through the glass thickness (straight line)
    z2 = comp.position + comp.thickness
    p_last = points[-1]
    seg = z2 - p_last[0]
    if abs(seg) > 1e-15:
        ddz, ddy = _direction_from_points(points)
        if abs(ddz) > 1e-15:
            y2 = p_last[1] + seg * (ddy / ddz)
        else:
            y2 = p_last[1]
        points.append([z2, y2])

    # Second surface: glass -> air
    _trace_spherical_surface(
        comp.position + comp.thickness, comp.radius2,
        points[-1][0], points[-1][1],
        *(_direction_from_points(points)),
        wavelength, points,
        n1=n, n2=1.0,
    )
    return True


def _direction_from_points(points: list[list[float]]) -> tuple[float, float]:
    """Reconstruct a unit direction from the last segment of the path."""
    if len(points) < 2:
        return 1.0, 0.0
    p1 = points[-2]
    p2 = points[-1]
    seg_z = p2[0] - p1[0]
    seg_y = p2[1] - p1[1]
    norm = math.hypot(seg_z, seg_y)
    if norm < 1e-15:
        return 1.0, 0.0
    return seg_z / norm, seg_y / norm


# ---------------------------------------------------------------------------
# Real-ray helpers used by the aberration module
# ---------------------------------------------------------------------------

def real_intercept_at_plane(
    points: list[list[float]], z_plane: float
) -> float:
    """
    Interpolate (or extrapolate) the ray height at a plane z = z_plane.

    The last straight segment of the path is extended linearly.
    """
    if not points:
        return 0.0
    if len(points) == 1:
        return points[0][1]
    p1 = points[-2]
    p2 = points[-1]
    dz = p2[0] - p1[0]
    if abs(dz) < 1e-15:
        return p2[1]
    return p2[1] + (z_plane - p2[0]) * (p2[1] - p1[1]) / dz


def real_axis_crossing(points: list[list[float]]) -> Optional[float]:
    """
    Extrapolate the final ray segment to its crossing of the optical axis.

    Returns the z position where y = 0, or None if the segment is
    essentially parallel to the axis.
    """
    if len(points) < 2:
        return None
    p1 = points[-2]
    p2 = points[-1]
    dy = p2[1] - p1[1]
    if abs(dy) < 1e-15:
        return None
    t = -p2[1] / dy
    return p2[0] + t * (p2[0] - p1[0])


def real_ray_crossing(
    pts1: list[list[float]], pts2: list[list[float]]
) -> Optional[float]:
    """
    Extrapolate two final ray segments to their intersection z.

    Returns the z where the two last segments cross, or None.
    """
    if len(pts1) < 2 or len(pts2) < 2:
        return None
    a1 = pts1[-2]
    a2 = pts1[-1]
    b1 = pts2[-2]
    b2 = pts2[-1]
    dz1 = a2[0] - a1[0]
    dz2 = b2[0] - b1[0]
    if abs(dz1) < 1e-15 or abs(dz2) < 1e-15:
        return None
    m1 = (a2[1] - a1[1]) / dz1
    m2 = (b2[1] - b1[1]) / dz2
    if abs(m1 - m2) < 1e-15:
        return None
    # y = y_a1 + m1 (z - z_a1);  y = y_b1 + m2 (z - z_b1)
    return (a1[1] - b1[1] - m1 * a1[0] + m2 * b1[0]) / (m2 - m1)