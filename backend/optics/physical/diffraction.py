"""
Diffraction propagation methods.

Implements:
- Fresnel diffraction (near-field)
- Fraunhofer diffraction (far-field)
- Angular spectrum method
- FFT-based propagation
"""

from typing import Optional, Tuple
import numpy as np
from numpy.fft import fft2, ifft2, fftshift, ifftshift


def fresnel_diffraction(
    field: np.ndarray,
    wavelength: float,
    distance: float,
    pixel_size: float,
) -> np.ndarray:
    """
    Fresnel diffraction by the transfer-function (convolution) method:
    U2 = IFFT{ FFT{U1} exp(i k z) exp(-i pi lambda z (fx^2 + fy^2)) }.
    The output sampling equals the input sampling.

    Args:
        field: Input complex field (2D array)
        wavelength: Wavelength (m)
        distance: Propagation distance (m)
        pixel_size: Pixel size in input plane (m)

    Returns:
        Output complex field
    """
    ny, nx = field.shape

    # Frequency coordinates
    dfx = 1 / (nx * pixel_size)
    dfy = 1 / (ny * pixel_size)
    fx = np.fft.fftfreq(nx, pixel_size)
    fy = np.fft.fftfreq(ny, pixel_size)
    FX, FY = np.meshgrid(fx, fy)

    # Fresnel transfer function
    H = np.exp(-1j * np.pi * wavelength * distance * (FX**2 + FY**2))

    # Propagation
    field_fft = fft2(field)
    output_fft = field_fft * H
    output = ifft2(output_fft)

    # Constant phase exp(i k z); the 1/(i lambda z) factor belongs to the
    # impulse-response form and is already contained in H.
    output *= np.exp(1j * 2 * np.pi * distance / wavelength)

    return output


def fraunhofer_diffraction(
    field: np.ndarray,
    wavelength: float,
    distance: float,
    pixel_size: float,
) -> np.ndarray:
    """
    Fraunhofer (far-field) diffraction:
    U2(x) = exp(ikz) exp(ik x^2 / 2z) / (i lambda z) * FT{U1}(x / lambda z).
    Output sampling is lambda z / (N dx); energy is conserved.

    Args:
        field: Input complex field (2D array)
        wavelength: Wavelength (m)
        distance: Propagation distance (m)
        pixel_size: Pixel size in input plane (m)

    Returns:
        Output complex field
    """
    ny, nx = field.shape

    if nx != ny:
        raise ValueError("Use a square field")
    k = 2 * np.pi / wavelength
    out_dx = wavelength * distance / (nx * pixel_size)
    x = (np.arange(nx) - nx // 2) * out_dx
    X, Y = np.meshgrid(x, x)
    field_fft = fftshift(fft2(ifftshift(field)))
    return (
        np.exp(1j * k * distance)
        * np.exp(1j * k * (X**2 + Y**2) / (2 * distance))
        / (1j * wavelength * distance)
        * field_fft
        * pixel_size**2
    )


def angular_spectrum_propagation(
    field: np.ndarray,
    wavelength: float,
    distance: float,
    pixel_size: float,
) -> np.ndarray:
    """
    Angular spectrum propagation method.

    Exact for scalar fields (within sampling limits) at any distance.

    Args:
        field: Input complex field (2D array)
        wavelength: Wavelength (m)
        distance: Propagation distance (m)
        pixel_size: Pixel size in input plane (m)

    Returns:
        Output complex field
    """
    ny, nx = field.shape

    # Frequency coordinates
    fx = np.fft.fftfreq(nx, pixel_size)
    fy = np.fft.fftfreq(ny, pixel_size)
    FX, FY = np.meshgrid(fx, fy)

    # Transfer function; evanescent components (kz imaginary) decay.
    k = 2 * np.pi / wavelength
    kz = np.sqrt((k**2 - (2 * np.pi * FX) ** 2 - (2 * np.pi * FY) ** 2).astype(complex))
    H = np.exp(1j * kz * distance)

    # Propagation
    field_fft = fft2(field)
    output_fft = field_fft * H
    output = ifft2(output_fft)

    return output


def propagate_to_waist(
    field: np.ndarray,
    wavelength: float,
    pixel_size: float,
    initial_distance: float = 0,
) -> Tuple[np.ndarray, float]:
    """
    Propagate field to find beam waist.

    Args:
        field: Input complex field
        wavelength: Wavelength (m)
        pixel_size: Pixel size (m)
        initial_distance: Starting distance (m)

    Returns:
        (field_at_waist, distance_to_waist)
    """
    # Simple approach: propagate in steps and find minimum beam width
    distance = initial_distance
    min_width = float("inf")
    best_field = field.copy()

    for d in np.linspace(0, 10 * pixel_size * field.shape[0], 100):
        propagated = angular_spectrum_propagation(field, wavelength, d, pixel_size)
        intensity = np.abs(propagated) ** 2

        # Calculate beam width (second moment)
        ny, nx = intensity.shape
        x = np.arange(nx) * pixel_size
        y = np.arange(ny) * pixel_size
        X, Y = np.meshgrid(x, y)

        total_power = np.sum(intensity)
        if total_power > 0:
            cx = np.sum(X * intensity) / total_power
            cy = np.sum(Y * intensity) / total_power
            width = 2 * np.sqrt(np.sum((X - cx) ** 2 * intensity) / total_power)

            if width < min_width:
                min_width = width
                best_field = propagated
                distance = d

    return best_field, distance


def calculate_diffraction_limit(
    aperture_diameter: float,
    focal_length: float,
    wavelength: float = 550e-9,
) -> float:
    """
    Calculate diffraction-limited spot size (Airy disk radius).

    Args:
        aperture_diameter: Aperture diameter (m)
        focal_length: Focal length (m)
        wavelength: Wavelength (m)

    Returns:
        Airy disk radius (m)
    """
    return 1.22 * wavelength * focal_length / aperture_diameter


def point_spread_function(
    pupil_function: np.ndarray,
    wavelength: float,
    focal_length: float,
    pixel_size: float,
) -> np.ndarray:
    """
    Calculate point spread function from pupil function.

    Args:
        pupil_function: Complex pupil function
        wavelength: Wavelength (m)
        focal_length: Focal length (m)
        pixel_size: Pixel size in pupil plane (m)

    Returns:
        PSF intensity
    """
    # PSF is |FFT(pupil)|²
    psf = np.abs(fftshift(fft2(ifftshift(pupil_function)))) ** 2

    # Normalize
    psf /= np.sum(psf)

    return psf


def optical_transfer_function(
    psf: np.ndarray,
) -> np.ndarray:
    """
    Calculate optical transfer function from PSF.

    Args:
        psf: Point spread function

    Returns:
        OTF (complex)
    """
    return fftshift(fft2(ifftshift(psf)))


def modulation_transfer_function(
    psf: np.ndarray,
) -> np.ndarray:
    """
    Calculate modulation transfer function from PSF.

    Args:
        psf: Point spread function

    Returns:
        MTF (real, normalized)
    """
    otf = optical_transfer_function(psf)
    mtf = np.abs(otf)

    # Normalize to 1 at zero frequency
    center = np.array(mtf.shape) // 2
    if mtf[center[0], center[1]] > 0:
        mtf /= mtf[center[0], center[1]]

    return mtf
