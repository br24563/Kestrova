"""Non-Sequential Enhancements for Professional Optical Design.

Adds advanced NSC capabilities:
- Beer-Lambert volumetric absorption, with absorption coefficients from the
  glass vendors' internal-transmittance data
- Fluorescence modeling (absorption + isotropic re-emission)
- Source spectra (blackbody, Gaussian) and an approximate display colour
- Plain-text ray file import/export (8 columns: x y z dx dy dz power
  wavelength; this is not the Zemax ZRD format)
"""

import math
from typing import Optional
from dataclasses import dataclass, field

import numpy as np

from .system import Ray, Vector3, HitPoint

# =============================================================================
# Beer-Lambert Volumetric Absorption
# =============================================================================


@dataclass
class VolumeProperties:
    """Volumetric material properties for absorption."""

    absorption_coeff: float = 0.0  # 1/meter
    scatter_coeff: float = 0.0  # 1/meter
    fluorescence_efficiency: float = 0.0
    fluorescence_wavelength: float = 600e-9
    fluorescence_decay: float = 1e-8  # seconds
    name: str = " "


def beer_lambert_transmittance(distance: float, absorption_coeff: float) -> float:
    """Calculate transmittance using Beer-Lambert law."""
    return math.exp(-absorption_coeff * distance)


def apply_volumetric_absorption(ray: Ray, distance: float, material: str) -> float:
    """
    Ray power after ``distance`` (meters) in ``material``, with the absorption
    coefficient from the vendor's internal transmittance at the ray's
    wavelength (raises ValueError when no data covers it).
    """
    from ..materials import get_material

    alpha = get_material(material).absorption_coefficient(ray.wavelength)
    return ray.intensity * beer_lambert_transmittance(distance, alpha)


# =============================================================================
# Fluorescence Modeling
# =============================================================================


@dataclass
class FluorescenceModel:
    """Fluorescence emission model."""

    absorption_wl: float = 400e-9
    emission_wl: float = 550e-9
    quantum_yield: float = 0.8
    decay_time: float = 1e-8
    emission_bandwidth: float = 50e-9


def compute_fluorescence_intensity(absorbed_intensity, model):
    """Compute fluorescence emission intensity."""
    return absorbed_intensity * model.quantum_yield


def generate_fluorescent_rays(ray, hit, model, n_rays=5):
    """Generate fluorescent emission rays."""
    emitted = []
    intensity = compute_fluorescence_intensity(ray.intensity, model)
    per_ray = intensity / n_rays if n_rays > 0 else 0
    for i in range(n_rays):
        theta = math.acos(1 - 2 * np.random.uniform(0, 1))
        phi = np.random.uniform(0, 2 * math.pi)
        dx = math.sin(theta) * math.cos(phi)
        dy = math.sin(theta) * math.sin(phi)
        dz = math.cos(theta)
        # emission_bandwidth is a FWHM
        wl = model.emission_wl + np.random.normal(
            0, model.emission_bandwidth / (2 * math.sqrt(2 * math.log(2)))
        )
        emitted.append(
            Ray(
                origin=hit.point,
                direction=Vector3(dx, dy, dz),
                intensity=per_ray,
                wavelength=wl,
                order=ray.order + 1,
            )
        )
    return emitted


# =============================================================================
# Source Spectrum and Color
# =============================================================================


@dataclass
class SpectralSource:
    """Spectral source definition."""

    wavelengths: list = field(default_factory=list)
    intensities: list = field(default_factory=list)
    name: str = "White"


def create_blackbody_spectrum(temperature, wl_range=None, n_samples=50):
    """Create blackbody radiation spectrum."""
    if wl_range is None:
        wl_range = (380e-9, 780e-9)
    h = 6.62607015e-34  # exact SI values
    c = 299792458.0
    k = 1.380649e-23
    wavelengths = np.linspace(wl_range[0], wl_range[1], n_samples)
    intensities = []
    for wl in wavelengths:
        i = (2 * h * c**2 / wl**5) / (math.exp(h * c / (wl * k * temperature)) - 1)
        intensities.append(i)
    intensities = np.array(intensities)
    intensities /= intensities.max() if intensities.max() > 0 else 1
    return SpectralSource(
        wavelengths=wavelengths.tolist(), intensities=intensities.tolist()
    )


def create_gaussian_spectrum(center_wl, fwhm, n_samples=50):
    """Create Gaussian spectral source."""
    sigma = fwhm / (2 * math.sqrt(2 * math.log(2)))
    wavelengths = np.linspace(center_wl - 3 * fwhm, center_wl + 3 * fwhm, n_samples)
    intensities = np.exp(-0.5 * ((wavelengths - center_wl) / sigma) ** 2)
    return SpectralSource(
        wavelengths=wavelengths.tolist(), intensities=intensities.tolist()
    )


def wavelength_to_rgb(wl):
    """
    Approximate display RGB of a monochromatic wavelength (piecewise-linear
    scheme after D. Bruton, 1996). Not colorimetry: use CIE colour-matching
    functions for colour calculations.
    """
    wl_nm = wl * 1e9
    if wl_nm < 380 or wl_nm > 780:
        return (0, 0, 0)
    if wl_nm < 440:
        r, g, b = -(wl_nm - 440) / (440 - 380), 0, 1
    elif wl_nm < 490:
        r, g, b = 0, (wl_nm - 440) / (490 - 440), 1
    elif wl_nm < 510:
        r, g, b = 0, 1, -(wl_nm - 510) / (510 - 490)
    elif wl_nm < 580:
        r, g, b = (wl_nm - 510) / (580 - 510), 1, 0
    elif wl_nm < 645:
        r, g, b = 1, -(wl_nm - 645) / (645 - 580), 0
    else:
        r, g, b = 1, 0, 0
    return (r, g, b)


def compute_rgb_from_spectrum(spectrum):
    """Intensity-weighted mean of :func:`wavelength_to_rgb` (display aid only)."""
    r_sum, g_sum, b_sum, total = 0, 0, 0, 0
    for wl, intensity in zip(spectrum.wavelengths, spectrum.intensities):
        r, g, b = wavelength_to_rgb(wl)
        r_sum += r * intensity
        g_sum += g * intensity
        b_sum += b * intensity
        total += intensity
    if total > 0:
        return (r_sum / total, g_sum / total, b_sum / total)
    return (0, 0, 0)


# =============================================================================
# NSC Ray File I/O
# =============================================================================


def export_rays_to_file(rays, filename):
    """Export ray data to a simple ray file format."""
    with open(filename, "w") as f:
        f.write("# NSC Ray File" + chr(10))
        for ray in rays:
            parts = [
                str(ray.origin.x),
                str(ray.origin.y),
                str(ray.origin.z),
                str(ray.direction.x),
                str(ray.direction.y),
                str(ray.direction.z),
                str(ray.intensity),
                str(ray.wavelength),
            ]
            f.write(" ".join(parts) + chr(10))


def import_rays_from_file(filename):
    """Import ray data from file."""
    rays = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 8:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                dx, dy, dz = float(parts[3]), float(parts[4]), float(parts[5])
                intensity, wl = float(parts[6]), float(parts[7])
                rays.append(
                    Ray(
                        origin=Vector3(x, y, z),
                        direction=Vector3(dx, dy, dz),
                        intensity=intensity,
                        wavelength=wl,
                    )
                )
    return rays
