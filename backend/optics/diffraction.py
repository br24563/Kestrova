"""
Diffraction analysis: Airy pattern, PSF, encircled energy, MTF/OTF.

Two kinds of result are provided:

- **Diffraction limit** of a circular pupil of image-space numerical
  aperture NA (Born & Wolf, *Principles of Optics*, sec. 8.5; Goodman,
  *Introduction to Fourier Optics*, sec. 6.3):

      PSF:  I(r) = [2 J1(x)/x]^2,      x = 2 pi NA r / lambda
      EE:   E(r) = 1 - J0(x)^2 - J1(x)^2
      MTF:  (2/pi)(acos u - u sqrt(1 - u^2)),  u = nu / nu_c,  nu_c = 2 NA / lambda
      Airy radius (first zero) = 0.61 lambda / NA = 1.22 lambda N_w

  with N_w = 1/(2 NA) the working F-number.

- **The system's actual PSF and MTF**, computed from the real-ray wavefront
  by FFT (:mod:`optics.pupil`), including aberrations and vignetting.

A system is reported diffraction-limited when its Strehl ratio is at
least 0.8 (the Marechal criterion, RMS wavefront error <= lambda/14).

All lengths are in meters; frequencies in cycles per meter.
"""

import math
from typing import Optional

import numpy as np
from scipy.special import j0, j1

from .models import OpticalSystem
from . import pupil as pp

MARECHAL_STREHL = 0.8


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def _wavelength(system: Optional[OpticalSystem], wavelength: Optional[float]) -> float:
    if wavelength is not None and wavelength > 0:
        return float(wavelength)
    if system is not None:
        return system.analysis_settings.wavelength
    raise ValueError("A wavelength is required")


def _na(
    system: Optional[OpticalSystem],
    na: Optional[float],
    f_number: Optional[float],
    wavelength: float,
) -> float:
    """Image-space NA from an explicit value, a working F-number, or the system."""
    if na is not None:
        if not (math.isfinite(na) and na > 0):
            raise ValueError("NA must be positive")
        return float(na)
    if f_number is not None:
        if not (math.isfinite(f_number) and f_number > 0):
            raise ValueError("F-number must be positive")
        return 1.0 / (2.0 * f_number)
    if system is None:
        raise ValueError("Give a system, an NA or a working F-number")
    value = pp.image_space_na(system, wavelength)
    if not value > 0:
        raise ValueError("The system has no finite image-space aperture")
    return value


# ---------------------------------------------------------------------------
# Diffraction-limit formulas
# ---------------------------------------------------------------------------


def airy_disk_radius(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    f_number: Optional[float] = None,
    wavelength: Optional[float] = None,
) -> float:
    """Radius of the first dark ring, 0.61 lambda / NA (meters)."""
    wl = _wavelength(system, wavelength)
    return 0.61 * wl / _na(system, na, f_number, wl)


def psf(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    wavelength: Optional[float] = None,
    max_radius: Optional[float] = None,
    num_points: int = 256,
    f_number: Optional[float] = None,
) -> dict:
    """Diffraction-limited (Airy) PSF, normalised to 1 at r = 0."""
    wl = _wavelength(system, wavelength)
    a = _na(system, na, f_number, wl)
    if max_radius is None:
        max_radius = 4.0 * 0.61 * wl / a
    r = np.linspace(0.0, max_radius, num_points)
    x = 2.0 * math.pi * a * r / wl
    intensity = np.ones_like(x)
    m = x > 1e-12
    intensity[m] = (2.0 * j1(x[m]) / x[m]) ** 2
    return {"r": r, "intensity": intensity}


