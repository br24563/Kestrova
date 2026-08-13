"""
Ray tracing engine for paraxial optical systems.

This module implements a simple sequential ray tracer using the
paraxial (small-angle) approximation. Rays are traced through thin
lenses systems step by step, recording the ray path at each optical
element.

Sign convention (optics, used in optical design software):
    - Light travels from left to right (z-axis).
    - Ray height (y): positive above the optical axis.
    - Ray angle (theta): positive if ray goes upward.
    - Object distance (s): NEGATIVE if object is to the LEFT of the lens.
    - Image distance (s'): NEGATIVE if image is to the LEFT of the lens.
    - Image distance (s'): POSITIVE if image is to the RIGHT of the lens.
    - Focal length: positive for converging lenses.

All values are in SI base units (meters, radians).
"""

import math
from typing import Optional
from .models import (
    OpticalSystem, Ray, RayPath, RayTraceResult,
    ThinLens, OpticalComponent,
)
from .lenses import (
    RayVector, propagation_matrix, thin_lens_matrix, apply_matrix,
)


# ---------------------------------------------------------------------------
# Ray Propagation
# ---------------------------------------------------------------------------

def propagate(y: float, theta: float, distance: float) -> tuple[float, float]:
    """
    Propagate a paraxial ray over a distance.

    In the paraxial approximation:
        y_new = y + distance * theta
        theta_new = theta

    Args:
        y: Ray height (meters).
        theta: Ray angle (radians).
        distance: Propagation distance (meters). Positive = to the right.

    Returns:
        Tuple of (new_y, new_theta).
    """
    new_y = y + distance * theta
    return new_y, theta


def refract_at_thin_lens(
    y: float, theta: float, focal_length: float
) -> tuple[float, float]:
    """
    Apply refraction at a thin lens.

    For a thin lens:
        y_new = y  (height doesn't change)
        theta_new = theta - y / f

    Args:
        y: Ray height at the lens (meters).
        theta: Ray angle before the lens (radians).
        focal_length: Lens focal length (meters). Positive = converging.

    Returns:
        Tuple of (new_y, new_theta).
    """
    new_theta = theta - y / focal_length
    return y, new_theta


# ---------------------------------------------------------------------------
# Ray Generation
# ---------------------------------------------------------------------------

def generate_rays(
    system: OpticalSystem,
    num_rays: Optional[int] = None,
    aperture_fraction: Optional[float] = None,
) -> list[Ray]:
    """
    Generate rays from the object through the first lens aperture.

    Rays are generated to pass through different heights of the first
    lens's aperture. The ray types are:
        - "chief": passes through the center of the aperture (y=0)
        - "marginal": passes through the edge of the aperture (y=±D/2)
        - "fill": evenly distributed across the aperture

    Args:
        system: The optical system.
        num_rays: Number of rays to generate. If None, uses system settings.
        aperture_fraction: Fraction of aperture to use (0.0 to 1.0).
                           If None, uses system settings.

    Returns:
        List of Ray objects, each with initial y, theta, z, and ray_type.

    Raises:
        ValueError: If the system has no lens components.
    """
    if num_rays is None:
        num_rays = system.analysis_settings.num_rays
    if aperture_fraction is None:
        aperture_fraction = system.analysis_settings.aperture_fraction

    # Find the first lens component (sorted by position)
    lenses = [c for c in system.components if isinstance(c, ThinLens)]
    if not lenses:
        raise ValueError("System has no lens components; cannot generate rays.")

    first_lens = min(lenses, key=lambda l: l.position)
    obj = system.object

    # Object position and height
    z_obj = obj.position
    h = obj.height

    # First lens position and aperture
    z_lens = first_lens.position
    D = first_lens.aperture_diameter * aperture_fraction

    # Distance from object to first lens
    d_obj_to_lens = z_lens - z_obj
    if abs(d_obj_to_lens) < 1e-15:
        raise ValueError("Object is at the same position as the first lens.")

    rays: list[Ray] = []
    wavelength = system.analysis_settings.wavelength

    # Generate aperture heights
    # We generate rays that pass through heights from -D/2 to +D/2
    if num_rays == 1:
        heights = [0.0]
    else:
        heights = [
            -D / 2 + i * D / (num_rays - 1)
            for i in range(num_rays)
        ]

    for i, y_ap in enumerate(heights):
        # Ray angle: from object point to aperture height
        # The object distance s is negative (object to the left of the lens)
        # in the optics sign convention, but the geometric distance is positive.
        theta = (y_ap - h) / d_obj_to_lens

        # Determine ray type
        if abs(y_ap) < 1e-15:
            ray_type = "chief"
        elif abs(y_ap - D / 2) < 1e-15 or abs(y_ap + D / 2) < 1e-15:
            ray_type = "marginal"
        else:
            ray_type = "fill"

        ray = Ray(
            y=h,
            theta=theta,
            z=z_obj,
            wavelength=wavelength,
            ray_type=ray_type,
        )
        rays.append(ray)

    return rays


# ---------------------------------------------------------------------------
# Ray Tracing Through a System
# ---------------------------------------------------------------------------

