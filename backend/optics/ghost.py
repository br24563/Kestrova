"""
Ghost (stray-reflection) analysis with real ray paths.

``nonsequential.analyze_ghost_reflections`` reports ghost orders from a
purely radiometric model: it multiplies surface reflectances but never
propagates a ray. That is enough to rank ghost orders by intensity, but it
cannot answer the questions that actually matter when a ghost appears:

    - where does the ghost focus land, and how far is it from the image?
    - how big is the ghost spot, and how much does it move with field?
    - does the ghost ray path even reach the image plane?

This module answers those by tracing genuine double-reflection paths with
exact reflection geometry and Snell refraction, reusing the same surface
primitives as ``real_rays``.

Ghost path definition
---------------------
A double-reflection (order-2) ghost follows:

    1. forward from the object, refracting at every surface, until the
       first reflecting surface ``i``;
    2. reflect at ``i``, travelling back toward the object, refracting at
       every surface it re-crosses, until surface ``j`` (``j < i``);
    3. reflect at ``j``, then travel forward again, refracting through the
       remaining surfaces to the image plane.

Surface indexing
----------------
Each refracting surface is counted separately, front surface before back:

    - ``ThinLens``  -> two biconvex surfaces
    - ``ThickLens`` -> two surfaces separated by the real thickness
    - ``SphericalSurface`` -> one surface, air on the left
    - ``Mirror`` -> one reflective surface

Modeling notes
--------------
- A ``ThinLens`` carries only a focal length and has no physical surfaces
  to reflect from, so for ghost analysis it is modelled as a symmetric
  biconvex lens with R = 2 (n - 1) f, centre thickness from the surface
  sagitta plus a nominal edge thickness (``edge_thickness``). The main ray
  tracer instead treats a ThinLens as an ideal lens; the primary image
  used as the ghost reference is traced through the same biconvex surfaces
  as the ghosts, so the two are consistent.
- Rays are aimed at the paraxial entrance pupil. Systems with mirrors are
  outside the scope of this module (a mirror is treated as opaque to the
  forward path).
- Reflectance comes from the Fresnel equations at the real incidence angle.
  Pass ``coating_reflectance`` to override every surface with a measured or
  designed value (for example the output of ``coatings.Coating``); this
  models the AR coating that real systems apply to suppress ghosts.
- Ghosts are ranked by the product of the reflectances along the path, with
  each transmission weighted by (1 - R). This is the standard ghost
  irradiance estimate relative to the primary image.

All values are in SI base units (meters, radians). Results returned as
millimetres are labelled ``_mm``.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .models import (
    OpticalSystem, Ray, ThinLens, ThickLens, SphericalSurface, Mirror,
    ApertureStop,
)
from .materials import refractive_index
from .real_rays import (
    _sphere_intersection, _snell_refract, trace_real_ray,
    real_intercept_at_plane,
)


# Index of the medium filling the spaces between elements.
N_AIR = 1.0

# Nominal edge thickness assumed when deriving a thin lens centre thickness.
DEFAULT_EDGE_THICKNESS = 1.0e-3   # 1 mm


# =============================================================================
# Fresnel reflectance
# =============================================================================

def normal_incidence_reflectance(n1: float, n2: float) -> float:
    """Fresnel power reflectance at normal incidence, R = ((n1-n2)/(n1+n2))^2."""
    if n1 + n2 <= 0:
        return 0.0
    return ((n1 - n2) / (n1 + n2)) ** 2


def fresnel_reflectance(n1: float, n2: float, theta_i: float = 0.0,
                        polarization: str = "avg") -> float:
    """
    Fresnel power reflectance at a dielectric interface.

    Args:
        n1: Index of the incident medium.
        n2: Index of the transmitting medium.
        theta_i: Angle of incidence (radians).
        polarization: "s", "p", or "avg" for the unpolarised mean.

    Returns:
        Power reflectance (0 to 1); 1.0 at total internal reflection.
    """
    if n1 <= 0 or n2 <= 0:
        return 0.0
    sin_t = (n1 / n2) * math.sin(theta_i)
    if abs(sin_t) >= 1.0:
        return 1.0  # total internal reflection
    theta_t = math.asin(sin_t)
    cos_i = math.cos(theta_i)
    cos_t = math.cos(theta_t)
    denom_s = n1 * cos_i + n2 * cos_t
    denom_p = n1 * cos_t + n2 * cos_i
    rs = ((n1 * cos_i - n2 * cos_t) / denom_s) ** 2 if denom_s > 0 else 1.0
    rp = ((n1 * cos_t - n2 * cos_i) / denom_p) ** 2 if denom_p > 0 else 1.0
    p = (polarization or "avg").strip().lower()
    if p == "s":
        return rs
    if p == "p":
        return rp
    return 0.5 * (rs + rp)


# =============================================================================
# Surface chain
# =============================================================================

@dataclass
class GhostSurface:
    """One refracting or reflecting surface of the flattened system."""
    index: int
    z: float
    radius: float          # signed radius of curvature (0 = plane)
    n_left: float
    n_right: float
    label: str             # e.g. "L1.front"
    reflective: bool = False

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        kind = "mirror" if self.reflective else f"{self.n_left:g}->{self.n_right:g}"
        return f"[{self.index}] {self.label} z={self.z * 1e3:.3f}mm R={self.radius * 1e3:.3f}mm {kind}"


def _lens_centre_thickness(radius: float, semi_aperture: float,
                           edge_thickness: float = DEFAULT_EDGE_THICKNESS) -> float:
    """
    Estimate a biconvex lens centre thickness from its surface sagitta.

    A lens with curvature radius R and semi-aperture h has sagitta
    s = |R| - sqrt(R^2 - h^2). A biconvex element is roughly two of those
    plus an edge thickness, so t ~ 2 s + edge.

    Falls back to the edge thickness when the geometry is degenerate
    (a plane surface, or a semi-aperture at or beyond the radius).
    """
    if abs(radius) < 1e-12 or semi_aperture <= 0:
        return edge_thickness
    if semi_aperture >= abs(radius):
        return edge_thickness
    sag = abs(radius) - math.sqrt(radius * radius - semi_aperture * semi_aperture)
    return 2.0 * sag + edge_thickness


def _thin_lens_surfaces(comp: ThinLens, wavelength: float,
                        edge_thickness: float) -> list[GhostSurface]:
    """Two biconvex surfaces for a ThinLens (see module docstring)."""
    n = refractive_index(comp.material, wavelength)
    f = comp.focal_length
    if abs(f) < 1e-15:
        return []
    radius = 2.0 * (n - 1.0) * f
    semi = max(0.0, comp.aperture_diameter / 2.0)
    thickness = _lens_centre_thickness(radius, semi, edge_thickness)
    return [
        GhostSurface(index=0, z=comp.position, radius=radius,
                     n_left=N_AIR, n_right=n, label=f"{comp.id}.front"),
        GhostSurface(index=0, z=comp.position + thickness, radius=-radius,
                     n_left=n, n_right=N_AIR, label=f"{comp.id}.back"),
    ]


def _thick_lens_surfaces(comp: ThickLens, wavelength: float) -> list[GhostSurface]:
    """Two exact surfaces separated by the real glass thickness."""
    n = refractive_index(comp.material, wavelength)
    return [
        GhostSurface(index=0, z=comp.position, radius=comp.radius1,
                     n_left=N_AIR, n_right=n, label=f"{comp.id}.front"),
        GhostSurface(index=0, z=comp.position + comp.thickness, radius=comp.radius2,
                     n_left=n, n_right=N_AIR, label=f"{comp.id}.back"),
    ]


def build_surface_chain(system: OpticalSystem,
                        wavelength: Optional[float] = None,
                        edge_thickness: float = DEFAULT_EDGE_THICKNESS,
                        ) -> list[GhostSurface]:
    """
    Flatten a system into an ordered list of refracting/reflecting surfaces.

    Args:
        system: The optical system.
        wavelength: Wavelength for the refractive index lookup; defaults to
            the system analysis wavelength.
        edge_thickness: Nominal edge thickness used for thin-lens geometry.

    Returns:
        Surfaces sorted by position, with sequential indices assigned.
    """
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength

    surfaces: list[GhostSurface] = []
    for comp in sorted(system.components, key=lambda c: c.position):
        if isinstance(comp, ThinLens):
            surfaces.extend(_thin_lens_surfaces(comp, wavelength, edge_thickness))
        elif isinstance(comp, ThickLens):
            surfaces.extend(_thick_lens_surfaces(comp, wavelength))
        elif isinstance(comp, Mirror):
            surfaces.append(GhostSurface(
                index=0, z=comp.position, radius=getattr(comp, "radius", 0.0) or 0.0,
                n_left=N_AIR, n_right=N_AIR, label=f"{comp.id}.mirror",
                reflective=True,
            ))
        elif isinstance(comp, SphericalSurface):
            n = refractive_index(comp.material, wavelength) if comp.material else N_AIR
            surfaces.append(GhostSurface(
                index=0, z=comp.position, radius=comp.radius,
                n_left=N_AIR, n_right=n, label=comp.id,
            ))
        # ApertureStop and non-refracting components are not surfaces.

    surfaces.sort(key=lambda s: s.z)
    for i, s in enumerate(surfaces):
        s.index = i
    return surfaces


# =============================================================================
# Bidirectional surface interaction
# =============================================================================

def _intersect_surface(z: float, y: float, dz: float, dy: float, surf: GhostSurface):
    """
    Intersect a ray with a surface, ahead of the ray.

    Returns (z, y, nx, ny) with an outward unit normal, or None on a miss.
    Plane surfaces use a normal along the axis.
    """
    if abs(surf.radius) < 1e-12:
        if abs(dz) < 1e-15:
            return None
        t = (surf.z - z) / dz
        if t < 1e-12:
            return None
        return z + t * dz, y + t * dy, 1.0, 0.0

    hit = _sphere_intersection(z, y, dz, dy, surf.z, surf.radius)
    if hit is None:
        return None
    hz, hy = hit
    nx = (hz - (surf.z + surf.radius)) / surf.radius
    ny = hy / surf.radius
    norm = math.hypot(nx, ny)
    if norm < 1e-15:
        return None
    return hz, hy, nx / norm, ny / norm


def _interact(z: float, y: float, dz: float, dy: float, surf: GhostSurface,
              action: str, forward: bool, wavelength: float,
              coating_reflectance: Optional[float] = None,
              mirror_reflectance: float = 0.95,
              polarization: str = "avg"):
    """
    Propagate a ray to one surface and apply either refraction or reflection.

    Args:
        z, y, dz, dy: Current ray state (unit direction).
        surf: The surface to hit.
        action: "transmit" or "reflect".
        forward: True if the ray is travelling toward increasing z.
        wavelength: Wavelength in meters (index bookkeeping only).
        coating_reflectance: If given, overrides the Fresnel reflectance of
            every surface with this value (models a uniform AR coating).
        mirror_reflectance: Reflectance used at surfaces marked reflective.
        polarization: Passed to the Fresnel calculation.

    Returns:
        (z, y, dz, dy, factor) where factor is the power fraction retained
        by this interaction, or None if the ray misses, is blocked, or
        suffers total internal reflection.
    """
    hit = _intersect_surface(z, y, dz, dy, surf)
    if hit is None:
        return None
    hz, hy, nx, ny = hit

    # Orient the normal to face the incoming ray, then get the incidence angle.
    nd = nx * dz + ny * dy
    if nd > 0.0:
        nx, ny, nd = -nx, -ny, -nd
    cos_i = max(-1.0, min(1.0, -nd))
    theta_i = math.acos(cos_i)

    reflecting = surf.reflective or action == "reflect"

    if surf.reflective and not reflecting:
        # A mirror is opaque: nothing is transmitted through it.
        return None

    # Reflectance of this surface at this incidence angle.
    if surf.reflective:
        r = mirror_reflectance
    elif coating_reflectance is not None:
        r = coating_reflectance
    elif forward:
        r = fresnel_reflectance(surf.n_left, surf.n_right, theta_i, polarization)
    else:
        r = fresnel_reflectance(surf.n_right, surf.n_left, theta_i, polarization)
    r = max(0.0, min(1.0, r))

    if reflecting:
        nz_new = dz - 2.0 * nd * nx
        ny_new = dy - 2.0 * nd * ny
        norm = math.hypot(nz_new, ny_new)
        if norm < 1e-15:
            return None
        return hz, hy, nz_new / norm, ny_new / norm, r

    # Transmit: refract from the incident medium into the outgoing medium.
    if forward:
        n1, n2 = surf.n_left, surf.n_right
    else:
        n1, n2 = surf.n_right, surf.n_left
    out = _snell_refract(dz, dy, nx, ny, n1, n2)
    if out is None:
        return None  # total internal reflection
    return hz, hy, out[0], out[1], 1.0 - r


# =============================================================================
# Ghost path tracing
# =============================================================================

@dataclass
class GhostResult:
    """One double-reflection ghost path and its image-plane consequences."""
    first_surface: int
    second_surface: int
    first_label: str
    second_label: str
    wavelength: float = 0.0
    blocked: bool = False
    blocked_at: str = ""

    # Energy
    first_reflectance: float = 0.0
    second_reflectance: float = 0.0
    transmission: float = 1.0
    reflectance_product: float = 0.0

    # Geometry
    ghost_image_height: float = 0.0      # m, at the image plane
    primary_image_height: float = 0.0    # m, chief ray at the image plane
    displacement: float = 0.0            # m, ghost minus primary
    ghost_focus_z: float = 0.0           # m, axial ghost focus
    ghost_focus_offset: float = 0.0      # m, focus offset from image plane
    ghost_spot_rms: float = 0.0          # m, RMS spot at the ghost focus
    ghost_spot_rms_at_image: float = 0.0  # m, RMS spot at the image plane
    focus_clipped: bool = False          # focus fell on the scan boundary
    num_rays: int = 0                    # pupil rays that completed the path
    num_rays_attempted: int = 0          # pupil rays tried
    path: list = field(default_factory=list)

    @property
    def relative_irradiance(self) -> float:
        """
        Ghost irradiance relative to the primary image.

        For a small ghost spot the irradiance ratio equals the throughput
        along the ghost path: the product of the two reflectances and the
        (1 - R) transmission of every surface crossed.
        """
        return self.transmission

    def as_dict(self) -> dict:
        """Return the result as a JSON-friendly dict (millimetres)."""
        return {
            "first_surface": self.first_surface,
            "second_surface": self.second_surface,
            "first_label": self.first_label,
            "second_label": self.second_label,
            "order": 2,
            "blocked": self.blocked,
            "blocked_at": self.blocked_at,
            "wavelength_m": self.wavelength,
            "first_reflectance": self.first_reflectance,
            "second_reflectance": self.second_reflectance,
            "reflectance_product": self.reflectance_product,
            "transmission": self.transmission,
            "relative_irradiance": self.relative_irradiance,
            "ghost_image_height_mm": self.ghost_image_height * 1e3,
            "primary_image_height_mm": self.primary_image_height * 1e3,
            "displacement_mm": self.displacement * 1e3,
            "ghost_focus_z_mm": self.ghost_focus_z * 1e3,
            "ghost_focus_offset_mm": self.ghost_focus_offset * 1e3,
            "ghost_spot_rms_mm": self.ghost_spot_rms * 1e3,
            "ghost_spot_rms_at_image_mm": self.ghost_spot_rms_at_image * 1e3,
            "focus_clipped": self.focus_clipped,
            "num_rays": self.num_rays,
            "num_rays_attempted": self.num_rays_attempted,
        }


def trace_ghost_path(surfaces: list, ray: Ray, first: int, second: int,
                     image_z: float,
                     coating_reflectance: Optional[float] = None,
                     mirror_reflectance: float = 0.95,
                     polarization: str = "avg"):
    """
    Trace one double-reflection ghost path.

    The ray travels forward to surface ``first``, reflects, travels back to
    surface ``second``, reflects again, then proceeds forward to the image
    plane. See the module docstring for the full definition.

    Args:
        surfaces: Surface chain from :func:`build_surface_chain`.
        ray: The input ray, starting at the object.
        first: Index of the first reflecting surface.
        second: Index of the second reflecting surface (must be < first).
        image_z: Image plane position (meters).
        coating_reflectance: Optional uniform surface reflectance override.
        mirror_reflectance: Reflectance used at reflective surfaces.
        polarization: Passed to the Fresnel calculation.

    Returns:
        (path, first_reflectance, second_reflectance, transmission, None) on
        success, or (None, 0.0, 0.0, 0.0, blocked_label) when the ray does
        not complete the path. The label is an empty string if the failure
        is geometric rather than an aperture block.
    """
    n_surfaces = len(surfaces)
    if first >= n_surfaces or second < 0 or second >= first:
        return None, 0.0, 0.0, 0.0, "invalid_pair"

    dz = math.cos(ray.theta)
    dy = math.sin(ray.theta)
    z, y = ray.z, ray.y
    points = [[z, y]]

    transmission = 1.0
    r_first = 0.0
    r_second = 0.0

    def _step(index, action, forward):
        nonlocal z, y, dz, dy, transmission, r_first, r_second
        res = _interact(z, y, dz, dy, surfaces[index], action, forward,
                        ray.wavelength, coating_reflectance,
                        mirror_reflectance, polarization)
        if res is None:
            return surfaces[index].label
        z, y, dz, dy, factor = res
        points.append([z, y])
        transmission *= factor
        if index == first and action == "reflect":
            r_first = factor
        if index == second and action == "reflect":
            r_second = factor
        return None

    # Leg A: forward from the object to the first reflecting surface.
    for k in range(0, first + 1):
        failed = _step(k, "reflect" if k == first else "transmit", True)
        if failed is not None:
            return None, r_first, r_second, transmission, failed

    # Leg B: backward toward the object, re-crossing earlier surfaces.
    for k in range(first - 1, second - 1, -1):
        if k < 0:
            return None, r_first, r_second, transmission, "invalid_pair"
        failed = _step(k, "reflect" if k == second else "transmit", False)
        if failed is not None:
            return None, r_first, r_second, transmission, failed

    # Leg C: forward again through every remaining surface.
    for k in range(second + 1, n_surfaces):
        failed = _step(k, "transmit", True)
        if failed is not None:
            return None, r_first, r_second, transmission, failed

    # Propagate to the image plane.
    if abs(dz) > 1e-15:
        y_image = y + (image_z - z) * (dy / dz)
    else:
        y_image = y
    points.append([image_z, y_image])

    return points, r_first, r_second, transmission, None


# =============================================================================
# System-level ghost analysis
# =============================================================================

def _pupil(system: OpticalSystem):
    """(entrance-pupil z, entrance-pupil radius, object-space field slope)
    from the paraxial first-order solution."""
    from . import raytrace as rt
    fo = rt.first_order(system)
    return fo.entrance_pupil_z, fo.entrance_pupil_semi_diameter, fo


def _ray_through_pupil(system: OpticalSystem, field_fraction: float, p: float,
                       kind: str) -> Ray:
    ep_z, ep_r, fo = _pupil(system)
    wl = system.analysis_settings.wavelength
    if fo.object_infinite:
        u = fo.chief.u_object_space * field_fraction
        z0 = min(c.position for c in system.components) - 2.0 * ep_r - 1e-3
        y0 = p * ep_r + u * (z0 - ep_z)
        return Ray(y=y0, theta=math.atan(u), z=z0, wavelength=wl, ray_type=kind)
    obj_h = system.object.height * field_fraction
    d = ep_z - system.object.position
    theta = math.atan((p * ep_r - obj_h) / d) if abs(d) > 1e-15 else 0.0
    return Ray(y=obj_h, theta=theta, z=system.object.position, wavelength=wl, ray_type=kind)


def chief_ray(system: OpticalSystem, field_fraction: float = 1.0) -> Ray:
    """Chief ray for a field point: through the centre of the entrance pupil."""
    return _ray_through_pupil(system, field_fraction, 0.0, "chief")


def pupil_fan(system: OpticalSystem, field_fraction: float = 1.0,
              num_rays: int = 5) -> list:
    """
    Meridional rays sampling the paraxial entrance pupil from -1 to +1.
    A single ray returns the chief ray.
    """
    n = max(1, int(num_rays))
    fractions = [0.0] if n == 1 else np.linspace(-1.0, 1.0, n)
    return [_ray_through_pupil(system, field_fraction, float(p), "fill") for p in fractions]


def _trace_primary(surfaces: list, ray: Ray, image_z: float) -> Optional[float]:
    """Image-plane height of a ray transmitted through every surface of the
    ghost surface chain (the same geometry the ghost paths use)."""
    z, y = ray.z, ray.y
    dz, dy = math.cos(ray.theta), math.sin(ray.theta)
    for surf in surfaces:
        res = _interact(z, y, dz, dy, surf, "transmit", True, ray.wavelength)
        if res is None:
            return None
        z, y, dz, dy, _ = res
    if abs(dz) < 1e-15:
        return None
    return y + (image_z - z) * dy / dz


def primary_image_height(system: OpticalSystem, field_fraction: float = 1.0) -> float:
    """
    Chief-ray image height (meters) through the ghost surface chain, the
    reference for ghost displacement.
    """
    surfaces = build_surface_chain(system)
    h = _trace_primary(surfaces, chief_ray(system, field_fraction),
                       system.image_plane.position)
    if h is None:
        raise ValueError("The chief ray does not reach the image plane")
    return float(h)


def _ghost_focus(paths: list, image_z: float,
                 scan_mm: Optional[float] = None, points: int = 81):
    """
    Find the axial ghost focus by minimising the RMS spot over z.

    Each path's final segment is a straight line, so the height at any plane
    beyond the last surface is an exact extrapolation.

    Args:
        paths: Ghost ray paths (list of [z, y] point lists).
        image_z: Image plane position (meters).
        scan_mm: Half-range of the axial scan in millimetres. ``None``
            chooses a range from the image distance, because intra-element
            ghosts can focus very far from the image plane.
        points: Number of planes in the scan.

    Returns:
        (focus_z, rms_at_focus, rms_at_image_plane, focus_clipped).
        ``focus_clipped`` is True when the minimiser landed on the edge of
        the scan, meaning the true focus lies outside the searched range.
    """
    if not paths:
        return image_z, 0.0, 0.0, False
    at_image = [real_intercept_at_plane(p, image_z) for p in paths]
    rms_image = float(np.std(at_image))
    if len(paths) < 2:
        # A single ray defines no spot: report the focus as the image plane
        # and leave the RMS values at zero so the caller can tell the
        # statistics apart from a genuinely perfect ghost focus.
        return image_z, 0.0, rms_image, False

    if scan_mm is None:
        # A ghost can focus anywhere from just inside the first element to
        # well beyond the image plane, so search a range that scales with the
        # image distance rather than a fixed window.
        scan_mm = max(20.0, abs(image_z) * 1e3 * 1.2)
    lo = image_z - scan_mm * 1e-3
    hi = image_z + scan_mm * 1e-3
    n = max(3, points)

    def _rms(z: float) -> float:
        return float(np.std([real_intercept_at_plane(p, z) for p in paths]))

    zs = np.linspace(lo, hi, n)
    values = [_rms(float(z)) for z in zs]
    k = int(np.argmin(values))
    best_z, best_rms = float(zs[k]), values[k]

    # Refine around the coarse minimum: a wide search range costs
    # resolution, and a ghost focus can be very sharp.
    step = (hi - lo) / (n - 1)
    for _ in range(3):
        step *= 0.25
        for z in np.linspace(best_z - step, best_z + step, 21):
            r = _rms(float(z))
            if r < best_rms:
                best_rms, best_z = r, float(z)

    clipped = bool(best_z <= lo + 1e-15 or best_z >= hi - 1e-15)
    return best_z, best_rms, rms_image, clipped


def analyze_ghosts(system: OpticalSystem,
                   field_fraction: float = 1.0,
                   num_rays: int = 5,
                   min_relative_irradiance: float = 1.0e-6,
                   coating_reflectance: Optional[float] = None,
                   mirror_reflectance: float = 0.95,
                   polarization: str = "avg",
                   focus_scan_mm: Optional[float] = None,
                   focus_points: int = 41,
                   surface_pairs: Optional[list] = None,
                   include_blocked: bool = False,
                   ) -> list:
    """
    Trace every double-reflection ghost of a system with real ray paths.

    Args:
        system: The optical system.
        field_fraction: Field point to analyse (0 = axis, 1 = edge).
        num_rays: Pupil rays per ghost path, used for the focus and spot
            statistics. One is enough for the geometry; more give a
            meaningful RMS spot.
        min_relative_irradiance: Ghosts fainter than this are dropped.
        coating_reflectance: Uniform surface reflectance override (models an
            AR coating). ``None`` uses the Fresnel reflectance.
        mirror_reflectance: Reflectance assumed at mirror surfaces.
        polarization: Passed to the Fresnel calculation.
        focus_scan_mm: Half-range of the axial scan used to find the ghost
            focus, in millimetres. ``None`` scales it with the image distance.
        focus_points: Number of planes in the focus scan.
        surface_pairs: Optional explicit list of (second, first) index
            pairs; default is every combination.
        include_blocked: Keep ghosts whose rays never reach the image.

    Returns:
        List of :class:`GhostResult` sorted by relative irradiance,
        brightest first.
    """
    surfaces = build_surface_chain(system)
    if len(surfaces) < 2:
        return []

    image_z = system.image_plane.position
    rays = pupil_fan(system, field_fraction, num_rays)
    primary_h = primary_image_height(system, field_fraction)

    if surface_pairs is None:
        pairs = [(s, f) for f in range(len(surfaces)) for s in range(f)]
    else:
        pairs = list(surface_pairs)

    results = []
    for second, first in pairs:
        if second >= first or second < 0 or first >= len(surfaces):
            continue

        paths = []
        r_first = r_second = 0.0
        transmission = 1.0
        blocked_at = ""
        for ray in rays:
            path, rf, rs, tr, fail = trace_ghost_path(
                surfaces, ray, first, second, image_z,
                coating_reflectance=coating_reflectance,
                mirror_reflectance=mirror_reflectance,
                polarization=polarization,
            )
            if path is None:
                blocked_at = blocked_at or (fail or "")
                continue
            paths.append(path)
            r_first, r_second, transmission = rf, rs, tr

        if not paths:
            if not include_blocked:
                continue
            results.append(GhostResult(
                first_surface=first, second_surface=second,
                first_label=surfaces[first].label,
                second_label=surfaces[second].label,
                wavelength=system.analysis_settings.wavelength,
                blocked=True, blocked_at=blocked_at,
                primary_image_height=primary_h,
                num_rays=0, num_rays_attempted=len(rays),
            ))
            continue

        heights = [p[-1][1] for p in paths]
        ghost_h = float(np.mean(heights))
        focus_z, rms_focus, rms_image, focus_clipped = _ghost_focus(
            paths, image_z, focus_scan_mm, focus_points)

        result = GhostResult(
            first_surface=first, second_surface=second,
            first_label=surfaces[first].label,
            second_label=surfaces[second].label,
            wavelength=system.analysis_settings.wavelength,
            first_reflectance=r_first,
            second_reflectance=r_second,
            transmission=transmission,
            reflectance_product=r_first * r_second,
            ghost_image_height=ghost_h,
            primary_image_height=primary_h,
            displacement=ghost_h - primary_h,
            ghost_focus_z=focus_z,
            ghost_focus_offset=focus_z - image_z,
            ghost_spot_rms=rms_focus,
            ghost_spot_rms_at_image=rms_image,
            focus_clipped=focus_clipped,
            num_rays=len(paths),
            num_rays_attempted=len(rays),
            path=paths[0],
        )
        if not include_blocked and result.relative_irradiance < min_relative_irradiance:
            continue
        results.append(result)

    results.sort(key=lambda g: g.relative_irradiance, reverse=True)
    return results


def ghost_analysis(system: OpticalSystem, **kwargs) -> dict:
    """
    Ghost analysis summary across the field.

    Calls :func:`analyze_ghosts` at the axis and at the edge of the field and
    returns the brightest ghost paths at each, plus the worst ghost overall.

    Any keyword argument accepted by :func:`analyze_ghosts` may be passed.
    """
    per_field = {}
    worst = None
    for name, ff in (("axis", 0.0), ("edge", 1.0)):
        ghosts = analyze_ghosts(system, field_fraction=ff, **kwargs)
        per_field[name] = [g.as_dict() for g in ghosts]
        if ghosts:
            candidate = ghosts[0]
            if worst is None or candidate.relative_irradiance > worst[1].relative_irradiance:
                worst = (name, candidate)

    surfaces = build_surface_chain(system)
    return {
        "num_surfaces": len(surfaces),
        "surfaces": [
            {
                "index": s.index, "label": s.label,
                "z_mm": s.z * 1e3, "radius_mm": s.radius * 1e3,
                "n_left": s.n_left, "n_right": s.n_right,
                "reflective": s.reflective,
            }
            for s in surfaces
        ],
        "axis_ghosts": per_field.get("axis", []),
        "edge_ghosts": per_field.get("edge", []),
        "num_axis_ghosts": len(per_field.get("axis", [])),
        "num_edge_ghosts": len(per_field.get("edge", [])),
        "worst_field": worst[0] if worst else None,
        "worst_ghost": worst[1].as_dict() if worst else None,
        "worst_relative_irradiance": worst[1].relative_irradiance if worst else 0.0,
    }
