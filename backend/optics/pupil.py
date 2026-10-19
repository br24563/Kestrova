"""
Pupil-function diffraction: wavefront maps, PSF, MTF and Strehl ratio.

The wavefront W(px, py) is the real-ray optical path difference on the
exit-pupil reference sphere (:func:`optics.raytrace.opd`). The pupil
function is P = A exp(2 pi i W / lambda) with A = 1 inside the traced
(unvignetted) pupil and 0 elsewhere. Then:

    PSF(x)  = |FFT{P}|^2              (Fraunhofer, scalar diffraction)
    OTF(nu) = autocorrelation of P, normalised to 1 at nu = 0
    Strehl  = PSF peak / peak of the aberration-free PSF of the same pupil
            = |sum P|^2 / |sum A|^2

Sampling: the normalised pupil (-1..1) is mapped onto image-space direction
cosines (-NA'..NA'), with NA' the real marginal-ray numerical aperture. This
linear mapping is exact for an aplanatic pupil and is the standard
assumption of FFT diffraction codes. Image-plane spacing is
lambda / (N * d_alpha) for an N-point FFT with pupil spacing d_alpha.

All lengths are in meters, frequencies in cycles per meter.
"""

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .models import OpticalSystem, ImagePlane
from . import raytrace as rt


@dataclass
class WavefrontGrid:
    px: np.ndarray  # (n, n) normalised pupil x
    py: np.ndarray  # (n, n) normalised pupil y
    W: np.ndarray  # (n, n) OPD in meters, NaN outside / vignetted
    mask: np.ndarray  # (n, n) bool, rays that reached the image
    wavelength: float
    na_image: float  # real image-space NA (n' sin U')
    field_fraction: float
    first_order: rt.FirstOrder

    @property
    def values(self) -> np.ndarray:
        return self.W[self.mask]

    @property
    def rms(self) -> float:
        v = self.values
        if v.size == 0:
            return 0.0
        return float(np.sqrt(np.mean((v - v.mean()) ** 2)))

    @property
    def peak_to_valley(self) -> float:
        v = self.values
        return float(np.ptp(v)) if v.size else 0.0


def image_space_na(
    system: OpticalSystem, wavelength: Optional[float] = None, seq=None, fo=None
) -> float:
    """n' sin U' of the real on-axis marginal ray."""
    if seq is None:
        seq = rt.build_sequence(system, wavelength)
    if fo is None:
        fo = rt.first_order(system, seq=seq)
    b, _, _ = rt.trace_field_rays(
        system, 0.0, 0.0, np.array([0.0]), np.array([1.0]), seq=seq, fo=fo, clip=False
    )
    if not b.valid[0]:
        raise ValueError("The marginal ray cannot be traced")
    axis = seq.image_rotation[:, 2]
    cos_u = abs(float(np.dot(b.directions[0], axis)))
    return seq.n_image * math.sqrt(max(0.0, 1.0 - cos_u * cos_u))


def vignetted_pupil(vignetting: Optional[tuple]) -> tuple:
    """(cx, cy, ax, ay): centre and semi-axes of the vignetted pupil ellipse
    for Code V factors (vux, vlx, vuy, vly), in normalised stop units."""
    if not vignetting:
        return 0.0, 0.0, 1.0, 1.0
    vux, vlx, vuy, vly = vignetting
    return (vlx - vux) / 2, (vly - vuy) / 2, (2 - vux - vlx) / 2, (2 - vuy - vly) / 2


