"""
Stray light: ghosts, scatter (PST) and narcissus.

- **Ghost reflections** are traced with real double-reflection ray paths by
  :mod:`optics.ghost`; this module ranks them. (A single reflection sends
  light back out of the system, so detector ghosts are even-order.)
- **Scatter / PST**: first-order estimate. A surface whose clear aperture is
  illuminated by an off-axis source scatters with radiance L = BSDF * E_s;
  by conservation of radiance, the irradiance it produces on the detector
  is E_det = BSDF * E_s * pi NA'^2, where NA' is the image-space numerical
  aperture (the scattering surface is assumed to fill the cone that
  converges on the detector point). With E_s = coverage * E_in the point
  source transmittance is

      PST(theta) = sum_i coverage_i(theta) * BSDF_i * pi * NA'^2

  coverage_i is the fraction of the source beam (entering the first clear
  aperture) that reaches surface i unvignetted, from real rays. Surface
  transmission losses are neglected. Valid for an object at infinity.
- **Narcissus**: the YNI metric (Lloyd, *Thermal Imaging Systems*, 1975):
  for each surface the product of the paraxial marginal-ray height y, the
  index n and the paraxial incidence angle i. A surface with small |YNI|
  retro-reflects the detector's own image onto itself; the cold return is
  strongest there.

All values are in SI units.
"""

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .models import OpticalSystem
from . import raytrace as rt

# =============================================================================
# Ghost reflections
# =============================================================================


@dataclass
class GhostPath:
    """A double-reflection ghost path."""

    surfaces: tuple[int, int]  # (second reflecting surface, first reflecting surface)
    reflection_count: int
    relative_intensity: float  # ghost irradiance relative to the primary image
    image_position: float  # ghost focus minus image-plane position (m)
    is_in_field: bool  # ghost lands within the primary image height at the image plane
    description: str


def analyze_ghost_reflections(
    system: OpticalSystem,
    n_reflections: int = 2,
    threshold: float = 1e-6,
    coating_reflectance: Optional[float] = None,
) -> list:
    """
    Real-ray double-reflection ghosts brighter than ``threshold``.

    Args:
        n_reflections: Only 2 (double reflection) is supported.
        coating_reflectance: Uniform surface reflectance (AR coating); None
            uses the Fresnel reflectance of each uncoated surface.
    """
    if n_reflections != 2:
        raise ValueError("Only double-reflection (order 2) ghosts reach the detector")
    from .ghost import analyze_ghosts

    ghosts = analyze_ghosts(
        system,
        field_fraction=0.0,
        num_rays=5,
        min_relative_irradiance=threshold,
        coating_reflectance=coating_reflectance,
    )
    h_img = abs(rt.first_order(system).image_height)
    out = []
    for g in ghosts:
        out.append(
            GhostPath(
                surfaces=(g.second_surface, g.first_surface),
                reflection_count=2,
                relative_intensity=g.relative_irradiance,
                image_position=g.ghost_focus_offset,
                is_in_field=abs(g.ghost_image_height)
                <= h_img + g.ghost_spot_rms_at_image,
                description=f"{g.first_label} then {g.second_label}",
            )
        )
    return out


# =============================================================================
# BRDF / BSDF models
# =============================================================================


@dataclass
class BRDFParameters:
    """
    Scatter model parameters.

    model "lambertian": BSDF = diffuse_fraction / pi.
    model "abg": Harvey-Shack ABg, BSDF = A / (B + |beta - beta0|^G), with
        beta the direction cosine (sin of the angle to the surface normal)
        and beta0 that of the specular direction.
    model "gaussian": total scatter ``diffuse_fraction`` spread as a 2D
        Gaussian of width ``sigma`` in direction-cosine space,
        BSDF = TS exp(-d^2 / 2 sigma^2) / (2 pi sigma^2 cos theta_s).
    """

    model: str
    A: float = 0.0
    B: float = 1.0
    G: float = 0.0
    sigma: float = 0.0
    diffuse_fraction: float = 0.0


def compute_brdf(angle_in: float, angle_out: float, params: BRDFParameters) -> float:
    """BSDF (1/sr) for the specular angle ``angle_in`` and scatter angle
    ``angle_out``, both from the surface normal (radians)."""
    model = params.model.lower()
    if model == "lambertian":
        return params.diffuse_fraction / math.pi
    d = abs(math.sin(angle_out) - math.sin(angle_in))
    if model == "abg":
        return params.A / (params.B + d**params.G)
    if model == "gaussian":
        if params.sigma <= 0:
            raise ValueError("Gaussian scatter needs sigma > 0")
        return (
            params.diffuse_fraction
            * math.exp(-0.5 * (d / params.sigma) ** 2)
            / (2.0 * math.pi * params.sigma**2 * max(math.cos(angle_out), 1e-6))
        )
    raise ValueError(f"Unknown BRDF model '{params.model}'")


# =============================================================================
# Scatter and point source transmittance
# =============================================================================


