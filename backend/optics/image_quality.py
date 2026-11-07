"""
Image quality per field: the polychromatic diffraction PSF with encircled
and ensquared energy, and the standard field plots (distortion, F-theta
distortion, lateral colour and relative illumination).

PSF: for each wavelength, the FFT PSF of the real-ray pupil function
(:func:`optics.pupil.psf`) within the field's vignetted pupil, centred on
that wavelength's chief ray. The wavelengths are resampled onto one grid,
shifted by their chief-ray positions relative to the reference wavelength
(lateral colour), each normalised to unit energy and weighted. Energies and
the centroid are measured on each wavelength's native FFT grid (the
resampled image is for display only). The diffraction-limited
encircled energy of a circular pupil is 1 - J0(v)^2 - J1(v)^2,
v = 2 pi NA' r / lambda (Rayleigh), weighted over the wavelengths.

Field plots are measured in the reference wavelength's paraxial image plane
along the field's y direction:

- distortion = (y_real - y_paraxial) / y_paraxial of the reference chief ray;
- F-theta distortion (object at infinity) = (y_real - f theta) / (f theta),
  f the effective focal length, theta the field angle;
- lateral colour = chief-ray height at each wavelength minus the reference.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy.ndimage import map_coordinates
from scipy.special import j0, j1

from . import pupil as pp
from . import raytrace as rt
from .fields import resolve_fields, wavelength_weights
from .illumination import relative_illumination
from .models import ImagePlane, OpticalSystem


def diffraction_limited_ee(radius, na: float, wavelength: float) -> np.ndarray:
    """Encircled energy of an aberration-free circular pupil (Rayleigh)."""
    v = 2.0 * math.pi * na * np.asarray(radius, dtype=float) / wavelength
    return np.clip(1.0 - j0(v) ** 2 - j1(v) ** 2, 0.0, 1.0)


def _chief_image(system, hx, hy, wavelength, seq=None, fo=None):
    """Chief-ray image point (image-plane local x, y) at a wavelength."""
    if seq is None:
        seq = rt.build_sequence(system, wavelength)
    if fo is None:
        fo = rt.first_order(system, seq=seq)
    b, _, _ = rt.trace_field_rays(
        system, hx, hy, np.array([0.0]), np.array([0.0]), seq=seq, fo=fo, clip=False
    )
    if not b.valid[0]:
        raise ValueError("The chief ray cannot be traced for this field")
    local = rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)[0]
    return float(local[0, 0]), float(local[0, 1])


def field_psf(
    system: OpticalSystem,
    index: int = 0,
    grid: int = 64,
    pad: int = 8,
    image_size: int = 65,
    extent_airy: Optional[float] = None,
    energy_points: int = 60,
) -> dict:
    """
    Polychromatic PSF of one field-table entry on an image_size^2 grid about
    the reference chief ray, with encircled and ensquared energy curves.

    The view spans +-extent_airy Airy radii (0.61 lambda_ref / NA'); by
    default it fits the energy: 1.3 x the 95 % encircled-energy radius, at
    least 8 Airy radii, at most the FFT window. ``exceeds_window`` reports
    a PSF wider than the diffraction calculation's window (over 1 % of the
    energy in its outer band, where the periodic FFT wraps around): the
    image is then aberration-limited and the spot diagram describes it.
    """
    tracing, fields = resolve_fields(system)
    if not 0 <= index < len(fields):
        raise ValueError(f"Field {index} does not exist ({len(fields)} fields)")
    f = fields[index]
    weights = wavelength_weights(system)
    lam_ref = system.analysis_settings.wavelength
    na_ref = pp.image_space_na(tracing, lam_ref)
    airy = 0.61 * lam_ref / na_ref
    ref_x, ref_y = _chief_image(tracing, f.hx, f.hy, lam_ref)

    # pass 1: each wavelength's PSF on its native grid, unit energy
    waves = []
    strehls, dl_ee_terms = [], []
    window, edge_energy = np.inf, 0.0
    for wl, w in zip(system.wavelengths, weights):
        g = pp.wavefront_grid(
            tracing, f.hy, grid, wl, field_x=f.hx, vignetting=f.vignetting
        )
        res = pp.psf(g, pad=pad)
        strehls.append({"wavelength": wl, "strehl": float(res.strehl)})
        dl_ee_terms.append((w, g.na_image, wl))
        cx_w, cy_w = _chief_image(tracing, f.hx, f.hy, wl)
        n = res.intensity.shape[0]
        frac = res.intensity / res.intensity.sum()
        k = np.abs(np.arange(n) - n // 2)
        band = np.maximum(k[:, None], k[None, :]) > 0.4 * n
        edge_energy += w * float(frac[band].sum())
        window = min(window, 0.5 * n * res.spacing)
        xs = (np.arange(n) - n // 2) * res.spacing + (cx_w - ref_x)
        ys = (np.arange(n) - n // 2) * res.spacing + (cy_w - ref_y)
        NX, NY = np.meshgrid(xs, ys)
        waves.append(
            (w, res, cx_w - ref_x, cy_w - ref_y, NX.ravel(), NY.ravel(), frac.ravel())
        )

    # centroid and energies on the native grids (energy-conserving)
    cx = sum(w * float((fr * x).sum()) for w, _, _, _, x, _, fr in waves)
    cy = sum(w * float((fr * y).sum()) for w, _, _, _, _, y, fr in waves)

    def energies(radii):
        enc = np.zeros(radii.size)
        sq = np.zeros(radii.size)
        for w, _, _, _, x, y, fr in waves:
            R = np.hypot(x - cx, y - cy)
            S = np.maximum(np.abs(x - cx), np.abs(y - cy))
            o_r, o_s = np.argsort(R), np.argsort(S)
            enc += w * np.interp(radii, R[o_r], np.cumsum(fr[o_r]), left=0.0)
            sq += w * np.interp(radii, S[o_s], np.cumsum(fr[o_s]), left=0.0)
        return enc, sq

    if extent_airy is not None:
        half = extent_airy * airy
    else:
        probe = np.linspace(0.0, window, 400)
        enc_probe, _ = energies(probe)
        r95 = (
            float(np.interp(0.95, enc_probe, probe))
            if enc_probe[-1] >= 0.95
            else window
        )
        half = min(max(8.0 * airy, 1.3 * r95), window)

    # pass 2: the display image (resampled, for viewing only) and curves
    axis = np.linspace(-half, half, int(image_size))
    X, Y = np.meshgrid(axis, axis)
    total = np.zeros(X.shape)
    for w, res, dx, dy, _, _, _ in waves:
        n = res.intensity.shape[0]
        col = (X - dx) / res.spacing + n // 2
        row = (Y - dy) / res.spacing + n // 2
        sampled = map_coordinates(res.intensity, [row, col], order=1, cval=0.0)
        total += w * sampled / (res.intensity.sum() * res.spacing**2)
    r_axis = np.linspace(0.0, half, int(energy_points))
    encircled, ensquared = energies(r_axis)
    limit = sum(w * diffraction_limited_ee(r_axis, na, wl) for w, na, wl in dl_ee_terms)
    peak = total.max()

    def radius_at(fraction: float) -> Optional[float]:
        if encircled[-1] < fraction:
            return None
        return float(np.interp(fraction, encircled, r_axis))

    r80 = radius_at(0.8)
    return {
        "field": index,
        "axis_mm": (axis * 1e3).tolist(),
        "psf": (total / peak if peak > 0 else total).tolist(),  # peak = 1
        "centroid_mm": [cx * 1e3, cy * 1e3],
        "radius_mm": (r_axis * 1e3).tolist(),
        "encircled": encircled.tolist(),
        "ensquared": ensquared.tolist(),
        "diffraction_limited_encircled": np.asarray(limit).tolist(),
        "radius_80_mm": None if r80 is None else r80 * 1e3,
        "airy_radius_mm": airy * 1e3,
        "strehl": strehls,
        "energy_total": float(sum(w * float(fr.sum()) for w, *_, fr in waves)),
        "window_mm": window * 1e3,
        "exceeds_window": bool(edge_energy > 0.01),
    }


def field_plots(system: OpticalSystem, points: int = 11) -> dict:
    """Distortion, F-theta distortion, lateral colour and relative
    illumination from the axis to the full field (y direction)."""
    lam_ref = system.analysis_settings.wavelength
    seq0 = rt.build_sequence(system, lam_ref)
    fo0 = rt.first_order(system, seq=seq0)
    if not math.isfinite(fo0.image_z):
        raise ValueError("Image is at infinity: image-plane field plots are undefined")
    s = system.model_copy(update={"image_plane": ImagePlane(position=fo0.image_z)})
    seq = rt.build_sequence(s, lam_ref)
    fo = rt.first_order(s, seq=seq)
    fracs = np.linspace(0.0, 1.0, int(points))
    infinite = bool(fo.object_infinite)
    tan_max = math.tan(fo.field_angle) if infinite else 0.0
    seqs = {wl: rt.build_sequence(s, wl) for wl in system.wavelengths}
    fos = {wl: rt.first_order(s, seq=q) for wl, q in seqs.items()}
    dist: list[float] = []
    ftheta: list[float] = []
    colour: dict[float, list[float]] = {wl: [] for wl in system.wavelengths}
    for ff in fracs:
        y_ref = _chief_image(s, 0.0, float(ff), lam_ref, seq, fo)[1]
        for wl in system.wavelengths:
            y = _chief_image(s, 0.0, float(ff), wl, seqs[wl], fos[wl])[1]
            colour[wl].append(y - y_ref)
        hp = fo.image_height * ff
        dist.append(float((y_ref - hp) / hp) if ff > 0 and hp else 0.0)
        if infinite:
            theta = math.atan(ff * tan_max)
            # the paraxial image height sign gives the image orientation
            sign = 1.0 if fo.image_height >= 0 else -1.0
            yf = sign * abs(fo.efl) * theta
            ftheta.append(float((y_ref - yf) / yf) if ff > 0 and yf else 0.0)
    ri = relative_illumination(system, int(points))
    return {
        "field_fractions": fracs.tolist(),
        "field_angle_deg": (
            [math.degrees(math.atan(ff * tan_max)) for ff in fracs]
            if infinite
            else None
        ),
        "distortion": dist,
        "ftheta_distortion": ftheta if infinite else None,
        "reference_wavelength": lam_ref,
        "lateral_colour_mm": [
            {"wavelength": wl, "offset_mm": [v * 1e3 for v in vals]}
            for wl, vals in colour.items()
        ],
        "relative_illumination": ri["relative_illumination"],
        "cos4": ri["cos4"],
    }