def wavefront_grid(
    system: OpticalSystem,
    field_fraction: float = 0.0,
    n: int = 64,
    wavelength: Optional[float] = None,
    defocus: float = 0.0,
    field_x: float = 0.0,
    vignetting: Optional[tuple] = None,
) -> WavefrontGrid:
    """
    OPD on an n x n pupil grid for the field point (``field_x``,
    ``field_fraction``), fractions of the object height. ``defocus`` moves
    the image plane along the axis (meters, in the direction of travel)
    before measuring. ``vignetting`` = (vux, vlx, vuy, vly) limits the pupil
    to Code V's vignetted ellipse; the grid stays in stop coordinates so the
    PSF and MTF scale is unchanged.
    """
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength
    if defocus:
        seq0 = rt.build_sequence(system, wavelength)
        system = system.model_copy(
            update={
                "image_plane": ImagePlane(
                    position=system.image_plane.position
                    + defocus * seq0.image_direction
                )
            }
        )
    seq = rt.build_sequence(system, wavelength)
    fo = rt.first_order(system, seq=seq)
    g = np.linspace(-1.0, 1.0, n)
    PX, PY = np.meshgrid(g, g)
    cx, cy, ax, ay = vignetted_pupil(vignetting)
    inside = ((PX - cx) / ax) ** 2 + ((PY - cy) / ay) ** 2 <= 1.0 + 1e-12
    W = np.full((n, n), np.nan)
    w, ok, _ = rt.opd(
        system, field_x, field_fraction, PX[inside], PY[inside], seq=seq, fo=fo
    )
    vals = np.where(ok, w, np.nan)
    W[inside] = vals
    mask = np.isfinite(W)
    na = image_space_na(system, seq=seq, fo=fo)
    return WavefrontGrid(PX, PY, W, mask, wavelength, na, field_fraction, fo)


def strehl_ratio(grid: WavefrontGrid) -> float:
    """Exact Strehl ratio |sum P|^2 / (sum A)^2 of the sampled pupil."""
    if not grid.mask.any():
        return 0.0
    phase = 2.0 * math.pi * grid.W[grid.mask] / grid.wavelength
    return float(abs(np.sum(np.exp(1j * phase))) ** 2 / grid.mask.sum() ** 2)


def _pupil_field(grid: WavefrontGrid, pad: int):
    n = grid.W.shape[0]
    N = pad * n
    P = np.zeros((N, N), dtype=complex)
    phase = np.where(
        grid.mask, 2.0 * math.pi * np.nan_to_num(grid.W) / grid.wavelength, 0.0
    )
    P[:n, :n] = grid.mask * np.exp(1j * phase)
    if not grid.na_image > 0:
        raise ValueError(
            "Image space is afocal (no image-space NA): the PSF and MTF "
            "in image-plane units are undefined"
        )
    d_alpha = 2.0 * grid.na_image / (n - 1)
    return P, N, d_alpha


@dataclass
class PSFResult:
    x: np.ndarray  # image-plane coordinates (meters), centred
    intensity: np.ndarray  # (N, N), normalised so the unaberrated peak = 1
    strehl: float
    spacing: float


