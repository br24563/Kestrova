"""
Optical quality metrics.

Provides:
- Strehl ratio
- Diffraction-limited performance metrics
- Point spread function analysis
- Encircled energy calculations
"""

from typing import Optional, Tuple
import numpy as np


def strehl_ratio(
    rms_wavefront_error: float,
    wavelength: float = 550e-9,
) -> float:
    """
    Strehl ratio estimated from the RMS wavefront error.

    Uses the extended Marechal approximation S ~ exp(-(2 pi W_rms / lambda)^2)
    (Mahajan, J. Opt. Soc. Am. 72, 1258 (1982)), accurate for S > ~0.3. For an
    exact value from a system's pupil use ``optics.pupil.strehl_ratio``.
    
    Args:
        rms_wavefront_error: RMS wavefront error in meters
        wavelength: Wavelength in meters
        
    Returns:
        Strehl ratio (0 to 1)
    """
    if wavelength <= 0:
        return 0.0
    
    W_rms = rms_wavefront_error
    strehl = np.exp(-(2 * np.pi * W_rms / wavelength)**2)
    
    return max(0.0, min(1.0, strehl))


def strehl_ratio_from_coeffs(
    zernike_coeffs: np.ndarray,
    wavelength: float = 550e-9,
) -> float:
    """
    Calculate Strehl ratio from Zernike coefficients.
    
    Args:
        zernike_coeffs: Zernike coefficients (excluding piston)
        wavelength: Wavelength in meters
        
    Returns:
        Strehl ratio
    """
    # RMS wavefront from Zernike coefficients (excluding piston)
    rms = np.sqrt(np.sum(zernike_coeffs**2))
    return strehl_ratio(rms, wavelength)


def diffraction_limited_check(
    rms_spot_radius: float,
    f_number: float,
    wavelength: float = 550e-9,
    rms_wavefront: Optional[float] = None,
) -> dict:
    """
    Diffraction-limit assessment.

    Geometric test: RMS spot radius within the Airy radius 1.22 lambda N
    (N = working F-number). When the RMS wavefront error is supplied, the
    Marechal test (W_rms <= lambda/14, Strehl >= 0.8) decides instead; a
    spot size alone cannot give a Strehl ratio.
    """
    airy_radius = 1.22 * wavelength * f_number
    margin = airy_radius / max(rms_spot_radius, 1e-15)
    out = {
        'airy_disk_radius': airy_radius,
        'rms_spot_radius': rms_spot_radius,
        'margin': margin,
        'geometric_criterion': rms_spot_radius <= airy_radius,
        'strehl_ratio': None,
        'wavefront_rms': rms_wavefront,
    }
    if rms_wavefront is not None:
        out['strehl_ratio'] = strehl_ratio(rms_wavefront, wavelength)
        out['is_diffraction_limited'] = rms_wavefront <= wavelength / 14.0
    else:
        out['is_diffraction_limited'] = out['geometric_criterion']
    return out


def encircled_energy(
    radius: float,
    wavelength: float = 550e-9,
    f_number: float = 2.0,
) -> float:
    """
    Encircled energy of the Airy pattern, 1 - J0(x)^2 - J1(x)^2 with
    x = pi r / (lambda N) (exact for an aberration-free circular pupil).
    
    Args:
        radius: Radius from center (meters)
        wavelength: Wavelength (meters)
        f_number: F-number
        
    Returns:
        Energy fraction (0 to 1)
    """
    from scipy.special import jv
    
    if radius <= 0:
        return 0.0
    
    # Normalized coordinate
    x = np.pi * radius / (wavelength * f_number)
    
    # Encircled energy formula for Airy pattern
    # EE(r) = 1 - J0(x)² - J1(x)²
    if x < 1e-10:
        return 0.0
    
    j0 = jv(0, x)
    j1 = jv(1, x)
    ee = 1 - j0**2 - j1**2
    
    return max(0.0, min(1.0, ee))


