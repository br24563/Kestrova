"""Source models and partially coherent imaging.

- Laser diode: elliptical, astigmatic beam described per axis by its waist
  and far-field half-angle (1/e^2); the beam quality of each axis follows as
  M^2 = pi w0 theta / lambda (embedded-Gaussian model).
- LED: Lambertian emitter with a Gaussian spectrum.
- Superluminescent diode: broadband, spatially coherent source.
- Imaging: incoherent OTF and PSF of an aberrated circular pupil by FFT,
  and partially coherent imaging by Abbe's method (sum over the source
  points of a circular condenser of coherence factor sigma).
"""

import math
from dataclasses import dataclass

import numpy as np

from .gaussian import GaussianBeam
from .coherence import TemporalCoherence, SpatialCoherence


@dataclass
class LaserDiode:
    """Laser diode with independent fast (parallel) and slow (perpendicular) axes."""

    wavelength: float = 635e-9
    power: float = 10e-3
    beam_waist_parallel: float = 1.0e-6  # fast-axis 1/e^2 waist radius
    beam_waist_perpendicular: float = 3.0e-6  # slow-axis waist radius
    divergence_parallel: float = 0.35  # fast-axis 1/e^2 half-angle (rad)
    divergence_perpendicular: float = 0.08  # slow-axis half-angle (rad)
    astigmatism: float = 0.0  # slow-axis waist behind the fast-axis waist (m)
    name: str = "LaserDiode"

    def m2(self, axis: str) -> float:
        w, th = (
            (self.beam_waist_parallel, self.divergence_parallel)
            if axis == "parallel"
            else (self.beam_waist_perpendicular, self.divergence_perpendicular)
        )
        m2 = math.pi * w * math.tan(th) / self.wavelength
        if m2 < 1.0 - 1e-9:
            raise ValueError(
                f"{axis}-axis waist and divergence violate the diffraction limit (M^2 < 1)"
            )
        return max(1.0, m2)

    def beam_parallel(self) -> GaussianBeam:
        return GaussianBeam(
            w0=self.beam_waist_parallel,
            wavelength=self.wavelength,
            M2=self.m2("parallel"),
            power=self.power,
        )

    def beam_perpendicular(self) -> GaussianBeam:
        return GaussianBeam(
            w0=self.beam_waist_perpendicular,
            wavelength=self.wavelength,
            M2=self.m2("perpendicular"),
            position=-self.astigmatism,
            power=self.power,
        )

    def intensity_profile(self, x, y, z=0.0) -> np.ndarray:
        """Intensity (W/m^2) on a grid at axial position z."""
        wx = self.beam_parallel().beam_radius(z)
        wy = self.beam_perpendicular().beam_radius(z)
        X, Y = np.meshgrid(x, y)
        return (2 * self.power / (math.pi * wx * wy)) * np.exp(
            -2 * (X**2 / wx**2 + Y**2 / wy**2)
        )


@dataclass
class LEDSource:
    """Lambertian LED with a Gaussian emission spectrum."""

    wavelength: float = 550e-9
    bandwidth: float = 30e-9  # FWHM
    power: float = 1e-3
    emitting_area_radius: float = 50e-6
    divergence_angle: float = 60.0  # full cone angle collected (degrees)
    name: str = "LED"

    def etendue(self) -> float:
        """Etendue pi A sin^2(theta) of a Lambertian emitter into half-angle theta."""
        theta = math.radians(self.divergence_angle / 2)
        return math.pi * self.emitting_area_radius**2 * math.pi * math.sin(theta) ** 2

    def spectral_density(self, wavelengths: np.ndarray) -> np.ndarray:
        """Spectral power density (W/m), Gaussian of FWHM ``bandwidth``."""
        sigma = self.bandwidth / (2 * math.sqrt(2 * math.log(2)))
        return (
            self.power
            * np.exp(-0.5 * ((wavelengths - self.wavelength) / sigma) ** 2)
            / (sigma * math.sqrt(2 * math.pi))
        )


@dataclass
class SLSource:
    """Superluminescent diode: broadband, single transverse mode."""

    wavelength: float = 840e-9
    bandwidth: float = 50e-9
    power: float = 5e-3
    beam_waist: float = 2.0e-6
    name: str = "SLD"

    def temporal_coherence(self) -> TemporalCoherence:
        return TemporalCoherence(wavelength=self.wavelength, bandwidth=self.bandwidth)

    def spatial_coherence(self, distance: float = 1.0) -> SpatialCoherence:
        """Treats the emitting aperture (diameter 2 w0) as the source."""
        return SpatialCoherence(
            wavelength=self.wavelength,
            source_size=2 * self.beam_waist,
            distance=distance,
        )


