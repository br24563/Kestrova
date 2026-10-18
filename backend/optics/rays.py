"""
Paraxial ray tracing for the optical bench display.

Rays are traced with the paraxial (y-u) equations through the full surface
sequence built by :mod:`optics.raytrace`, so thick lenses, single
refracting surfaces and mirrors are all handled with their real paraxial
power and position. Real (exact) rays, spot sizes and aberrations come from
:mod:`optics.raytrace` and the analysis modules built on it.

Sign convention:
    - Light enters travelling +z; heights are positive above the axis.
    - Ray angle theta is the slope dy/dz along the axis direction.
    - Object distance s is negative for an object to the left.

All values are in SI base units (meters, radians).
"""

import math
from typing import Optional

from .models import OpticalSystem, Ray, RayPath, RayTraceResult
from . import raytrace as rt

# ---------------------------------------------------------------------------
# Elementary paraxial operations
# ---------------------------------------------------------------------------


def propagate(y: float, theta: float, distance: float) -> tuple[float, float]:
    """Paraxial transfer: y' = y + d*theta, theta unchanged."""
    return y + distance * theta, theta


def reflect_at_mirror(y: float, theta: float) -> tuple[float, float]:
    """
    Reflection at a flat mirror normal to the axis.

    The slope relative to the (now reversed) direction of travel is
    unchanged, so the slope dy/dz measured along the fixed z axis changes
    sign.
    """
    return y, -theta


def refract_at_thin_lens(
    y: float, theta: float, focal_length: float
) -> tuple[float, float]:
    """Thin lens in air: y unchanged, theta' = theta - y/f."""
    return y, theta - y / focal_length


# ---------------------------------------------------------------------------
# Ray generation
# ---------------------------------------------------------------------------


def generate_rays(
    system: OpticalSystem,
    num_rays: Optional[int] = None,
    aperture_fraction: Optional[float] = None,
) -> list[Ray]:
    """
    Paraxial rays from the top of the object through the entrance pupil.

    The rays are spread uniformly across the entrance pupil (the image of
    the aperture stop), so the "chief" ray passes through the centre of
    the stop and the "marginal" rays through its edge. For an object at
    infinity the rays start on a plane in front of the first surface with
    the field angle.
    """
    if num_rays is None:
        num_rays = system.analysis_settings.num_rays
    if aperture_fraction is None:
        aperture_fraction = system.analysis_settings.aperture_fraction
    wavelength = system.analysis_settings.wavelength
    seq = rt.build_sequence(system, wavelength)
    fo = rt.first_order(system, seq=seq)
    ep_z = fo.entrance_pupil_z
    ep_r = fo.entrance_pupil_semi_diameter * aperture_fraction
    if num_rays == 1:
        fracs = [0.0]
    else:
        fracs = [-1.0 + 2.0 * i / (num_rays - 1) for i in range(num_rays)]

    rays = []
    for p in fracs:
        if abs(p) < 1e-12:
            kind = "chief"
        elif abs(abs(p) - 1.0) < 1e-12:
            kind = "marginal"
        else:
            kind = "fill"
        if seq.object_infinite:
            u = fo.chief.u_object_space
            z0 = seq.surfaces[0].z - rt._start_offset(seq)
            # ray through the pupil point (p * ep_r) at ep_z with the field slope
            y0 = p * ep_r + u * (z0 - ep_z)
            rays.append(Ray(y=y0, theta=u, z=z0, wavelength=wavelength, ray_type=kind))
        else:
            h = system.object.height
            if math.isfinite(ep_z) and abs(ep_z - system.object.position) > 1e-15:
                theta = (p * ep_r - h) / (ep_z - system.object.position)
            else:
                theta = (
                    fo.chief.u_object_space
                    + p * fo.marginal.u_object_space * aperture_fraction
                )
            rays.append(
                Ray(
                    y=h,
                    theta=theta,
                    z=system.object.position,
                    wavelength=wavelength,
                    ray_type=kind,
                )
            )
    return rays


