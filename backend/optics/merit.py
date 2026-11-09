"""
Merit functions and system properties for optimization (Code V style).

The default merit (``LensData.merit``) is either

- transverse: ray errors at the image (m) over a Gaussian pupil sampling
  (G. W. Forbes, JOSA A 5, 1943 (1988)) at every field and wavelength,
  measured from the chief ray or from each spot's centroid; or
- wavefront: the wavefront error in waves with piston and tilt removed
  over the same sampling,

each residual weighted by sqrt(pupil-area share x field weight x
wavelength weight) with the weights normalised to sum 1, so the sum of
squares is the weighted mean-square spot (m^2) or wavefront (waves^2).
User operands add weight * (value - target) for any property below.

Properties (also usable as exact constraints) are evaluated on the traced
system; field properties take an entry of the field table (default: the
last, usually the full field).
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from . import raytrace as rt
from .fields import ResolvedField, pupil_samples, resolve_fields, wavelength_weights
from .models import ImagePlane, OpticalSystem

#: Residual for a ray that cannot be traced: transverse (in entrance pupil
#: diameters) and wavefront (in waves).
_FAILED_WAVES = 10.0


def _fields(system: OpticalSystem) -> tuple[OpticalSystem, list[ResolvedField]]:
    return resolve_fields(system)


def _field(system: OpticalSystem, index: Optional[int]):
    tracing, fields = _fields(system)
    k = len(fields) - 1 if index is None else index
    if not 0 <= k < len(fields):
        raise ValueError(
            f"Field {k} does not exist (the field table has {len(fields)})"
        )
    return tracing, fields[k]


def _weights(system: OpticalSystem, fields) -> tuple[list[float], list[float]]:
    total = sum(f.weight for f in fields) or 1.0
    return [f.weight / total for f in fields], wavelength_weights(system)


def _chief(tracing: OpticalSystem, f: ResolvedField, wavelength: float, seq=None):
    """Chief-ray image point (local x, y) and direction (local) at a wavelength."""
    seq = seq or rt.build_sequence(tracing, wavelength)
    fo = rt.first_order(tracing, seq=seq)
    b, _, _ = rt.trace_field_rays(
        tracing, f.hx, f.hy, np.zeros(1), np.zeros(1), seq=seq, fo=fo, clip=False
    )
    if not b.valid[0]:
        raise ValueError("The chief ray cannot be traced for this field")
    p, d = rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)
    return p[0], d[0]


# =============================================================================
# Image terms of the merit
# =============================================================================


def transverse_residuals(
    system: OpticalSystem, rings: int = 3, reference: str = "chief", clip: bool = False
) -> np.ndarray:
    """Transverse ray errors (m); the sum of squares is the weighted
    mean-square spot about the chief ray or the centroid."""
    tracing, fields = _fields(system)
    fw, ww = _weights(system, fields)
    res = []
    for wl, w_wl in zip(system.wavelengths, ww):
        seq = rt.build_sequence(tracing, wl)
        fo = rt.first_order(tracing, seq=seq)
        for f, w_f in zip(fields, fw):
            if w_f * w_wl == 0:
                continue
            px, py, pw = pupil_samples(rings, f.vignetting)
            b, _, _ = rt.trace_field_rays(
                tracing, f.hx, f.hy, px, py, seq=seq, fo=fo, clip=clip
            )
            if not b.valid[0] and reference == "chief":
                raise ValueError("The chief ray cannot be traced for this field")
            P = rt._to_local(
                seq.image_origin, seq.image_rotation, b.image, b.directions
            )[0]
            ok = b.valid[1:]
            w = pw[1:]
            if reference == "centroid":
                if not ok.any():
                    raise ValueError("No rays reach the image for this field")
                cx = np.sum(w[ok] * P[1:, 0][ok]) / np.sum(w[ok])
                cy = np.sum(w[ok] * P[1:, 1][ok]) / np.sum(w[ok])
            else:
                cx, cy = P[0, 0], P[0, 1]
            ex, ey = P[1:, 0] - cx, P[1:, 1] - cy
            big = 2.0 * fo.entrance_pupil_semi_diameter
            ex = np.where(ok, ex, big)
            ey = np.where(ok, ey, big)
            s = np.sqrt(w_f * w_wl * w)
            res += [s * ex, s * ey]
    return np.concatenate(res) if res else np.zeros(0)


def _wavefront_errors(tracing, f, wl, seq, fo, rings, clip):
    """Wavefront errors (waves, piston and tilt removed) at one field and
    wavelength, and the square roots of their pupil weights."""
    px, py, pw = pupil_samples(rings, f.vignetting)
    px, py, w = px[1:], py[1:], pw[1:]
    W, ok, _ = rt.opd(tracing, f.hx, f.hy, px, py, wl, seq=seq, fo=fo, clip=clip)
    sw = np.sqrt(w)
    if ok.sum() >= 3:
        A = np.stack([np.ones_like(px), px, py], axis=1)
        coef = np.linalg.lstsq(
            (A * sw[:, None])[ok], (np.nan_to_num(W) * sw)[ok], rcond=None
        )[0]
        e = (np.nan_to_num(W) - A @ coef) / wl
    else:
        e = np.zeros_like(px)
    return np.where(ok, e, _FAILED_WAVES), sw


def wavefront_residuals(
    system: OpticalSystem, rings: int = 3, clip: bool = False
) -> np.ndarray:
    """Wavefront errors (waves) with piston and tilt removed; the sum of
    squares is the weighted mean-square wavefront error."""
    tracing, fields = _fields(system)
    fw, ww = _weights(system, fields)
    res = []
    for wl, w_wl in zip(system.wavelengths, ww):
        seq = rt.build_sequence(tracing, wl)
        fo = rt.first_order(tracing, seq=seq)
        for f, w_f in zip(fields, fw):
            if w_f * w_wl == 0:
                continue
            e, sw = _wavefront_errors(tracing, f, wl, seq, fo, rings, clip)
            res.append(math.sqrt(w_f * w_wl) * sw * e)
    return np.concatenate(res) if res else np.zeros(0)


def image_residuals(system: OpticalSystem, spec) -> np.ndarray:
    """The image term of a merit specification (:class:`MeritSpec`)."""
    if spec.kind == "wavefront":
        r = wavefront_residuals(system, spec.rings)
    else:
        r = transverse_residuals(system, spec.rings, spec.reference)
    return spec.image_weight * r


# =============================================================================
# Properties
# =============================================================================


def distortion(system: OpticalSystem, field: Optional[int] = None) -> float:
    """Real chief-ray image height over the paraxial one, minus 1, at the
    paraxial focus of the reference wavelength."""
    fo0 = rt.first_order(system)
    if not math.isfinite(fo0.image_z):
        raise ValueError("Distortion needs a finite image")
    s = system.model_copy(update={"image_plane": ImagePlane(position=fo0.image_z)})
    tracing, f = _field(s, field)
    fo = rt.first_order(tracing)
    p, _ = _chief(tracing, f, tracing.analysis_settings.wavelength)
    r_par = abs(fo.image_height) * math.hypot(f.hx, f.hy)
    return float(math.hypot(p[0], p[1]) / r_par - 1.0) if r_par else 0.0


def chief_ray_angle(system: OpticalSystem, field: Optional[int] = None) -> float:
    """Angle (rad) of the chief ray to the axis in image space."""
    tracing, f = _field(system, field)
    _, d = _chief(tracing, f, tracing.analysis_settings.wavelength)
    return float(math.atan2(math.hypot(d[0], d[1]), abs(d[2])))


def image_height(system: OpticalSystem, field: Optional[int] = None) -> float:
    """Radial height (m) of the real chief ray on the image plane."""
    tracing, f = _field(system, field)
    p, _ = _chief(tracing, f, tracing.analysis_settings.wavelength)
    return float(math.hypot(p[0], p[1]))


def lateral_color(system: OpticalSystem, field: Optional[int] = None) -> float:
    """Chief-ray height at the longest minus the shortest wavelength (m)."""
    tracing, f = _field(system, field)
    lo, hi = min(system.wavelengths), max(system.wavelengths)
    p_hi, _ = _chief(tracing, f, hi)
    p_lo, _ = _chief(tracing, f, lo)
    return float(math.hypot(p_hi[0], p_hi[1]) - math.hypot(p_lo[0], p_lo[1]))


def axial_color(system: OpticalSystem) -> float:
    """Paraxial focus at the longest minus the shortest wavelength (m)."""
    lo, hi = min(system.wavelengths), max(system.wavelengths)
    return float(
        rt.first_order(system, hi).image_z - rt.first_order(system, lo).image_z
    )


def spot_rms(
    system: OpticalSystem, field: Optional[int] = None, rings: int = 6
) -> float:
    """RMS spot radius (m) about the centroid of all wavelengths at one field."""
    tracing, f = _field(system, field)
    ww = wavelength_weights(system)
    pts, wts = [], []
    for wl, w_wl in zip(system.wavelengths, ww):
        seq = rt.build_sequence(tracing, wl)
        fo = rt.first_order(tracing, seq=seq)
        px, py, pw = pupil_samples(rings, f.vignetting)
        b, _, _ = rt.trace_field_rays(
            tracing, f.hx, f.hy, px[1:], py[1:], seq=seq, fo=fo
        )
        P = rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)[0]
        ok = b.valid
        pts.append(P[ok, :2])
        wts.append(w_wl * pw[1:][ok])
    P = np.concatenate(pts)
    w = np.concatenate(wts)
    if w.sum() <= 0:
        raise ValueError("No rays reach the image for this field")
    c = np.sum(w[:, None] * P, axis=0) / w.sum()
    return float(math.sqrt(np.sum(w * np.sum((P - c) ** 2, axis=1)) / w.sum()))


def wavefront_rms(
    system: OpticalSystem, field: Optional[int] = None, rings: int = 6
) -> float:
    """RMS wavefront error (waves, piston and tilt removed) at one field,
    the wavelengths weighted."""
    tracing, f = _field(system, field)
    ms = 0.0
    for wl, w_wl in zip(system.wavelengths, wavelength_weights(system)):
        seq = rt.build_sequence(tracing, wl)
        fo = rt.first_order(tracing, seq=seq)
        e, sw = _wavefront_errors(tracing, f, wl, seq, fo, rings, True)
        ms += w_wl * float(np.sum((sw * e) ** 2))
    return math.sqrt(ms)


def seidel(system: OpticalSystem, n: int) -> float:
    """Seidel sum S_n (m), n = 1 .. 5."""
    ss = rt.seidel_sums(system)
    return float(getattr(ss, f"S{n}"))


def property_value(
    kind: str, system: OpticalSystem, field: Optional[int] = None
) -> float:
    """Value of a system property that needs only the traced system."""
    if kind == "distortion":
        return distortion(system, field)
    if kind == "chief_ray_angle":
        return chief_ray_angle(system, field)
    if kind == "image_height":
        return image_height(system, field)
    if kind == "lateral_color":
        return lateral_color(system, field)
    if kind == "axial_color":
        return axial_color(system)
    if kind == "spot_rms":
        return spot_rms(system, field)
    if kind == "wavefront_rms":
        return wavefront_rms(system, field)
    if kind.startswith("seidel_S"):
        return seidel(system, int(kind[-1]))
    raise ValueError(f"Unknown property '{kind}'")