@dataclass
class StrayLightPath:
    """Scatter contribution of one surface."""

    path_id: int
    source_surface: int  # surface index in the sequence
    scatter_surface: int  # same surface (first-order scatter)
    detector_position: float
    relative_intensity: float  # contribution to the PST
    path_type: str
    description: str


def _coverage(system: OpticalSystem, seq, angle_rad: float, n: int = 15) -> np.ndarray:
    """Fraction of a collimated beam at ``angle_rad`` (filling the first
    clear aperture) that reaches each surface unvignetted."""
    first = seq.surfaces[0]
    semi = first.semi_aperture or max((s.semi_aperture or 0.0) for s in seq.surfaces)
    g = np.linspace(-1.0, 1.0, n)
    X, Y = np.meshgrid(g, g)
    m = X**2 + Y**2 <= 1.0
    x, y = X[m] * semi, Y[m] * semi
    d = np.array([0.0, math.sin(angle_rad), math.cos(angle_rad)])
    z0 = first.z - 1e-3
    # start on a plane in front of the first surface, aimed through its aperture
    p0 = np.stack([x, y - d[1] / d[2] * 1e-3, np.full_like(x, z0)], axis=1)
    d0 = np.tile(d, (len(x), 1))
    cov = np.zeros(len(seq.surfaces))
    for i in range(len(seq.surfaces)):
        sub = rt.Sequence(
            seq.surfaces[: i + 1],
            seq.wavelength,
            seq.object_z,
            seq.object_height,
            True,
            seq.surfaces[i].z,
            seq.surfaces[i].origin,
            seq.surfaces[i].rotation,
            1,
            seq.n_object,
            seq.n_image,
            0,
        )
        b = rt.trace_bundle(sub, p0, d0, clip=True)
        cov[i] = b.valid.mean()
    return cov


def analyze_stray_light(
    system: OpticalSystem,
    source_angle: float = 30.0,
    brdf_params: Optional[BRDFParameters] = None,
    n_scatter_events: int = 1,
) -> list:
    """
    First-order scatter contribution of every refracting/reflecting surface
    for a point source ``source_angle`` degrees off axis (see module notes).
    """
    if n_scatter_events != 1:
        raise ValueError("Only first-order (single) scatter is modelled")
    if brdf_params is None:
        raise ValueError("A scatter model (brdf_params) is required")
    seq = rt.build_sequence(system)
    if not seq.object_infinite:
        raise ValueError("PST is defined for a source at infinity (object at infinity)")
    from .pupil import image_space_na

    na = image_space_na(system, seq=seq)
    th = math.radians(source_angle)
    cov = _coverage(system, seq, th)
    paths: list = []
    for i, s in enumerate(seq.surfaces):
        if s.kind not in ("refract", "reflect"):
            continue
        # specular direction ~ the source direction; detector-bound scatter ~ axial
        bsdf = compute_brdf(th, 0.0, brdf_params)
        contrib = cov[i] * bsdf * math.pi * na * na
        paths.append(
            StrayLightPath(
                path_id=len(paths),
                source_surface=i,
                scatter_surface=i,
                detector_position=system.image_plane.position,
                relative_intensity=float(contrib),
                path_type="scatter",
                description=f"Scatter from {s.label} (beam coverage {cov[i]:.2f})",
            )
        )
    paths.sort(key=lambda p: p.relative_intensity, reverse=True)
    return paths


def compute_pst(
    system: OpticalSystem,
    angles: np.ndarray,
    brdf_params: Optional[BRDFParameters] = None,
) -> np.ndarray:
    """First-order PST (dB, 10 log10) versus source angle in degrees."""
    out = []
    for a in np.asarray(angles, dtype=float):
        total = sum(
            p.relative_intensity
            for p in analyze_stray_light(system, float(a), brdf_params)
        )
        out.append(10.0 * math.log10(total) if total > 0 else -math.inf)
    return np.array(out)


# =============================================================================
# Narcissus (YNI)
# =============================================================================


def analyze_narcissus(system: OpticalSystem) -> list:
    """
    YNI narcissus metric of every surface, smallest |YNI| (worst) first.

    YNI = y * n * i with y the paraxial marginal-ray height, n the index
    before the surface and i = u + y c the paraxial incidence angle. The
    ratio to the largest |YNI| is reported as ``relative_yni``.
    """
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    idx = rt.signed_indices(seq)
    m = fo.marginal
    rows = []
    for i, s in enumerate(seq.surfaces):
        if s.kind not in ("refract", "reflect"):
            continue
        nb = idx[i][0]
        inc = m.u_before[i] + m.y[i] * s.curvature
        rows.append(
            {"surface_index": i, "surface_id": s.label, "yni": float(m.y[i] * nb * inc)}
        )
    big = max((abs(r["yni"]) for r in rows), default=0.0)
    for r in rows:
        r["relative_yni"] = abs(r["yni"]) / big if big > 0 else 0.0
        r["description"] = f"YNI at {r['surface_id']}"
    rows.sort(key=lambda r: abs(r["yni"]))
    return rows