def encircled_energy(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    wavelength: Optional[float] = None,
    radius: Optional[float] = None,
    max_radius: Optional[float] = None,
    num_points: int = 256,
    f_number: Optional[float] = None,
) -> dict:
    """Diffraction-limited encircled energy, 1 - J0(x)^2 - J1(x)^2."""
    wl = _wavelength(system, wavelength)
    a = _na(system, na, f_number, wl)

    def frac(rr):
        x = 2.0 * math.pi * a * np.asarray(rr, dtype=float) / wl
        return np.clip(1.0 - j0(x) ** 2 - j1(x) ** 2, 0.0, 1.0)

    if radius is not None:
        return {"radius": float(radius), "energy": [float(frac(radius))]}
    if max_radius is None:
        max_radius = 3.0 * 0.61 * wl / a
    r = np.linspace(0.0, max_radius, num_points)
    return {"r": r, "energy": frac(r)}


def mtf(
    system: Optional[OpticalSystem] = None,
    frequencies: Optional[np.ndarray] = None,
    num_points: int = 128,
    wavelength: Optional[float] = None,
    na: Optional[float] = None,
    f_number: Optional[float] = None,
) -> dict:
    """Diffraction-limited MTF of a circular pupil (cycles/m)."""
    wl = _wavelength(system, wavelength)
    a = _na(system, na, f_number, wl)
    f_c = 2.0 * a / wl
    f = (
        np.linspace(0.0, f_c, num_points)
        if frequencies is None
        else np.asarray(frequencies, float)
    )
    u = f / f_c
    out = np.zeros_like(u)
    m = u < 1.0
    out[m] = (2.0 / math.pi) * (np.arccos(u[m]) - u[m] * np.sqrt(1.0 - u[m] ** 2))
    return {"f": f, "frequency": f, "mtf": out, "f_c": f_c}


def otf(
    system: Optional[OpticalSystem] = None,
    frequencies: Optional[np.ndarray] = None,
    num_points: int = 128,
    wavelength: Optional[float] = None,
    na: Optional[float] = None,
    f_number: Optional[float] = None,
) -> dict:
    """Diffraction-limited OTF (real and equal to the MTF: zero phase)."""
    res = mtf(system, frequencies, num_points, wavelength, na, f_number)
    return {
        "f": res["f"],
        "otf": res["mtf"].astype(complex),
        "mtf": res["mtf"],
        "f_c": res["f_c"],
    }


# ---------------------------------------------------------------------------
# The system's actual (aberrated) diffraction performance
# ---------------------------------------------------------------------------


def _radial_profile(psf2d: np.ndarray, x: np.ndarray, num_points: int):
    X, Y = np.meshgrid(x, x)
    w = psf2d / psf2d.sum()
    cx, cy = float((X * w).sum()), float((Y * w).sum())
    R = np.hypot(X - cx, Y - cy)
    rmax = 0.5 * (x[-1] - x[0]) * 0.9
    edges = np.linspace(0.0, rmax, num_points + 1)
    idx = np.digitize(R.ravel(), edges) - 1
    sel = (idx >= 0) & (idx < num_points)
    sums = np.bincount(idx[sel], weights=psf2d.ravel()[sel], minlength=num_points)
    counts = np.bincount(idx[sel], minlength=num_points)
    prof = np.where(counts > 0, sums / np.maximum(counts, 1), 0.0)
    rc = 0.5 * (edges[:-1] + edges[1:])
    enc = np.cumsum(np.bincount(idx[sel], weights=w.ravel()[sel], minlength=num_points))
    return rc, prof, enc


def system_diffraction(
    system: OpticalSystem,
    field_fraction: float = 0.0,
    grid: int = 64,
    wavelength: Optional[float] = None,
    num_points: int = 128,
) -> dict:
    """
    Actual PSF, encircled energy and MTF of the system from its real-ray
    wavefront at one field point.
    """
    g = pp.wavefront_grid(system, field_fraction, grid, wavelength)
    pres = pp.psf(g, pad=4)
    r, prof, enc = _radial_profile(pres.intensity, pres.x, num_points)
    mres = pp.mtf(g)
    keep = mres.frequency <= mres.cutoff
    return {
        "field_fraction": field_fraction,
        "wavelength": g.wavelength,
        "na_image": g.na_image,
        "strehl_ratio": pres.strehl,
        "rms_wavefront": g.rms,
        "peak_to_valley_wavefront": g.peak_to_valley,
        "psf": {"r": r, "intensity": prof},
        "encircled_energy": {"r": r, "energy": enc},
        "mtf": {
            "frequency": mres.frequency[keep],
            "tangential": mres.tangential[keep],
            "sagittal": mres.sagittal[keep],
            "cutoff": mres.cutoff,
        },
    }