def encircled_energy_curve(
    wavelengths: np.ndarray = None,
    f_number: float = 2.0,
    num_points: int = 100,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate encircled energy curve.
    
    Args:
        wavelengths: Array of wavelengths (default: 550nm)
        f_number: F-number
        num_points: Number of radius points
        
    Returns:
        (radii, energy_fractions)
    """
    if wavelengths is None:
        wavelengths = np.array([550e-9])
    
    wl = wavelengths[0] if len(wavelengths) > 0 else 550e-9
    
    # Maximum radius (3x Airy radius)
    max_radius = 3 * 1.22 * wl * f_number
    radii = np.linspace(0, max_radius, num_points)
    
    energy = np.array([encircled_energy(r, wl, f_number) for r in radii])
    
    return radii, energy


def mtf_diffraction(
    frequency: np.ndarray,
    wavelength: float = 550e-9,
    f_number: float = 2.0,
) -> np.ndarray:
    """
    Diffraction-limited MTF of a circular pupil.

    Args:
        frequency: Spatial frequencies (cycles per meter)
        wavelength: Wavelength (meters)
        f_number: Working F-number
        
    Returns:
        MTF values
    """
    # Cutoff frequency
    f_c = 1 / (wavelength * f_number)
    
    # MTF formula for diffraction-limited system
    frequency = np.asarray(frequency, dtype=float)
    mtf = np.zeros_like(frequency)
    valid = frequency < f_c
    
    if np.any(valid):
        f_norm = frequency[valid] / f_c
        mtf[valid] = (2 / np.pi) * (np.arccos(f_norm) - f_norm * np.sqrt(1 - f_norm**2))
    
    return mtf


def psf_encircled_energy(
    psf_data: np.ndarray,
    pixel_size: float,
    num_rings: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate encircled energy from PSF data.
    
    Args:
        psf_data: 2D PSF intensity array
        pixel_size: Pixel size in meters
        num_rings: Number of radial bins
        
    Returns:
        (radii, energy_fraction)
    """
    ny, nx = psf_data.shape
    cy, cx = ny // 2, nx // 2
    
    # Create coordinate grids
    y, x = np.ogrid[-cy:ny-cy, -cx:nx-cx]
    r = np.sqrt(x**2 + y**2) * pixel_size
    
    # Maximum radius
    r_max = min(cy, cx) * pixel_size
    radii = np.linspace(0, r_max, num_rings)
    
    # Total energy
    total_energy = np.sum(psf_data)
    if total_energy == 0:
        return radii, np.zeros_like(radii)
    
    # Calculate encircled energy
    energy = np.zeros(num_rings)
    for i, radius in enumerate(radii):
        mask = r <= radius
        energy[i] = np.sum(psf_data[mask]) / total_energy
    
    return radii, energy


def quality_metrics(
    rms_wavefront: float = None,
    rms_spot: float = None,
    strehl: float = None,
    wavelength: float = 550e-9,
    f_number: float = None,
) -> dict:
    """
    Calculate comprehensive quality metrics.
    
    Args:
        rms_wavefront: RMS wavefront error (meters)
        rms_spot: RMS spot radius (meters)
        strehl: Strehl ratio (if known)
        wavelength: Wavelength (meters)
        f_number: F-number
        
    Returns:
        Dictionary with quality metrics
    """
    metrics = {}
    
    # Strehl ratio
    if strehl is not None:
        metrics['strehl_ratio'] = strehl
    elif rms_wavefront is not None:
        metrics['strehl_ratio'] = strehl_ratio(rms_wavefront, wavelength)
    else:
        metrics['strehl_ratio'] = None
    
    # Maréchal criterion (Strehl > 0.8)
    if metrics['strehl_ratio'] is not None:
        metrics['is_diffraction_limited'] = metrics['strehl_ratio'] > 0.8
    
    # Marechal criterion on the wavefront itself (W_rms <= lambda/14)
    if rms_wavefront is not None:
        metrics['marechal_criterion'] = rms_wavefront <= wavelength / 14
    
    # RMS values
    if rms_wavefront is not None:
        metrics['rms_wavefront'] = rms_wavefront
        metrics['waves_rms'] = rms_wavefront / wavelength
    
    if rms_spot is not None:
        metrics['rms_spot'] = rms_spot
    
    # Diffraction limit
    if f_number is not None:
        metrics['airy_disk_radius'] = 1.22 * wavelength * f_number
        if rms_spot is not None:
            metrics['margin_to_diffraction_limit'] = metrics['airy_disk_radius'] / rms_spot
    
    return metrics