def psf(grid: WavefrontGrid, pad: int = 4) -> PSFResult:
    """FFT point spread function of a wavefront grid."""
    P, N, d_alpha = _pupil_field(grid, pad)
    F = np.fft.fftshift(np.fft.fft2(P))
    I = np.abs(F) ** 2
    ideal_peak = float(grid.mask.sum()) ** 2
    I = I / ideal_peak if ideal_peak > 0 else I
    dx = grid.wavelength / (N * d_alpha)
    x = (np.arange(N) - N // 2) * dx
    return PSFResult(x, I, strehl_ratio(grid), dx)


@dataclass
class MTFResult:
    frequency: np.ndarray  # cycles/m
    tangential: np.ndarray  # MTF along y (meridional)
    sagittal: np.ndarray  # MTF along x
    cutoff: float  # 2 NA' / lambda
    otf_tangential: np.ndarray  # complex
    otf_sagittal: np.ndarray


def _otf_along(otf: np.ndarray, k: np.ndarray, angle: float) -> np.ndarray:
    """OTF at shifts k samples along direction ``angle`` (from +y toward +x),
    by bilinear interpolation of the periodic OTF array."""
    N = otf.shape[0]
    fy, fx = k * math.cos(angle), k * math.sin(angle)
    y0, x0 = np.floor(fy).astype(int), np.floor(fx).astype(int)
    ty, tx = fy - y0, fx - x0

    def at(iy, ix):
        return otf[iy % N, ix % N]

    return (
        (1 - ty) * (1 - tx) * at(y0, x0)
        + ty * (1 - tx) * at(y0 + 1, x0)
        + (1 - ty) * tx * at(y0, x0 + 1)
        + ty * tx * at(y0 + 1, x0 + 1)
    )


def mtf(grid: WavefrontGrid, pad: int = 2, azimuth: float = 0.0) -> MTFResult:
    """
    OTF as the normalised autocorrelation of the pupil function, sliced along
    the tangential and sagittal frequency directions up to the cutoff. The
    tangential direction is +y rotated by ``azimuth`` toward +x (the image
    direction of the field point for a field off the y axis); azimuth 0
    gives the y (tangential) and x (sagittal) axes exactly.
    """
    P, N, d_alpha = _pupil_field(grid, pad)
    F = np.fft.fft2(P)
    otf = np.fft.ifft2(np.abs(F) ** 2)
    otf = otf / otf[0, 0]
    n = grid.W.shape[0]
    # shift by k pupil samples = frequency k * d_alpha / lambda
    k = np.arange(n)
    freq = k * d_alpha / grid.wavelength
    cutoff = 2.0 * grid.na_image / grid.wavelength
    if azimuth == 0.0:
        tan = otf[k, 0]
        sag = otf[0, k]
    else:
        kf = k.astype(float)
        tan = _otf_along(otf, kf, azimuth)
        sag = _otf_along(otf, kf, azimuth + math.pi / 2)
    return MTFResult(freq, np.abs(tan), np.abs(sag), cutoff, tan, sag)


def mtf_at(result: MTFResult, frequency: float, direction: str = "tangential") -> float:
    """MTF at a frequency (cycles/m) by linear interpolation."""
    curve = result.tangential if direction == "tangential" else result.sagittal
    if frequency >= result.cutoff:
        return 0.0
    return float(np.interp(frequency, result.frequency, curve))


def polychromatic_mtf(
    system: OpticalSystem,
    field_fraction: float = 0.0,
    wavelengths: Optional[list] = None,
    weights: Optional[list] = None,
    n: int = 64,
    frequencies: Optional[np.ndarray] = None,
    field_x: float = 0.0,
    vignetting: Optional[tuple] = None,
    azimuth: float = 0.0,
) -> dict:
    """
    Polychromatic MTF: weighted sum of the complex OTFs of each wavelength
    (each normalised to 1 at zero frequency), interpolated onto common
    frequencies. Weights default to the system's wavelength weights.
    """
    if wavelengths is None:
        wavelengths = list(system.wavelengths)
        if weights is None and system.wavelength_weights is not None:
            weights = list(system.wavelength_weights)
    if weights is None:
        weights = [1.0] * len(wavelengths)
    wsum = float(sum(weights))
    results = [
        mtf(
            wavefront_grid(
                system, field_fraction, n, wl, field_x=field_x, vignetting=vignetting
            ),
            azimuth=azimuth,
        )
        for wl in wavelengths
    ]
    fmax = max(r.cutoff for r in results)
    if frequencies is None:
        frequencies = np.linspace(0.0, fmax, 101)
    tan = np.zeros(len(frequencies), dtype=complex)
    sag = np.zeros(len(frequencies), dtype=complex)
    for r, w in zip(results, weights):
        for acc, otf in ((tan, r.otf_tangential), (sag, r.otf_sagittal)):
            re = np.interp(frequencies, r.frequency, otf.real, right=0.0)
            im = np.interp(frequencies, r.frequency, otf.imag, right=0.0)
            acc += w / wsum * (re + 1j * im)
    return {
        "frequency": np.asarray(frequencies),
        "tangential": np.abs(tan),
        "sagittal": np.abs(sag),
        "cutoff": fmax,
    }