def diffraction_limited_check(
    system: OpticalSystem, field_fraction: float = 0.0
) -> dict:
    """
    Marechal test: diffraction-limited when Strehl >= 0.8.

    Also reports the geometric RMS spot radius against the Airy radius for
    reference (margin = Airy radius / RMS spot).
    """
    from .analysis import real_spot

    g = pp.wavefront_grid(system, field_fraction, 64)
    strehl = pp.strehl_ratio(g)
    airy = 0.61 * g.wavelength / g.na_image
    _, rms_spot, _, _, _ = real_spot(system, field_fraction)
    return {
        "airy_disk_radius": airy,
        "rms_spot_radius": rms_spot,
        "strehl_ratio": strehl,
        "rms_wavefront": g.rms,
        "rms_wavefront_waves": g.rms / g.wavelength,
        "criterion": "Strehl >= 0.8 (Marechal)",
        "is_diffraction_limited": strehl >= MARECHAL_STREHL,
        "margin": airy / rms_spot if rms_spot > 1e-15 else float("inf"),
    }


def diffraction_analysis(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    wavelength: Optional[float] = None,
    frequencies: Optional[list] = None,
    num_points: int = 128,
    field_fraction: float = 0.0,
) -> dict:
    """
    Diffraction analysis. With a system, the PSF, encircled energy and MTF
    are the system's actual (aberrated) ones at ``field_fraction``, each
    alongside the diffraction limit for the same NA. Without a system, only
    the diffraction-limit curves for the given NA are returned.
    """
    if system is None:
        wl = _wavelength(None, wavelength)
        freqs = (
            np.asarray(frequencies, dtype=float) if frequencies is not None else None
        )
        m = mtf(None, freqs, num_points, wl, na)
        return {
            "psf": psf(None, na, wl, num_points=num_points),
            "encircled_energy": encircled_energy(None, na, wl, num_points=num_points),
            "mtf": {"frequency": m["f"], "mtf": m["mtf"], "cutoff": m["f_c"]},
            "otf": otf(None, freqs, num_points, wl, na),
            "airy_disk_radius": airy_disk_radius(None, na, wavelength=wl),
        }
    wl = _wavelength(system, wavelength)
    actual = system_diffraction(
        system, field_fraction, wavelength=wl, num_points=num_points
    )
    a = actual["na_image"] if na is None else na
    ideal_mtf = mtf(None, actual["mtf"]["frequency"], wavelength=wl, na=a)
    return {
        "psf": actual["psf"],
        "encircled_energy": actual["encircled_energy"],
        "mtf": {
            "frequency": actual["mtf"]["frequency"],
            "mtf": actual["mtf"]["tangential"],
            "tangential": actual["mtf"]["tangential"],
            "sagittal": actual["mtf"]["sagittal"],
            "diffraction_limit": ideal_mtf["mtf"],
            "cutoff": actual["mtf"]["cutoff"],
        },
        "diffraction_limit": {
            "psf": psf(None, a, wl, num_points=num_points),
            "encircled_energy": encircled_energy(None, a, wl, num_points=num_points),
        },
        "airy_disk_radius": 0.61 * wl / a,
        "strehl_ratio": actual["strehl_ratio"],
        "rms_wavefront": actual["rms_wavefront"],
        "na_image": a,
        "working_f_number": 1.0 / (2.0 * a),
        "diffraction_limited": diffraction_limited_check(system, field_fraction),
    }