# ---------------------------------------------------------------------------
# Ray tracing
# ---------------------------------------------------------------------------


def trace_ray(system: OpticalSystem, ray: Ray) -> RayPath:
    """
    Trace one paraxial ray through the system, recording (z, y) at the
    start, at every surface, and at the image plane.
    """
    seq = rt.build_sequence(system, ray.wavelength)
    idx = rt.signed_indices(seq)
    z, y, theta = ray.z, ray.y, ray.theta
    points = [[z, y]]
    nu = idx[0][0] * theta
    n_cur = idx[0][0]
    rt.s_wavelength_holder[0] = seq.wavelength
    for i, s in enumerate(seq.surfaces):
        y = y + (s.z - z) * nu / n_cur
        z = s.z
        points.append([z, y])
        nb, na = idx[i]
        nu = nu - y * rt._surface_power(s, nb, na)
        n_cur = na
    theta = nu / n_cur
    z_img = system.image_plane.position
    y = y + (z_img - z) * theta
    points.append([z_img, y])
    return RayPath(
        points=points,
        ray_type=ray.ray_type,
        wavelength=ray.wavelength,
        initial_y=ray.y,
        initial_theta=ray.theta,
        final_y=y,
        final_theta=theta,
    )


def trace_system(
    system: OpticalSystem,
    num_rays: Optional[int] = None,
    aperture_fraction: Optional[float] = None,
) -> RayTraceResult:
    """Trace the bench rays and report the paraxial image."""
    rays = generate_rays(system, num_rays, aperture_fraction)
    ray_paths = [trace_ray(system, ray) for ray in rays]
    chief = next((p for p in ray_paths if p.ray_type == "chief"), None)
    return RayTraceResult(
        ray_paths=ray_paths,
        image_position=calculate_paraxial_image_position(
            system, system.analysis_settings.wavelength
        ),
        image_height=chief.final_y if chief is not None else 0.0,
        paraxial_image_height=calculate_paraxial_image_height(
            system, system.analysis_settings.wavelength
        ),
    )


# ---------------------------------------------------------------------------
# Paraxial image
# ---------------------------------------------------------------------------


def calculate_paraxial_image_position(
    system: OpticalSystem, wavelength: Optional[float] = None
) -> float:
    """Paraxial image position (z, meters) at a wavelength (default: the
    system's analysis wavelength)."""
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength
    return rt.first_order(system, wavelength).image_z


def calculate_paraxial_image_height(
    system: OpticalSystem, wavelength: Optional[float] = None
) -> float:
    """
    Paraxial image height (meters) of the top of the object at a
    wavelength (default: the system's analysis wavelength). For an object at
    infinity this is the chief-ray height in the paraxial image plane.
    """
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength
    return rt.first_order(system, wavelength).image_height


# ---------------------------------------------------------------------------
# Spot of the bench rays
# ---------------------------------------------------------------------------


def calculate_spot_diagram(
    ray_paths: list[RayPath],
    image_position: float,
) -> tuple[list[float], float]:
    """
    Heights of the traced (paraxial, meridional) rays where they cross
    ``image_position`` and their RMS spread about the mean.

    Paraxial rays have no aberrations, so this spread measures defocus
    only; the real, aberrated spot comes from ``optics.analysis``.
    """
    heights: list[float] = []
    for path in ray_paths:
        if len(path.points) < 2:
            continue
        (z1, y1), (z2, y2) = path.points[-2], path.points[-1]
        if abs(z2 - z1) > 1e-15:
            heights.append(y2 + (image_position - z2) * (y2 - y1) / (z2 - z1))
        else:
            heights.append(y2)
    if not heights:
        return [], 0.0
    mean = sum(heights) / len(heights)
    rms = math.sqrt(sum((h - mean) ** 2 for h in heights) / len(heights))
    return heights, rms
