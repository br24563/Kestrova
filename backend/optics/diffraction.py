"""
Diffraction analysis (Fraunhofer, diffraction-limited performance).

This module computes diffraction-based performance metrics for an optical
system using the standard formulas for a circular aperture:

    - Airy disk radius
    - Point Spread Function (PSF)  - Fraunhofer diffraction pattern
    - Encircled energy fraction
    - Modulation Transfer Function (MTF)
    - Optical Transfer Function (OTF)
    - Diffraction-limited assessment

All formulas follow the classical Fourier-optics results for a
diffraction-limited circular aperture (Born & Wolf, Hecht "Optics"):

    PSF:      I(r) = | 2 J1(x) / x |^2,   x = (2 pi / lambda) NA r
    Energy:   E(x) = 1 - J0(x)^2 - J1(x)^2
    MTF:      u = f / f_c,  f_c = 1 / (lambda F)
              MTF(u) = 2/pi ( arccos(u) - u sqrt(1 - u^2) ), u in [0,1]
    OTF:      equals the MTF for an aberration-free system (zero phase).
    Airy:     r_airy = 1.22 lambda F  =  0.61 lambda / NA

A system is reported diffraction-limited (educational criterion) when its
RMS spot radius at the image plane is no larger than the Airy disk
first-minimum radius.

All values are in SI base units (meters, radians).
"""

import math
from typing import Optional

import numpy as np
from scipy.special import j1, j0

from .models import OpticalSystem
from .analysis import analyze_system

# Defaults used when a system has no usable aperture / F-number.
_DEFAULT_F_NUMBER = 10.0
_DEFAULT_NA = 0.05

# Wavelength used when the analysis settings do not supply one.
_DEFAULT_WAVELENGTH = 550e-9


def _get_wavelength(wavelength: Optional[float]) -> float:
    """Return the wavelength (meters) to use, defaulting to 550 nm."""
    if wavelength is not None and wavelength > 0:
        return float(wavelength)
    return _DEFAULT_WAVELENGTH


def _valid_f_number(f_number: Optional[float]) -> bool:
    return f_number is not None and math.isfinite(f_number) and f_number > 0


def _valid_na(na: Optional[float]) -> bool:
    return na is not None and math.isfinite(na) and na > 0


def _system_aperture(system: OpticalSystem, wavelength: Optional[float]) -> tuple[float, float, float]:
    """
    Extract (na, f_number, wavelength) from an analyzed system.

    Falls back to sensible defaults when a system yields zero/infinite
    values (e.g. a system with no lenses).
    """
    analysis = analyze_system(system)
    na = analysis.numerical_aperture if _valid_na(analysis.numerical_aperture) else _DEFAULT_NA
    f_number = analysis.f_number if _valid_f_number(analysis.f_number) else _DEFAULT_F_NUMBER
    wl = _get_wavelength(system.analysis_settings.wavelength if not wavelength else wavelength)
    return na, f_number, wl


# ---------------------------------------------------------------------------
# Airy disk
# ---------------------------------------------------------------------------

def airy_disk_radius(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    f_number: Optional[float] = None,
    wavelength: Optional[float] = None,
) -> float:
    """
    Radius of the first dark ring of the Airy disk (meters).

    For a circular aperture the first zero of the diffraction pattern is
    at r = 1.22 * lambda * F  (equivalently 0.61 * lambda / NA). When a
    system is supplied its effective F-number and NA are used; explicit
    values can be supplied instead.

    Args:
        system: Optional optical system.
        na: Optional numerical aperture (dimensionless).
        f_number: Optional F-number (dimensionless).
        wavelength: Optional wavelength (meters).

    Returns:
        Airy disk radius (meters).
    """
    if system is not None:
        na, f_number, wl = _system_aperture(system, wavelength)
    else:
        wl = _get_wavelength(wavelength)

    if _valid_na(na):
        return 0.61 * wl / na
    f = _get_f_or_default(f_number)
    return 1.22 * wl * f


def _get_f_or_default(f_number: Optional[float]) -> float:
    """Return the F-number, falling back to the default."""
    return f_number if _valid_f_number(f_number) else _DEFAULT_F_NUMBER


# ---------------------------------------------------------------------------
# PSF (Fraunhofer diffraction pattern)
# ---------------------------------------------------------------------------

