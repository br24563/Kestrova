"""
Wavefront analysis.

- Wavefront (OPD) map over the full 2D pupil from real rays, measured on
  the exit-pupil reference sphere (:mod:`optics.pupil`).
- Zernike decomposition (Noll standard, least squares).
- Strehl ratio from the pupil function (exact, not the Marechal estimate).
- Interferogram of the wavefront against a flat reference, with optional
  added tilt and defocus.
- Seidel wavefront coefficients from the Seidel sums.

OPD values are in meters; W = OPL(chief) - OPL(ray) on the reference sphere.
"""

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .models import OpticalSystem
from .zernike import zernike_fit, zernike_names, zernike_standard
from . import pupil as pp
from . import raytrace as rt


@dataclass
class WavefrontMap:
    """2D wavefront error map (NaN outside the traced pupil)."""
    pupil_x: list
    pupil_y: list
    opd: list
    opd_rms: float
    opd_pv: float
    strehl: float
    field_fraction: float
    wavelength: float


@dataclass
class ZernikeDecomposition:
    """Zernike (Noll) fit of the wavefront."""
    coefficients: list
    names: list
    rms_wavefront: float
    peak_to_valley: float
    strehl_ratio: float
    wavefront_map: list
    pupil_x: list
    pupil_y: list
    fit_residual_rms: float = 0.0


@dataclass
class InterferogramData:
    """Simulated interferogram (intensity 0..1, NaN-free)."""
    intensity: list
    fringe_count: int
    tilt_x: float
    tilt_y: float
    resolution: int


@dataclass
class SeidelCoefficients:
    """Seidel wavefront coefficients (meters) at the full field and aperture:
    W040, W131, W222, W220 and W311."""
    spherical: float
    coma: float
    astigmatism: float
    field_curvature: float
    distortion: float


@dataclass
class WavefrontAnalysisResult:
    """Complete wavefront analysis results."""
    wavefront_map: Optional[WavefrontMap] = None
    zernike: Optional[ZernikeDecomposition] = None
    interferogram: Optional[InterferogramData] = None
    seidel: Optional[SeidelCoefficients] = None
    strehl: float = 1.0
    rms_wavefront: float = 0.0
    is_diffraction_limited: bool = True


def _grid(system, num_rays, field_fraction):
    return pp.wavefront_grid(system, field_fraction, max(int(num_rays), 5))


def compute_wavefront_map(system: OpticalSystem, num_rays: int = 21,
                          field_fraction: float = 1.0) -> WavefrontMap:
    """OPD map over a num_rays x num_rays pupil grid."""
    g = _grid(system, num_rays, field_fraction)
    W = np.where(g.mask, g.W, np.nan)
    return WavefrontMap(
        pupil_x=g.px[0].tolist(), pupil_y=g.py[:, 0].tolist(),
        opd=[[None if not np.isfinite(v) else float(v) for v in row] for row in W],
        opd_rms=g.rms, opd_pv=g.peak_to_valley, strehl=pp.strehl_ratio(g),
        field_fraction=field_fraction, wavelength=g.wavelength,
    )


def zernike_decompose(system: OpticalSystem, num_rays: int = 31, num_terms: int = 16,
                      field_fraction: float = 1.0) -> ZernikeDecomposition:
    """Least-squares Noll Zernike fit of the 2D wavefront."""
    g = _grid(system, num_rays, field_fraction)
    x, y, w = g.px[g.mask], g.py[g.mask], g.W[g.mask]
    coeffs = zernike_fit(w, x, y, num_terms)
    rho, th = np.hypot(x, y), np.arctan2(y, x)
    model = sum(c * zernike_standard(j + 1, rho, th) for j, c in enumerate(coeffs))
    resid = w - model
    return ZernikeDecomposition(
        coefficients=coeffs.tolist(), names=zernike_names(num_terms),
        rms_wavefront=g.rms, peak_to_valley=g.peak_to_valley,
        strehl_ratio=pp.strehl_ratio(g),
        wavefront_map=w.tolist(), pupil_x=x.tolist(), pupil_y=y.tolist(),
        fit_residual_rms=float(np.sqrt(np.mean(resid ** 2))),
    )


def simulate_interferogram(system: OpticalSystem, num_rays: int = 64,
                           tilt_x: float = 0.0, tilt_y: float = 0.0,
                           defocus: float = 0.0, field_fraction: float = 0.0
                           ) -> InterferogramData:
    """
    Single-pass interferogram against a flat reference wavefront.

    Args:
        tilt_x, tilt_y: Reference tilt in waves across the pupil radius.
        defocus: Added defocus in waves at the pupil edge (rho^2 term).
    """
    g = _grid(system, num_rays, field_fraction)
    lam = g.wavelength
    total = np.where(g.mask, g.W / lam, 0.0) + tilt_x * g.px + tilt_y * g.py \
        + defocus * (g.px ** 2 + g.py ** 2)
    intensity = np.where(g.mask, 0.5 * (1.0 + np.cos(2.0 * math.pi * total)), 0.0)
    vals = total[g.mask]
    fringes = int(math.floor(np.ptp(vals))) if vals.size else 0
    return InterferogramData(intensity=intensity.tolist(), fringe_count=fringes,
                             tilt_x=tilt_x, tilt_y=tilt_y, resolution=g.W.shape[0])


def compute_seidel_from_wavefront(system: OpticalSystem, num_rays: int = 21) -> SeidelCoefficients:
    """Seidel wavefront coefficients W040..W311 from the Seidel sums."""
    s = rt.seidel_sums(system)
    return SeidelCoefficients(
        spherical=s.S1 / 8.0, coma=s.S2 / 2.0, astigmatism=s.S3 / 2.0,
        field_curvature=(s.S3 + s.S4) / 4.0, distortion=s.S5 / 2.0,
    )


def full_wavefront_analysis(system: OpticalSystem, num_rays: int = 21,
                            num_terms: int = 16, field_fraction: float = 1.0
                            ) -> WavefrontAnalysisResult:
    """Wavefront map, Zernike fit, interferogram and Seidel coefficients."""
    wf_map = compute_wavefront_map(system, num_rays, field_fraction)
    zern = zernike_decompose(system, num_rays, num_terms, field_fraction)
    interf = simulate_interferogram(system, min(num_rays * 2, 64), field_fraction=field_fraction)
    try:
        seidel = compute_seidel_from_wavefront(system)
    except ValueError:
        seidel = None
    return WavefrontAnalysisResult(
        wavefront_map=wf_map, zernike=zern, interferogram=interf, seidel=seidel,
        strehl=wf_map.strehl, rms_wavefront=wf_map.opd_rms,
        is_diffraction_limited=wf_map.strehl >= 0.8,
    )
