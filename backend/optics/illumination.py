"""
Vignetting, relative illumination, and MTF field/focus maps.

- **Vignetting**: real rays are aimed across the aperture stop
  (:mod:`optics.raytrace`); a ray that falls outside any surface's clear
  aperture is vignetted, and the surface that blocks it is recorded.
- **Relative illumination**: image irradiance from a Lambertian object is
  E = L * Omega_p, with Omega_p the projected solid angle of the ray bundle
  converging on the image point (radiance is conserved through lossless
  optics). Omega_p is the area of the bundle in image-space direction-cosine
  space (dL dM = cos(theta) dOmega), measured from a grid of real rays. The
  relative illumination is Omega_p(field) / Omega_p(axis); it includes
  vignetting, pupil distortion and obliquity. The thin-lens cos^4 law is
  reported alongside for comparison. Surface transmission losses are not
  included.
- **MTF maps**: diffraction MTF from the real pupil function by FFT
  (:mod:`optics.pupil`), tangential and sagittal.

All values are in SI base units unless a key says otherwise.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .models import OpticalSystem, ImagePlane
from . import raytrace as rt
from . import pupil as pp


# =============================================================================
# Vignetting
# =============================================================================

@dataclass
class VignettingResult:
    """Vignetting at one field point."""
    field_fraction: float
    field_angle: float              # radians, chief ray at the image
    throughput: float               # fraction of the stop area whose rays reach the image
    pupil_samples: int
    passing_samples: int
    clipped_by: dict = field(default_factory=dict)

    @property
    def is_vignetted(self) -> bool:
        return self.throughput < 0.999

    @property
    def loss_percent(self) -> float:
        return max(0.0, (1.0 - self.throughput) * 100.0)

    def as_dict(self) -> dict:
        return {
            "field_fraction": self.field_fraction,
            "field_angle_rad": self.field_angle,
            "field_angle_deg": math.degrees(self.field_angle),
            "throughput": self.throughput,
            "loss_percent": self.loss_percent,
            "is_vignetted": self.is_vignetted,
            "pupil_samples": self.pupil_samples,
            "passing_samples": self.passing_samples,
            "clipped_by": dict(self.clipped_by),
        }


def chief_ray_image_angle(system: OpticalSystem, field_fraction: float) -> float:
    """Angle between the real chief ray and the image-plane normal (radians)."""
    b, seq, _ = rt.trace_field_rays(system, 0.0, field_fraction, np.array([0.0]),
                                    np.array([0.0]), clip=False)
    if not b.valid[0]:
        raise ValueError("Chief ray cannot be traced at this field")
    axis = seq.image_rotation[:, 2]
    c = abs(float(np.dot(b.directions[0], axis)))
    return math.acos(min(1.0, c))


def _blocking_surface(seq, b) -> list:
    """Label of the first surface whose clear aperture each ray misses (or None)."""
    out = []
    for k in range(b.points.shape[0]):
        lab = None
        for i, s in enumerate(seq.surfaces):
            if s.semi_aperture is None:
                continue
            pl = (b.points[k, i + 1] - s.origin) @ s.rotation
            if math.hypot(pl[0], pl[1]) > s.semi_aperture * (1 + 1e-9) + 1e-12:
                lab = s.component_id or s.label
                break
        out.append(lab)
    return out


def vignetting_at_field(system: OpticalSystem, field_fraction: float = 0.0,
                        num_rays: int = 21) -> VignettingResult:
    """Fraction of a uniform grid over the stop whose rays reach the image."""
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    px, py = rt.pupil_grid(num_rays)
    b, _, _ = rt.trace_field_rays(system, 0.0, field_fraction, px, py, seq=seq, fo=fo)
    clipped: dict[str, int] = {}
    if not b.valid.all():
        bb, _, _ = rt.trace_field_rays(system, 0.0, field_fraction, px[~b.valid], py[~b.valid],
                                       seq=seq, fo=fo, clip=False)
        for lab in _blocking_surface(seq, bb):
            key = lab or "failed trace"
            clipped[key] = clipped.get(key, 0) + 1
    n = len(px)
    passing = int(b.valid.sum())
    return VignettingResult(
        field_fraction=field_fraction,
        field_angle=chief_ray_image_angle(system, field_fraction),
        throughput=passing / n if n else 1.0,
        pupil_samples=n, passing_samples=passing, clipped_by=clipped,
    )


def vignetting_analysis(system: OpticalSystem, num_fields: int = 11,
                        num_rays: int = 21) -> dict:
    """Vignetting across the field and the worst case."""
    results = [vignetting_at_field(system, float(f), num_rays)
               for f in np.linspace(0.0, 1.0, num_fields)]
    worst = min(results, key=lambda r: r.throughput)
    return {
        "fields": [r.as_dict() for r in results],
        "field_fractions": [r.field_fraction for r in results],
        "throughput": [r.throughput for r in results],
        "worst_field": worst.field_fraction,
        "worst_throughput": worst.throughput,
        "worst_loss_percent": worst.loss_percent,
        "is_vignetted": any(r.is_vignetted for r in results),
    }


# =============================================================================
# Relative illumination
# =============================================================================

def cos4_falloff(field_angle: float) -> float:
    """Thin-lens cos^4 obliquity law (reference only)."""
    return math.cos(field_angle) ** 4


def projected_solid_angle(system: OpticalSystem, field_fraction: float, n: int = 31) -> float:
    """
    Projected solid angle (sr) of the real ray bundle converging on the image
    of a field point: the integral over the stop of the Jacobian of the
    image-space direction cosines (L, M) with respect to the normalised stop
    coordinates. The stop disk is integrated by Gauss-Legendre quadrature
    in radius (n // 2 nodes) and the trapezoid rule in angle (2n nodes),
    which represents its rim exactly; rays that do not reach the image
    contribute nothing. The Jacobian comes from central differences.
    """
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    nr = max(n // 2, 4)
    nt = max(2 * n, 16)
    xr, wr = np.polynomial.legendre.leggauss(nr)
    r = 0.5 * (xr + 1.0)
    wr = 0.5 * wr
    th = np.arange(nt) * (2 * np.pi / nt)
    R, T = np.meshgrid(r, th, indexing="ij")
    W = (wr[:, None] * R * (2 * np.pi / nt)).ravel()
    x, y = (R * np.cos(T)).ravel(), (R * np.sin(T)).ravel()
    h = 1e-3
    px = np.concatenate([x + h, x - h, x, x])
    py = np.concatenate([y, y, y + h, y - h])
    free, _, _ = rt.trace_field_rays(system, 0.0, field_fraction, px, py,
                                     seq=seq, fo=fo, clip=False)
    real, _, _ = rt.trace_field_rays(system, 0.0, field_fraction, x, y, seq=seq, fo=fo)
    D = (free.directions @ seq.image_rotation).reshape(4, -1, 3)
    ok = real.valid & free.valid.reshape(4, -1).all(axis=0)
    dLx = (D[0, :, 0] - D[1, :, 0]) / (2 * h)
    dMx = (D[0, :, 1] - D[1, :, 1]) / (2 * h)
    dLy = (D[2, :, 0] - D[3, :, 0]) / (2 * h)
    dMy = (D[2, :, 1] - D[3, :, 1]) / (2 * h)
    jac = np.abs(dLx * dMy - dLy * dMx)
    return float(np.sum(np.where(ok & np.isfinite(jac), jac * W, 0.0)))


@dataclass
class RelativeIlluminationPoint:
    field_fraction: float
    field_angle: float
    cos4_factor: float
    vignetting_factor: float
    relative_illumination: float

    def as_dict(self) -> dict:
        return {
            "field_fraction": self.field_fraction,
            "field_angle_deg": math.degrees(self.field_angle),
            "cos4_factor": self.cos4_factor,
            "vignetting_factor": self.vignetting_factor,
            "relative_illumination": self.relative_illumination,
        }


def relative_illumination(system: OpticalSystem, num_fields: int = 11,
                          num_rays: int = 31) -> dict:
    """Relative illumination across the field (exact projected solid angle)."""
    fields = np.linspace(0.0, 1.0, num_fields)
    omega0 = projected_solid_angle(system, 0.0, num_rays)
    if omega0 <= 0:
        raise ValueError("No rays reach the image on axis")
    pts = []
    for f in fields:
        ang = chief_ray_image_angle(system, float(f))
        v = vignetting_at_field(system, float(f), min(num_rays, 21))
        pts.append(RelativeIlluminationPoint(
            field_fraction=float(f), field_angle=ang, cos4_factor=cos4_falloff(ang),
            vignetting_factor=v.throughput,
            relative_illumination=projected_solid_angle(system, float(f), num_rays) / omega0,
        ))
    edge = pts[-1]
    return {
        "points": [p.as_dict() for p in pts],
        "field_fractions": [p.field_fraction for p in pts],
        "relative_illumination": [p.relative_illumination for p in pts],
        "cos4": [p.cos4_factor for p in pts],
        "vignetting": [p.vignetting_factor for p in pts],
        "edge_relative_illumination": edge.relative_illumination,
        "edge_loss_percent": (1.0 - edge.relative_illumination) * 100.0,
        "method": "projected solid angle of the real ray bundle",
    }


# =============================================================================
# MTF field and focus maps
# =============================================================================

def _working_f_number(system) -> float:
    """Working F-number 1 / (2 NA') from the real image-space marginal ray."""
    return 1.0 / (2.0 * pp.image_space_na(system))


def _mtf_values(system, field_fraction, freqs_m, grid, defocus=0.0):
    g = pp.wavefront_grid(system, field_fraction, grid, defocus=defocus)
    m = pp.mtf(g)
    return ([pp.mtf_at(m, f, "tangential") for f in freqs_m],
            [pp.mtf_at(m, f, "sagittal") for f in freqs_m], g)


def mtf_field_map(system: OpticalSystem, frequencies: Optional[list] = None,
                  num_fields: int = 11, num_rays: int = 32) -> dict:
    """
    Diffraction MTF (tangential and sagittal) versus field and frequency.

    Args:
        frequencies: cycles/mm (default 20, 40, 60, 80, 100).
        num_rays: pupil grid size per field.
    """
    freqs_mm = [float(f) for f in (frequencies or [20.0, 40.0, 60.0, 80.0, 100.0])]
    freqs_m = [f * 1e3 for f in freqs_mm]
    fields = np.linspace(0.0, 1.0, num_fields)
    tan, sag, rms = [], [], []
    for ff in fields:
        t, s, g = _mtf_values(system, float(ff), freqs_m, num_rays)
        tan.append(t)
        sag.append(s)
        rms.append(g.rms)
    return {
        "field_fractions": [float(f) for f in fields],
        "frequencies_cyc_per_mm": freqs_mm,
        "mtf": tan,
        "mtf_t": tan,
        "mtf_s": sag,
        "rms_wavefront_waves": [w / system.analysis_settings.wavelength for w in rms],
        "wavelength": system.analysis_settings.wavelength,
        "f_number": _working_f_number(system),
    }


def mtf_focus_map(system: OpticalSystem, frequencies: Optional[list] = None,
                  defocus_range: tuple = (-50e-6, 50e-6), num_points: int = 21,
                  field_fraction: float = 0.0, num_rays: int = 32) -> dict:
    """
    Tangential diffraction MTF versus image-plane position and frequency.
    Best focus is judged at the highest frequency that keeps contrast
    above 0.05 somewhere in the scan.
    """
    freqs_mm = [float(f) for f in (frequencies or [20.0, 40.0, 60.0, 80.0, 100.0])]
    freqs_m = [f * 1e3 for f in freqs_mm]
    positions = np.linspace(defocus_range[0], defocus_range[1], num_points)
    rows = [_mtf_values(system, field_fraction, freqs_m, num_rays, float(d))[0] for d in positions]
    eval_index = 0
    for c in range(len(freqs_mm) - 1, -1, -1):
        if max(r[c] for r in rows) > 0.05:
            eval_index = c
            break
    col = [r[eval_index] for r in rows]
    best = int(np.argmax(col))
    above = [p for p, v in zip(positions, col) if v >= 0.5 * col[best]]
    depth = float(max(above) - min(above)) if len(above) >= 2 else 0.0
    return {
        "defocus_m": [float(p) for p in positions],
        "defocus_um": [float(p) * 1e6 for p in positions],
        "frequencies_cyc_per_mm": freqs_mm,
        "mtf": rows,
        "best_defocus": float(positions[best]),
        "best_defocus_um": float(positions[best]) * 1e6,
        "best_mtf": float(col[best]),
        "depth_of_focus": depth,
        "depth_of_focus_um": depth * 1e6,
        "field_fraction": field_fraction,
        "evaluation_frequency_cyc_per_mm": freqs_mm[eval_index],
        "f_number": _working_f_number(system),
    }


def illumination_summary(system: OpticalSystem, num_fields: int = 11, num_rays: int = 21,
                         focus_points: int = 21, include_mtf: bool = True) -> dict:
    """
    Vignetting, relative illumination and (optionally) MTF maps. The
    "meets_50pct_rule" flag reports whether edge illumination is at least
    50% of the axis value, a common acceptance threshold for camera lenses.
    """
    vin = vignetting_analysis(system, num_fields, num_rays)
    rel = relative_illumination(system, num_fields, max(num_rays, 21))
    edge = rel["edge_relative_illumination"]
    out = {
        "vignetting": vin,
        "relative_illumination": rel,
        "edge_relative_illumination": edge,
        "edge_loss_percent": rel["edge_loss_percent"],
        "meets_50pct_rule": edge >= 0.50,
    }
    if include_mtf:
        out["mtf_field"] = mtf_field_map(system, num_fields=num_fields)
        out["mtf_focus"] = mtf_focus_map(system, num_points=focus_points)
    return out