def psf(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    wavelength: Optional[float] = None,
    max_radius: Optional[float] = None,
    num_points: int = 256,
) -> dict:
    """
    Compute the normalized Fraunhofer PSF for a circular aperture.

    The PSF is the normalized intensity  I(r) / I(0):

        I(r) = | 2 J1(x) / x |^2 ,   x = (2 pi / lambda) * NA * r

    This is the ideal (diffraction-limited) PSF; it ignores aberrations.

    Args:
        system: Optional optical system (uses its NA and wavelength).
        na: Optional numerical aperture (dimensionless).
        wavelength: Optional wavelength (meters).
        max_radius: Optional maximum image radius (meters). Defaults to
            4 * Airy disk radius.
        num_points: Number of radial samples.

    Returns:
        Dict with keys "r" (radial coordinates, meters) and "intensity"
        (normalized, peak = 1 at r = 0).
    """
    if system is not None:
        na, _, wl = _system_aperture(system, wavelength)
    else:
        na = _get_na_or_default(na)
        wl = _get_wavelength(wavelength)

    na_val = _get_na_or_default(na)

    if max_radius is None:
        max_radius = 4.0 * airy_disk_radius(na=na_val, wavelength=wl)

    r = np.linspace(0.0, max_radius, num_points)
    x = 2.0 * math.pi / wl * na_val * r

    intensity = np.ones_like(x)
    mask = x > 1e-12
    intensity[mask] = (2.0 * j1(x[mask]) / x[mask]) ** 2

    return {"r": r, "intensity": intensity}


def _get_na_or_default(na: Optional[float]) -> float:
    """Return the NA, falling back to the default."""
    return na if _valid_na(na) else _DEFAULT_NA


# ---------------------------------------------------------------------------
# Encircled energy
# ---------------------------------------------------------------------------

def encircled_energy(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    wavelength: Optional[float] = None,
    radius: Optional[float] = None,
    max_radius: Optional[float] = None,
    num_points: int = 256,
) -> dict:
    """
    Fraction of the image energy enclosed within a radius.

    For a circular pupil:

        E(x) = 1 - J0(x)^2 - J1(x)^2 ,   x = (2 pi / lambda) * NA * r

    Args:
        system: Optional optical system.
        na: Optional numerical aperture.
        wavelength: Optional wavelength (meters).
        radius: Optional single radius (meters). If given, evaluates the
            enclosed fraction at just that radius.
        max_radius: Optional max radius for the curve (meters). Defaults
            to 3 * Airy disk radius.
        num_points: Number of samples for the curve.

    Returns:
        Dict with:
            - "r": radial coordinates (meters)
            - "energy": enclosed-energy fraction (0..1)
    """
    if system is not None:
        na, _, wl = _system_aperture(system, wavelength)
    else:
        na = _get_na_or_default(na)
        wl = _get_wavelength(wavelength)

    na_val = _get_na_or_default(na)

    def fraction(rr: float) -> float:
        x = 2.0 * math.pi / wl * na_val * float(rr)
        if x < 1e-12:
            return 0.0
        return max(0.0, 1.0 - j0(x) ** 2 - j1(x) ** 2)

    if radius is not None:
        return {"radius": float(radius), "energy": [fraction(radius)]}

    if max_radius is None:
        max_radius = 3.0 * airy_disk_radius(na=na_val, wavelength=wl)

    r = np.linspace(0.0, max_radius, num_points)
    energy = np.array([fraction(rr) for rr in r])
    return {"r": r, "energy": energy}


# ---------------------------------------------------------------------------
# MTF / OTF
# ---------------------------------------------------------------------------

def _cutoff_frequency(system: Optional[OpticalSystem], wavelength: Optional[float]) -> float:
    """Spatial-frequency cutoff (cycles per meter in the image plane).

    For an incoherent circular-aperture system:  f_c = 1 / (lambda * F).
    """
    if system is not None:
        _, f_number, wl = _system_aperture(system, wavelength)
        return 1.0 / (wl * f_number)
    wl = _get_wavelength(wavelength)
    return 1.0 / (wl * _DEFAULT_F_NUMBER)


