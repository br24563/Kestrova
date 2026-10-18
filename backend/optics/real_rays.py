"""
Real (exact) meridional ray tracing.

A thin convenience layer over :mod:`optics.raytrace`: a ray given by its
height ``y``, slope angle ``theta`` and start ``z`` is traced exactly (vector
Snell's law / law of reflection) through every surface of the system, and
its path is returned as a list of [z, y] points (start, each surface, image
plane). See :mod:`optics.raytrace` for the modelling conventions,
including how a ``ThinLens`` is represented (an ideal paraxial lens).

All values are in SI base units (meters, radians).
"""

import math
from typing import Optional

import numpy as np

from .models import OpticalSystem, Ray
from . import raytrace as rt

# ---------------------------------------------------------------------------
# Geometric helpers (2D, meridional plane)
# ---------------------------------------------------------------------------


def _sphere_intersection(
    z0: float,
    y0: float,
    dz: float,
    dy: float,
    z_vertex: float,
    radius: float,
) -> Optional[tuple[float, float]]:
    """
    Intersection of a ray with the sphere through ``z_vertex`` of signed
    radius ``radius``, on the cap containing the vertex.

    Returns (z, y), or None if the ray misses that cap.
    """
    zc = z_vertex + radius
    b = 2.0 * (dz * (z0 - zc) + dy * y0)
    c = (z0 - zc) ** 2 + y0**2 - radius**2
    disc = b * b - 4.0 * c
    if disc < 0.0:
        return None
    sq = math.sqrt(disc)
    best = None
    for t in ((-b - sq) / 2.0, (-b + sq) / 2.0):
        if t <= 1e-12:
            continue
        z, y = z0 + t * dz, y0 + t * dy
        # same hemisphere as the vertex: (z - zc) has the sign of -radius
        if (z - zc) * (-radius) >= 0 and (best is None or t < best[0]):
            best = (t, z, y)
    return None if best is None else (best[1], best[2])


def _snell_refract(
    dz: float, dy: float, nx: float, ny: float, n1: float, n2: float
) -> Optional[tuple[float, float]]:
    """
    Vector Snell's law in the meridional plane.

    Args:
        dz, dy: Unit incident direction.
        nx, ny: Unit surface normal (either orientation).
        n1, n2: Indices of the incident and transmitting media.

    Returns:
        Unit transmitted direction, or None at total internal reflection.
    """
    nd = nx * dz + ny * dy
    if nd > 0.0:
        nx, ny, nd = -nx, -ny, -nd
    sin_i_sq = max(0.0, 1.0 - nd * nd)
    ratio = n1 / n2
    sin_t_sq = ratio * ratio * sin_i_sq
    if sin_t_sq > 1.0:
        return None
    cos_t = math.sqrt(1.0 - sin_t_sq)
    tz = ratio * (dz - nd * nx) - nx * cos_t
    ty = ratio * (dy - nd * ny) - ny * cos_t
    norm = math.hypot(tz, ty)
    return tz / norm, ty / norm


# ---------------------------------------------------------------------------
# Real ray tracing
# ---------------------------------------------------------------------------


def trace_real_ray(
    system: OpticalSystem,
    ray: Ray,
    aperture_diameter: Optional[float] = None,
    clip: bool = False,
) -> list[list[float]]:
    """
    Trace one meridional ray exactly through the system.

    Args:
        system: The optical system.
        ray: Start height ``y``, slope angle ``theta`` (radians) and ``z``.
        aperture_diameter: Unused; kept for backward compatibility.
        clip: Stop the path at the first surface whose clear aperture the
            ray misses (vignetting) or where it is totally internally
            reflected.

    Returns:
        [[z, y], ...] at the start, at each surface reached, and at the
        image plane.
    """
    seq = rt.build_sequence(system, ray.wavelength)
    p0 = np.array([[0.0, ray.y, ray.z]])
    d0 = np.array([[0.0, math.sin(ray.theta), math.cos(ray.theta)]])
    b = rt.trace_bundle(seq, p0, d0, clip=clip)
    pts = b.points[0]
    path = [[float(p[2]), float(p[1])] for p in pts]
    if not b.valid[0]:
        # truncate at the first non-finite point
        good = [p for p in path if math.isfinite(p[0]) and math.isfinite(p[1])]
        return good
    return path


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def real_intercept_at_plane(points: list[list[float]], z_plane: float) -> float:
    """Height where the last straight segment of a path meets z = z_plane."""
    if not points:
        return 0.0
    if len(points) == 1:
        return points[0][1]
    p1, p2 = points[-2], points[-1]
    dz = p2[0] - p1[0]
    if abs(dz) < 1e-15:
        return p2[1]
    return p2[1] + (z_plane - p2[0]) * (p2[1] - p1[1]) / dz


def real_axis_crossing(points: list[list[float]]) -> Optional[float]:
    """z where the last straight segment of a path crosses the axis (y = 0)."""
    if len(points) < 2:
        return None
    p1, p2 = points[-2], points[-1]
    dy = p2[1] - p1[1]
    if abs(dy) < 1e-15:
        return None
    return p2[0] - p2[1] * (p2[0] - p1[0]) / dy


def real_ray_crossing(
    pts1: list[list[float]], pts2: list[list[float]]
) -> Optional[float]:
    """z where the last segments of two paths intersect, or None."""
    if len(pts1) < 2 or len(pts2) < 2:
        return None
    a1, a2 = pts1[-2], pts1[-1]
    b1, b2 = pts2[-2], pts2[-1]
    dz1 = a2[0] - a1[0]
    dz2 = b2[0] - b1[0]
    if abs(dz1) < 1e-15 or abs(dz2) < 1e-15:
        return None
    m1 = (a2[1] - a1[1]) / dz1
    m2 = (b2[1] - b1[1]) / dz2
    if abs(m1 - m2) < 1e-15:
        return None
    return (a1[1] - b1[1] - m1 * a1[0] + m2 * b1[0]) / (m2 - m1)