def trace_ray(
    system: OpticalSystem,
    ray: Ray,
) -> RayPath:
    """
    Trace a single paraxial ray through the optical system.

    The ray is propagated step by step through each optical component.
    At each thin lens, the ray angle is updated according to the
    thin lens formula. The ray path is recorded as a series of (z, y)
    points.

    Args:
        system: The optical system.
        ray: The input ray (with initial y, theta, z).

    Returns:
        RayPath containing the ray's path through the system.
    """
    # Sort components by position (left to right)
    components = sorted(system.components, key=lambda c: c.position)

    # Initialize ray state
    z = ray.z
    y = ray.y
    theta = ray.theta

    # Record the starting point
    points: list[list[float]] = [[z, y]]

    # Trace through each component
    for comp in components:
        # Propagate from current position to the component
        distance = comp.position - z
        if distance > 0:
            y, theta = propagate(y, theta, distance)
            z = comp.position
            points.append([z, y])

        # Apply the component's effect
        if isinstance(comp, ThinLens):
            y, theta = refract_at_thin_lens(y, theta, comp.focal_length)
            # Record the point after refraction (same z, same y)
            points.append([z, y])
        # Other component types (spherical surfaces, apertures, etc.)
        # will be added in future phases.

    # Propagate to the image plane
    z_image = system.image_plane.position
    distance = z_image - z
    if distance > 0:
        y, theta = propagate(y, theta, distance)
        z = z_image
        points.append([z, y])
    elif distance < 0:
        # Image plane is before the last component
        y, theta = propagate(y, theta, distance)
        z = z_image
        points.append([z, y])

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
    """
    Trace all rays through the optical system.

    Generates rays from the object, traces each through the system,
    and returns the results including ray paths and image information.

    Args:
        system: The optical system.
        num_rays: Number of rays to trace. If None, uses system settings.
        aperture_fraction: Fraction of aperture to use. If None, uses settings.

    Returns:
        RayTraceResult with ray paths and image information.
    """
    # Generate rays
    rays = generate_rays(system, num_rays, aperture_fraction)

    # Trace each ray
    ray_paths = [trace_ray(system, ray) for ray in rays]

    # Calculate image position using paraxial formula
    image_pos = calculate_paraxial_image_position(system)

    # Calculate paraxial image height
    paraxial_image_height = calculate_paraxial_image_height(system)

    return RayTraceResult(
        ray_paths=ray_paths,
        image_position=image_pos,
        image_height=ray_paths[0].final_y if ray_paths else 0.0,
        paraxial_image_height=paraxial_image_height,
    )


# ---------------------------------------------------------------------------
# Paraxial Image Calculation
# ---------------------------------------------------------------------------

def calculate_paraxial_image_position(system: OpticalSystem) -> float:
    """
    Calculate the paraxial image position for the optical system.

    For a system of thin lenses, the image is found by sequentially
    applying the thin lens equation at each lens.

    Sign convention (optics):
        - Object distance s is NEGATIVE if the object is to the LEFT.
        - Image distance s' is POSITIVE if the image is to the RIGHT.

    Args:
        system: The optical system.

    Returns:
        Image position along the z-axis (meters).
    """
    obj = system.object
    components = sorted(system.components, key=lambda c: c.position)

    # Current "image" position (starts as the object position)
    current_pos = obj.position
    current_height = obj.height

    for comp in components:
        if isinstance(comp, ThinLens):
            # Object distance from this lens (optics convention)
            # s < 0 if object is to the LEFT of the lens
            s = current_pos - comp.position

            if abs(s) < 1e-15:
                # Object is at the lens
                continue

            # Image distance from this lens
            # 1/f = 1/s' - 1/s  =>  s' = f * s / (s + f)
            s_prime = comp.focal_length * s / (s + comp.focal_length)

            # Update current position
            current_pos = comp.position + s_prime
            # Update current height (for off-axis objects)
            if abs(s) > 1e-15:
                m = s_prime / s
                current_height = current_height * m

    return current_pos


def calculate_paraxial_image_height(system: OpticalSystem) -> float:
    """
    Calculate the paraxial image height for the optical system.

    Uses the magnification of each lens to compute the final image height.

    Sign convention (optics):
        - Object distance s is NEGATIVE if the object is to the LEFT.
        - Magnification m = s' / s (negative = inverted).

    Args:
        system: The optical system.

    Returns:
        Image height (meters).
    """
    obj = system.object
    components = sorted(system.components, key=lambda c: c.position)

    current_pos = obj.position
    current_height = obj.height

    for comp in components:
        if isinstance(comp, ThinLens):
            s = current_pos - comp.position
            if abs(s) < 1e-15:
                continue
            s_prime = comp.focal_length * s / (s + comp.focal_length)
            m = s_prime / s
            current_height = current_height * m
            current_pos = comp.position + s_prime

    return current_height


# ---------------------------------------------------------------------------
# Spot Diagram
# ---------------------------------------------------------------------------

def calculate_spot_diagram(
    ray_paths: list[RayPath],
    image_position: float,
) -> tuple[list[float], float]:
    """
    Calculate the spot diagram at the image plane.

    The spot diagram shows where each ray intersects the image plane.
    For a perfect paraxial system, all rays should converge to the same
    point, giving an RMS spot radius of zero.

    Args:
        ray_paths: List of ray paths from trace_system().
        image_position: The z-position of the image plane (meters).

    Returns:
        Tuple of (spot_heights, rms_spot_radius):
            - spot_heights: list of y-values at the image plane (meters)
            - rms_spot_radius: RMS spot radius (meters)
    """
    spot_heights: list[float] = []

    for path in ray_paths:
        # Find the y-value at the image plane
        # The last point in the path should be at the image plane
        if path.points:
            y_at_image = path.points[-1][1]
            spot_heights.append(y_at_image)

    if not spot_heights:
        return [], 0.0

    # RMS spot radius
    # For a 1D spot diagram (meridional rays), RMS = sqrt(mean(y^2))
    mean_y = sum(spot_heights) / len(spot_heights)
    rms = math.sqrt(sum((y - mean_y) ** 2 for y in spot_heights) / len(spot_heights))

    return spot_heights, rms