# =============================================================================
# Pupil-based imaging
# =============================================================================


def compute_transfer_function(
    wavelength, pupil_radius=1.0, defocus=0.0, spherical=0.0, astigmatism=0.0, n=128
):
    """
    Coherent transfer function (pupil function) on a Cartesian grid over the
    normalised pupil. Aberrations are wavefront coefficients in meters:
    W = defocus rho^2 + spherical rho^4 + astigmatism rho^2 cos^2(theta).
    Returns (pupil, X, Y).
    """
    g = np.linspace(-1, 1, n)
    X, Y = np.meshgrid(g, g)
    R2 = X**2 + Y**2
    W = defocus * R2 + spherical * R2**2 + astigmatism * Y**2
    pupil = np.where(R2 <= 1.0, np.exp(2j * np.pi * W / wavelength), 0.0)
    return pupil, X, Y


def compute_mtf(wavelength, NA, spatial_freqs, defocus=0.0, n=128):
    """
    Incoherent MTF (tangential) of a circular pupil of image-space NA with an
    optional defocus wavefront coefficient W020 (meters), by pupil
    autocorrelation. Frequencies in cycles/m.
    """
    pupil, _, _ = compute_transfer_function(wavelength, 1.0, defocus=defocus, n=n)
    P = np.zeros((2 * n, 2 * n), dtype=complex)
    P[:n, :n] = pupil
    otf = np.fft.ifft2(np.abs(np.fft.fft2(P)) ** 2)
    otf = otf / otf[0, 0]
    d_alpha = 2 * NA / (n - 1)
    freq = np.arange(n) * d_alpha / wavelength
    curve = np.abs(otf[np.arange(n), 0])
    f = np.asarray(spatial_freqs, dtype=float)
    return np.where(f < 2 * NA / wavelength, np.interp(f, freq, curve), 0.0)


def compute_otf(wavelength, NA, spatial_freq, defocus=0.0):
    """Incoherent MTF at one frequency (see :func:`compute_mtf`)."""
    return float(compute_mtf(wavelength, NA, [spatial_freq], defocus)[0])


def compute_psf(wavelength, NA, pixel_size=None, grid_size=128):
    """
    Aberration-free incoherent PSF of a circular pupil by FFT, normalised to
    unit sum. Returns (psf, sample spacing in meters).
    """
    pupil, _, _ = compute_transfer_function(wavelength, 1.0, n=grid_size)
    pad = 4
    P = np.zeros((pad * grid_size, pad * grid_size), dtype=complex)
    P[:grid_size, :grid_size] = pupil
    psf = np.abs(np.fft.fftshift(np.fft.fft2(P))) ** 2
    psf /= psf.sum()
    dx = wavelength / (pad * grid_size * (2 * NA / (grid_size - 1)))
    return psf, dx


def partially_coherent_image(
    object_amplitude, wavelength, NA, pixel_size, sigma=0.5, n_source=9
):
    """
    Partially coherent image by Abbe's method: the intensity image is the
    sum over points of a uniform circular source (radius sigma NA in pupil
    units) of coherent images through the pupil (cutoff NA / lambda).

    Args:
        object_amplitude: complex or real 2D object transmission.
        sigma: coherence factor (condenser NA / objective NA); 0 = coherent.
        n_source: source points across the condenser diameter.
    """
    obj = np.asarray(object_amplitude, dtype=complex)
    ny, nx = obj.shape
    FX, FY = np.meshgrid(np.fft.fftfreq(nx, pixel_size), np.fft.fftfreq(ny, pixel_size))
    fc = NA / wavelength
    O = np.fft.fft2(obj)
    if sigma <= 0:
        pts = [(0.0, 0.0)]
    else:
        g = np.linspace(-1, 1, n_source)
        pts = [(sx, sy) for sx in g for sy in g if sx * sx + sy * sy <= 1.0]
    image = np.zeros((ny, nx))
    for sx, sy in pts:
        shift_x, shift_y = sx * sigma * fc, sy * sigma * fc
        H = ((FX + shift_x) ** 2 + (FY + shift_y) ** 2 <= fc * fc).astype(float)
        image += np.abs(np.fft.ifft2(O * H)) ** 2
    return image / len(pts)