def mtf(
    system: Optional[OpticalSystem] = None,
    frequencies: Optional[np.ndarray] = None,
    num_points: int = 128,
    wavelength: Optional[float] = None,
) -> dict:
    """
    Modulation Transfer Function (MTF) of the system.

    The incoherent MTF of a diffraction-limited circular aperture is:

        u = f / f_c,   f_c = 1 / (lambda * F)

        MTF(u) = 2/pi ( arccos(u) - u * sqrt(1 - u^2) ),  u in [0, 1]

    For u > 1 the MTF is zero (beyond cutoff).

    Args:
        system: Optional optical system (uses its F-number and wavelength).
        frequencies: Optional array of spatial frequencies (cycles/m).
        num_points: Number of samples between 0 and the cutoff.
        wavelength: Optional wavelength (meters).

    Returns:
        Dict with "f" (cycles/m), "mtf" (0..1), and "f_c" (cutoff).
    """
    f_c = _cutoff_frequency(system, wavelength)

    if frequencies is None:
        frequencies = np.linspace(0.0, f_c, num_points)
    else:
        frequencies = np.asarray(frequencies, dtype=float)

    u = frequencies / f_c
    mtf_out = np.zeros_like(u, dtype=float)
    m = u < 1.0
    uu = u[m]
    mtf_out[m] = (2.0 / math.pi) * (
        np.arccos(uu) - uu * np.sqrt(1.0 - uu * uu)
    )
    return {"f": frequencies, "mtf": mtf_out, "f_c": f_c}


def otf(
    system: Optional[OpticalSystem] = None,
    frequencies: Optional[np.ndarray] = None,
    num_points: int = 128,
    wavelength: Optional[float] = None,
) -> dict:
    """
    Optical Transfer Function (OTF) of the system.

    For an aberration-free (diffraction-limited) system the OTF is real
    and equals the MTF (zero phase).

    Returns:
        Dict with "f" (cycles/m), "otf" (complex array), "mtf" (modulus).
    """
    res = mtf(system, frequencies=frequencies, num_points=num_points,
              wavelength=wavelength)
    otf_val = res["mtf"].astype(complex)
    return {"f": res["f"], "otf": otf_val, "mtf": res["mtf"], "f_c": res["f_c"]}


# ---------------------------------------------------------------------------
# Diffraction-limited assessment
# ---------------------------------------------------------------------------

def diffraction_limited_check(system: OpticalSystem) -> dict:
    """
    Assess whether the system is diffraction-limited.

    Educational criterion: the RMS spot radius at the image plane is no
    larger than the Airy disk first-minimum radius.

    Returns:
        Dict with:
            - "airy_disk_radius": Airy first-minimum radius (meters)
            - "rms_spot_radius": measured RMS spot (meters)
            - "is_diffraction_limited": bool
            - "margin": airy_radius / max(rms_spot, small_eps)
    """
    analysis = analyze_system(system)
    rms = analysis.rms_spot_radius
    airy = airy_disk_radius(system)

    margin = airy / rms if rms > 1e-15 else float("inf")

    return {
        "airy_disk_radius": airy,
        "rms_spot_radius": rms,
        "is_diffraction_limited": rms <= airy,
        "margin": margin,
    }


# ---------------------------------------------------------------------------
# Full diffraction analysis
# ---------------------------------------------------------------------------

def diffraction_analysis(
    system: Optional[OpticalSystem] = None,
    na: Optional[float] = None,
    wavelength: Optional[float] = None,
    frequencies: Optional[list] = None,
    num_points: int = 128,
) -> dict:
    """
    Run a complete diffraction analysis on the system.

    Args:
        system: The optical system.
        na: Optional numerical aperture override.
        wavelength: Optional wavelength override (meters).
        frequencies: Optional list of spatial frequencies for MTF.
        num_points: Number of samples for the PSF / energy curves.

    Returns:
        Dict combining the Airy radius, PSF, encircled energy, MTF, OTF,
        and (when a system is supplied) the diffraction-limited check.
    """
    psf_data = psf(system, na=na, wavelength=wavelength, num_points=num_points)
    ee_data = encircled_energy(
        system, na=na, wavelength=wavelength, num_points=num_points
    )
    mtf_data = mtf(system, frequencies=frequencies, num_points=num_points,
                   wavelength=wavelength)
    otf_data = otf(system, frequencies=frequencies, num_points=num_points,
                   wavelength=wavelength)

    result = {
        "psf": psf_data,
        "encircled_energy": ee_data,
        "mtf": mtf_data,
        "otf": otf_data,
        "airy_disk_radius": airy_disk_radius(
            system, na=na, wavelength=wavelength
        ),
    }

    if system is not None:
        result["diffraction_limited"] = diffraction_limited_check(system)

    return result