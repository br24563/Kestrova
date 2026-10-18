"""
Image simulation: object to sensor through the real system.

Professional tools ship an image simulator (Zemax Image Simulation, Code V
``IMS``) because quantitative spot and MTF numbers do not tell you what the
customer will actually see. This module closes that gap:

    - object test targets (bar charts, Siemens star, grid, edge, point)
    - point spread function from diffraction and the real RMS spot size
    - relative illumination falloff across the field
    - radial distortion remapping from real chief-ray traces
    - sensor model: pixel sampling, full well, shot noise, read noise, ADC

Pixel convention
----------------
Everything is computed in **image-plane pixels**. One array pixel is one
sensor pixel of width ``SensorConfig.pixel_pitch``. The object pattern is
therefore sampled at an object-plane pitch of ``pixel_pitch / |m|``, where
``m`` is the system magnification, so a square wave with a period of P
pixels in the object arrives with a period of P pixels on the sensor.

Modeling notes
--------------
- The PSF is the system's own diffraction PSF, computed by FFT from the
  real-ray wavefront (:mod:`optics.pupil`), resampled onto the sensor pixel
  grid. With diffraction switched off, the PSF is the geometric spot
  (real-ray intercepts binned into pixels); with aberrations switched off it
  is the Airy pattern of the system's working F-number.
- Relative illumination comes from the projected solid angle of the real
  ray bundle (:mod:`optics.illumination`); distortion from real chief rays.
- Noise is photon shot noise (Poisson) plus Gaussian read noise, in
  electrons, then quantised to ADU at the given bit depth and gain.
- Polychromatic effects are not simulated: one wavelength (the analysis
  wavelength) is used.

All values are in SI base units (meters) except the array-valued results,
which are in image-plane pixels.
"""

import math
import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.ndimage import map_coordinates
from scipy.signal import fftconvolve
from scipy.special import j1

from .models import OpticalSystem, ImagePlane


# =============================================================================
# Sensor model
# =============================================================================

@dataclass
class SensorConfig:
    """
    Detector properties used by the image simulator.

    Defaults describe a small scientific CMOS sensor.
    """
    resolution: int = 128          # pixels per side (square sensor)
    pixel_pitch: float = 5.0e-6    # m
    quantum_efficiency: float = 0.6
    full_well: float = 20000.0     # electrons
    read_noise: float = 5.0        # electrons RMS
    dark_current: float = 0.0      # electrons / pixel / second
    exposure_time: float = 1.0e-3  # s
    bit_depth: int = 12
    gain: float = 4.88             # electrons per ADU; see the note below
    fill_factor: float = 1.0       # fraction of the pixel that collects light

    # The default gain is full_well / (2^bit_depth - 1) = 20000 / 4095, so the
    # ADC full scale coincides with the full well. A lower gain makes the ADC
    # the limiting element and clips the signal long before the well fills,
    # which silently defeats ``peak_fraction_of_full_well``; that case is
    # still detected and reported as saturation.

    @property
    def max_adu(self) -> int:
        """Saturation level in ADU for the configured bit depth."""
        return (1 << int(self.bit_depth)) - 1

    def half_diagonal(self) -> float:
        """Half-diagonal extent of the sensor in meters."""
        return math.sqrt(2.0) * self.resolution * self.pixel_pitch / 2.0


def effective_f_number(system: OpticalSystem,
                       wavelength: Optional[float] = None) -> float:
    """Infinite-conjugate F-number EFL / entrance-pupil diameter (inf if undefined)."""
    from .analysis import system_f_number
    try:
        fno = float(system_f_number(system))
    except ValueError:
        return float("inf")
    return fno if math.isfinite(fno) and fno > 0 else float("inf")


def working_f_number(system: OpticalSystem,
                     wavelength: Optional[float] = None) -> float:
    """Working F-number 1 / (2 NA'), NA' from the real image-space marginal ray."""
    from .pupil import image_space_na
    try:
        na = image_space_na(system, wavelength)
    except ValueError:
        return float("inf")
    return 1.0 / (2.0 * na) if na > 0 else float("inf")


def magnification(system: OpticalSystem,
                  wavelength: Optional[float] = None) -> float:
    """
    Paraxial lateral magnification. For an object at infinity, the ratio of
    image height to the object height at its (large) distance, -EFL/distance.
    """
    from . import raytrace as rt
    seq = rt.build_sequence(system, wavelength)
    fo = rt.first_order(system, seq=seq)
    if not seq.object_infinite:
        return fo.magnification
    return -fo.efl / (seq.surfaces[0].z - system.object.position)


def object_pixel_pitch(system: OpticalSystem, sensor: SensorConfig,
                       wavelength: Optional[float] = None) -> float:
    """Object-plane sampling pitch that maps onto one sensor pixel."""
    m = abs(magnification(system, wavelength))
    if m < 1e-15:
        return sensor.pixel_pitch
    return sensor.pixel_pitch / m


def field_of_view(system: OpticalSystem, sensor: SensorConfig,
                  wavelength: Optional[float] = None) -> float:
    """Object-plane extent covered by the sensor (meters)."""
    return sensor.resolution * object_pixel_pitch(system, sensor, wavelength)


# =============================================================================
# Point spread function
# =============================================================================

def _psf_grid_size(f_number: float, wavelength: float, pixel_pitch: float,
                   rms_spot: float = 0.0,
                   min_size: int = 33, max_size: int = 401) -> int:
    """Odd PSF grid size that contains the Airy disk and the blur envelope."""
    airy_extent = 6.0 * wavelength * f_number if math.isfinite(f_number) else 0.0
    blur_extent = 4.0 * max(rms_spot, 0.0)
    extent = max(airy_extent, blur_extent)
    needed = int(math.ceil(2.0 * extent / pixel_pitch)) + 1
    size = max(min_size, needed)
    if size % 2 == 0:
        size += 1
    return int(min(size, max_size))


def airy_psf(f_number: float, wavelength: float, pixel_pitch: float,
             size: Optional[int] = None) -> np.ndarray:
    """
    Diffraction-limited PSF integrated over each sensor pixel.

    The Airy pattern is I(v) / I0 = (2 J1(v) / v)^2 with v = pi r / (lambda N);
    it is averaged over a 9 x 9 sub-grid in every pixel, since pixels are
    often comparable to the Airy disk.

    Args:
        f_number: Working f-number.
        wavelength: Wavelength in meters.
        pixel_pitch: Sensor pixel pitch in meters.
        size: Optional grid size (pixels); chosen automatically if None.

    Returns:
        Normalised 2D array (sums to 1).
    """
    if size is None:
        size = _psf_grid_size(f_number, wavelength, pixel_pitch)
    half = size // 2
    sub = 9
    axis = ((np.arange(size * sub, dtype=float) + 0.5) / sub - 0.5 - half) * pixel_pitch
    rr = np.hypot(axis[None, :], axis[:, None])

    if not math.isfinite(f_number) or f_number <= 0:
        psf = np.zeros((size, size))
        psf[half, half] = 1.0
        return psf

    v = math.pi * rr / (wavelength * f_number)
    safe_v = np.where(v < 1e-9, 1.0, v)
    psf = (2.0 * j1(safe_v) / safe_v) ** 2
    psf = np.where(v < 1e-9, 1.0, psf)
    psf = np.nan_to_num(psf, nan=0.0, posinf=0.0)
    psf = psf.reshape(size, sub, size, sub).sum(axis=(1, 3))
    total = float(psf.sum())
    return psf / total if total > 0 else psf


def _overlap_matrix(centres: np.ndarray, width: float, edges: np.ndarray) -> np.ndarray:
    """(len(edges)-1, len(centres)) fraction of each sample cell of the given
    width lying inside each pixel interval."""
    lo = centres - width / 2.0
    hi = centres + width / 2.0
    a = np.maximum(lo[None, :], edges[:-1, None])
    b = np.minimum(hi[None, :], edges[1:, None])
    return np.clip(b - a, 0.0, None) / width


def _resample_psf(x: np.ndarray, psf2d: np.ndarray, pixel_pitch: float,
                  size: Optional[int]) -> np.ndarray:
    """
    Integrate a finely sampled PSF into sensor pixels centred on its
    centroid, each sample treated as a uniform cell whose area is shared
    exactly among the pixels it overlaps. Normalised to sum 1.
    """
    dx = x[1] - x[0]
    w = psf2d / psf2d.sum()
    cx = float((w.sum(axis=0) * x).sum())
    cy = float((w.sum(axis=1) * x).sum())
    if size is None:
        r = math.sqrt(float((w.sum(axis=0) * (x - cx) ** 2).sum()
                            + (w.sum(axis=1) * (x - cy) ** 2).sum()))
        size = int(2 * math.ceil(4.0 * max(r, dx) / pixel_pitch) + 1)
        size = max(9, min(size, 401))
    half = size // 2
    edges = (np.arange(size + 1) - half - 0.5) * pixel_pitch
    Ax = _overlap_matrix(x - cx, dx, edges)
    Ay = _overlap_matrix(x - cy, dx, edges)
    out = Ay @ w @ Ax.T
    t = out.sum()
    return out / t if t > 0 else out


def psf_for_system(system: OpticalSystem, field_fraction: float = 0.0,
                   sensor: Optional[SensorConfig] = None,
                   wavelength: Optional[float] = None,
                   size: Optional[int] = None,
                   num_rays: int = 64) -> np.ndarray:
    """
    The system's diffraction PSF at a field point from its real-ray
    wavefront, integrated into sensor pixels and normalised to sum 1.

    The aberrations come from the wavefront itself. ``num_rays`` is the pupil grid
    size (it is raised automatically when the wavefront is too steep to
    sample).
    """
    from . import pupil as pp
    if sensor is None:
        sensor = SensorConfig()
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength
    n = max(32, int(num_rays))
    for _ in range(4):
        g = pp.wavefront_grid(system, field_fraction, n, wavelength)
        # phase step between neighbouring samples must stay below pi
        W = np.where(g.mask, g.W, np.nan)
        step = np.nanmax(np.abs(np.diff(W, axis=0))) if g.mask.any() else 0.0
        step = max(step, np.nanmax(np.abs(np.diff(W, axis=1))) if g.mask.any() else 0.0)
        if not np.isfinite(step) or step < 0.5 * wavelength or n >= 512:
            break
        n *= 2
    # Zero-pad the pupil so the PSF is sampled at <= 1/16 pixel (sinc
    # interpolation), capped at a 4096-point FFT.
    m = g.W.shape[0]
    dx4 = wavelength * (m - 1) / (4 * m * 2.0 * g.na_image)
    pad = int(min(max(4, math.ceil(4 * 16 * dx4 / sensor.pixel_pitch)), max(4, 4096 // m)))
    res = pp.psf(g, pad=pad)
    return _resample_psf(res.x, res.intensity, sensor.pixel_pitch, size)


def geometric_psf(system: OpticalSystem, field_fraction: float, sensor: SensorConfig,
                  size: Optional[int] = None, grid: int = 41,
                  wavelength: Optional[float] = None) -> np.ndarray:
    """Geometric PSF: real-ray image-plane intercepts binned into pixels."""
    from .analysis import real_spot
    pts, _, _, _, _ = real_spot(system, field_fraction, grid, wavelength=wavelength)
    pts = np.asarray(pts)
    if size is None:
        ext = np.max(np.abs(pts)) if len(pts) else 0.0
        size = max(9, min(401, int(2 * math.ceil(ext / sensor.pixel_pitch) + 3)))
    half = size // 2
    out = np.zeros((size, size))
    if len(pts):
        ix = np.floor(pts[:, 0] / sensor.pixel_pitch + 0.5).astype(int) + half
        iy = np.floor(pts[:, 1] / sensor.pixel_pitch + 0.5).astype(int) + half
        ok = (ix >= 0) & (ix < size) & (iy >= 0) & (iy < size)
        np.add.at(out, (iy[ok], ix[ok]), 1.0)
    else:
        out[half, half] = 1.0
    return out / out.sum()


def rms_spot_radius(system: OpticalSystem, field_fraction: float = 0.0,
                    num_rays: int = 15,
                    wavelength: Optional[float] = None) -> float:
    """Real-ray RMS spot radius about the centroid (meters)."""
    from .analysis import real_spot
    return real_spot(system, field_fraction, num_rays, wavelength=wavelength)[1]


# =============================================================================
# Object test targets
# =============================================================================

TEST_TARGETS = (
    "bars", "siemens", "grid", "checkerboard", "edge", "point", "flat",
)


def _square_wave(coord: np.ndarray, period: float, duty: float = 0.5) -> np.ndarray:
    """Binary square wave in [0, 1] with the given period and duty cycle."""
    phase = np.mod(coord, period) / period
    return (phase < duty).astype(float)


def test_target(kind: str = "bars", size: int = 128,
                periods=(4, 8, 16, 32), duty: float = 0.5,
                num_spokes: int = 36, line_width: int = 2,
                contrast: float = 1.0, background: float = 0.0) -> np.ndarray:
    """
    Build an object-plane test pattern.

    Args:
        kind: One of :data:`TEST_TARGETS`.
        size: Pattern size in pixels (square).
        periods: Bar periods in object pixels, one per horizontal band
            (``bars`` and ``checkerboard``).
        duty: Bright fraction of each bar period.
        num_spokes: Number of spokes in the Siemens star.
        line_width: Line width in pixels for ``grid``.
        contrast: Peak-to-peak modulation of the pattern.
        background: Base level of the pattern.

    Returns:
        2D float array with values in [0, 1].
    """
    kind = (kind or "bars").strip().lower()
    if kind not in TEST_TARGETS:
        raise ValueError(
            f"Unknown test target {kind!r}; expected one of {TEST_TARGETS}")

    n = max(4, int(size))
    coord = np.arange(n, dtype=float)
    xx, yy = np.meshgrid(coord, coord, indexing="xy")

    if kind == "flat":
        pattern = np.ones((n, n), dtype=float)

    elif kind == "point":
        pattern = np.zeros((n, n), dtype=float)
        pattern[n // 2, n // 2] = 1.0

    elif kind == "edge":
        pattern = (xx >= n / 2.0).astype(float)

    elif kind == "grid":
        w = max(1, int(line_width))
        period = max(w + 1, n // 8)
        vertical = (np.mod(xx, period) < w).astype(float)
        horizontal = (np.mod(yy, period) < w).astype(float)
        pattern = np.clip(vertical + horizontal, 0.0, 1.0)

    elif kind == "siemens":
        cx = cy = (n - 1) / 2.0
        angle = np.arctan2(yy - cy, xx - cx)
        pattern = (np.cos(num_spokes * angle) >= 0.0).astype(float)

    elif kind == "checkerboard":
        periods = tuple(periods) if periods else (8,)
        pattern = np.zeros((n, n), dtype=float)
        band_h = max(1, n // len(periods))
        for i, p in enumerate(periods):
            p = max(2.0, float(p))
            r0 = i * band_h
            r1 = n if i == len(periods) - 1 else min(n, r0 + band_h)
            checker = _square_wave(xx[r0:r1], p, 0.5) * _square_wave(yy[r0:r1], p, 0.5)
            pattern[r0:r1] = checker

    else:  # "bars"
        periods = tuple(periods) if periods else (4, 8, 16, 32)
        pattern = np.zeros((n, n), dtype=float)
        band_h = max(1, n // len(periods))
        for i, p in enumerate(periods):
            p = max(2.0, float(p))
            r0 = i * band_h
            r1 = n if i == len(periods) - 1 else min(n, r0 + band_h)
            pattern[r0:r1] = _square_wave(xx[r0:r1], p, duty)

    return np.clip(background + contrast * pattern, 0.0, 1.0)


# =============================================================================
# Field-dependent effects
# =============================================================================

def distortion_curve(system: OpticalSystem, num_fields: int = 11,
                     field_fraction_max: float = 1.0) -> dict:
    """
    Distortion from real chief rays at the paraxial image plane:
    D = 100 (h_real - h_paraxial) / h_paraxial.
    """
    from . import raytrace as rt
    seq0 = rt.build_sequence(system)
    fo0 = rt.first_order(system, seq=seq0)
    s = system.model_copy(update={"image_plane": ImagePlane(position=fo0.image_z)})
    seq = rt.build_sequence(s)
    fo = rt.first_order(s, seq=seq)
    fractions = np.linspace(0.0, float(field_fraction_max), max(2, num_fields))
    real_mm, par_mm, dist = [], [], []
    for ff in fractions:
        b, _, _ = rt.trace_field_rays(s, 0.0, float(ff), np.array([0.0]), np.array([0.0]),
                                      seq=seq, fo=fo, clip=False)
        h_real = float(rt._to_local(seq.image_origin, seq.image_rotation, b.image,
                                    b.directions)[0][0, 1])
        h_par = fo.image_height * float(ff)
        real_mm.append(h_real * 1e3)
        par_mm.append(h_par * 1e3)
        dist.append(100.0 * (h_real - h_par) / h_par if abs(h_par) > 1e-15 else 0.0)
    return {
        "field_fractions": [float(f) for f in fractions],
        "real_image_height_mm": real_mm,
        "paraxial_image_height_mm": par_mm,
        "distortion_percent": dist,
        "edge_distortion_percent": dist[-1],
        "max_abs_distortion_percent": max(abs(d) for d in dist),
    }


def relative_illumination_profile(system: OpticalSystem, num_fields: int = 11) -> dict:
    """Relative illumination versus field (see :mod:`optics.illumination`)."""
    from .illumination import relative_illumination
    return relative_illumination(system, num_fields=num_fields)


def relative_illumination_map(system: OpticalSystem, sensor: SensorConfig,
                              num_fields: int = 11, vignetting: bool = True) -> np.ndarray:
    """
    Relative illumination over the sensor, the sensor half-diagonal being the
    edge of the field. With ``vignetting=False`` only the thin-lens cos^4
    obliquity factor is applied.
    """
    from .illumination import relative_illumination, cos4_falloff, chief_ray_image_angle
    fractions = np.linspace(0.0, 1.0, max(2, num_fields))
    if vignetting:
        values = np.asarray(relative_illumination(system, len(fractions))["relative_illumination"])
    else:
        values = np.array([cos4_falloff(chief_ray_image_angle(system, float(f))) for f in fractions])
        values = values / values[0]
    n = sensor.resolution
    half = (n - 1) / 2.0
    ax = (np.arange(n, dtype=float) - half) / max(half, 1e-12)
    rr = np.clip(np.hypot(ax[None, :], ax[:, None]), 0.0, 1.0)
    return np.interp(rr, fractions, values)


# =============================================================================
# Sensor response
# =============================================================================

def sensor_response(image: np.ndarray, sensor: SensorConfig,
                    peak_fraction_of_full_well: float = 0.8,
                    seed: Optional[int] = None,
                    noise: bool = True) -> dict:
    """
    Apply the detector model to a normalised irradiance map.

    Photon shot noise is applied to the *incident* photon count, which is
    then converted to electrons through the quantum efficiency and fill
    factor. That ordering matters: shot noise belongs to the photons, not to
    the electrons that survive detection.

    Args:
        image: Normalised irradiance map (0 to 1).
        sensor: Detector parameters.
        peak_fraction_of_full_well: Signal level of the brightest pixel as a
            fraction of the full well. Sets the exposure.
        seed: Optional RNG seed for reproducible noise.
        noise: Set False for a noiseless (ideal detector) result.

    Returns:
        Dict with "electrons", "adu", "image" (0 to 1), "peak_electrons",
        "saturated_pixels", "mean_snr" and "peak_snr".
    """
    arr = np.asarray(image, dtype=float)
    peak = float(arr.max())
    if peak <= 0:
        peak = 1.0
    norm = np.clip(arr / peak, 0.0, 1.0)

    qe = max(1e-6, float(sensor.quantum_efficiency))
    fill = max(1e-6, float(sensor.fill_factor))
    conversion = qe * fill

    target_electrons = norm * (peak_fraction_of_full_well * sensor.full_well)
    incident_mean = target_electrons / conversion

    rng = np.random.default_rng(seed)
    if noise:
        incident = rng.poisson(incident_mean).astype(float)
    else:
        incident = incident_mean

    signal_electrons = incident * conversion
    dark_mean = max(0.0, sensor.dark_current) * max(0.0, sensor.exposure_time)
    if dark_mean > 0.0 and noise:
        signal_electrons = signal_electrons + rng.poisson(dark_mean, size=arr.shape)
    elif dark_mean > 0.0:
        signal_electrons = signal_electrons + dark_mean

    if noise and sensor.read_noise > 0:
        signal_electrons = signal_electrons + rng.normal(
            0.0, sensor.read_noise, size=arr.shape)

    gain = max(1e-9, float(sensor.gain))
    # Electrons the ADC can represent at this gain. When the gain is set low
    # relative to the full well and bit depth this is the tighter limit, and
    # the signal clips in the ADC before the well fills.
    adc_full_scale = float(sensor.max_adu) * gain

    saturated = int(np.count_nonzero(
        (signal_electrons >= sensor.full_well)
        | (signal_electrons >= adc_full_scale)))
    clipped = np.clip(signal_electrons, 0.0, min(sensor.full_well, adc_full_scale))

    adu = np.clip(np.floor(clipped / gain), 0, sensor.max_adu).astype(np.uint16)

    shot = np.sqrt(np.maximum(np.abs(signal_electrons), 1.0))
    noise_total = np.sqrt(shot ** 2 + max(0.0, sensor.read_noise) ** 2
                          + max(dark_mean, 0.0))
    snr = np.divide(signal_electrons, noise_total,
                    out=np.zeros_like(signal_electrons), where=noise_total > 0)

    return {
        "electrons": signal_electrons,
        "adu": adu,
        "image": adu.astype(float) / float(sensor.max_adu),
        "peak_electrons": float(signal_electrons.max()),
        "saturated_pixels": saturated,
        "mean_snr": float(np.mean(snr)),
        "peak_snr": float(np.max(snr)),
        "max_adu": sensor.max_adu,
        "adc_full_scale_electrons": adc_full_scale,
    }


# =============================================================================
# Full simulation
# =============================================================================

@dataclass
class SimulationResult:
    """Output of :func:`simulate_image`."""
    image: np.ndarray            # displayed image, 0 to 1
    adu: np.ndarray              # raw ADU
    electrons: np.ndarray
    ideal: np.ndarray            # before blur, illumination and noise
    psf: np.ndarray
    illumination: np.ndarray
    sensor: SensorConfig = field(default_factory=SensorConfig)
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Summary dict (arrays are summarised, not serialised)."""
        md = dict(self.metadata)
        md.update({
            "shape": list(self.image.shape),
            "image_min": float(self.image.min()),
            "image_max": float(self.image.max()),
            "image_mean": float(self.image.mean()),
            "ideal_mean": float(self.ideal.mean()),
            "psf_shape": list(self.psf.shape),
        })
        return md

    def ascii_preview(self, width: int = 56, height: Optional[int] = None,
                      chars: str = " .:-=+*#%@") -> str:
        """Render the image as ASCII so results are visible in a terminal."""
        return ascii_preview(self.image, width=width, height=height, chars=chars)

    def png_bytes(self) -> bytes:
        """Encode the image as an 8-bit greyscale PNG."""
        return encode_png_gray(self.image)

    def save_png(self, path: str) -> str:
        """Write the image to an 8-bit greyscale PNG and return the path."""
        with open(path, "wb") as fh:
            fh.write(self.png_bytes())
        return path


def _distort(image: np.ndarray, sensor: SensorConfig,
             curve: dict) -> np.ndarray:
    """
    Remap an ideal image by the system's radial distortion.

    For each output pixel the distorted image height is known; the curve
    gives the paraxial height that produced it, and the ideal image is
    sampled there.

    The mapping is radial, so the curve is used through the *magnitude* of
    each image height. ``distortion_curve`` reports signed heights (an
    inverting system has negative image heights), and interpolating the
    positive sensor radii against a signed, negative curve would clamp every
    sample to a single point -- collapsing the image to a constant.
    """
    distorted = np.abs(np.asarray(curve.get("real_image_height_mm"), dtype=float))
    paraxial = np.abs(np.asarray(curve.get("paraxial_image_height_mm"), dtype=float))
    if distorted.size < 2 or paraxial.size < 2:
        return image
    order = np.argsort(distorted)
    d_sorted = distorted[order]
    p_sorted = paraxial[order]
    if np.ptp(d_sorted) < 1e-12:
        return image

    n = sensor.resolution
    half = (n - 1) / 2.0
    coords = (np.arange(n, dtype=float) - half)
    # Sensor radius in the same units the curve uses.
    scale = sensor.pixel_pitch * 1e3   # m -> mm per pixel
    yy, xx = np.meshgrid(coords, coords, indexing="ij")
    r_mm = np.hypot(xx, yy) * scale

    r_par = np.interp(r_mm, d_sorted, p_sorted, left=p_sorted[0], right=p_sorted[-1])
    with np.errstate(invalid="ignore", divide="ignore"):
        factor = np.where(r_mm > 1e-12, r_par / r_mm, 1.0)
    src_y = (half + (yy - 0.0) * factor).ravel()
    src_x = (half + (xx - 0.0) * factor).ravel()
    sampled = map_coordinates(np.asarray(image, dtype=float),
                              [src_y, src_x], order=1, mode="nearest")
    return sampled.reshape(n, n)


def _convolve_psf(image: np.ndarray, psf: np.ndarray) -> np.ndarray:
    """
    Convolve an image with a normalised PSF, preserving the mean level.

    Uses an FFT convolution normalised by the convolution of a flat field,
    which makes a uniform input map exactly to itself (the same guarantee
    the direct ``mode="nearest"`` convolution gave) while keeping the cost
    at O(N^2 log N) in the image size regardless of the kernel size.

    A direct convolution costs O(N^2 M^2) and is impractical, and
    memory-hungry, once the blur exceeds a few tens of pixels -- which
    happens for any defocused or strongly aberrated system, exactly the
    cases the simulator is most useful for.
    """
    image = np.asarray(image, dtype=float)
    psf = np.asarray(psf, dtype=float)
    if psf.ndim != 2 or psf.size <= 1:
        return image
    total = float(psf.sum())
    if total <= 0:
        return image
    kernel = psf / total
    blurred = fftconvolve(image, kernel, mode="same")
    # Weight of the kernel that actually landed on each pixel; dividing by it
    # restores the flat-field response at the borders.
    weight = fftconvolve(np.ones_like(image), kernel, mode="same")
    weight = np.where(weight > 1e-12, weight, 1.0)
    return blurred / weight


def simulate_image(system: OpticalSystem,
                   target=None,
                   sensor: Optional[SensorConfig] = None,
                   target_kind: str = "bars",
                   field_fraction: float = 0.0,
                   full_field: bool = False,
                   with_diffraction: bool = True,
                   with_aberration: bool = True,
                   with_vignetting: bool = True,
                   with_distortion: bool = True,
                   with_noise: bool = True,
                   peak_fraction_of_full_well: float = 0.8,
                   num_rays: int = 9,
                   seed: Optional[int] = None,
                   target_kwargs: Optional[dict] = None) -> SimulationResult:
    """
    Simulate an image of a test target through the real system.

    Args:
        system: The optical system.
        target: Optional object pattern (a 2D array in image-plane pixels).
            When omitted, ``target_kind`` is used to build one sized to the
            sensor.
        sensor: Sensor definition; defaults to :class:`SensorConfig`.
        target_kind: Test target used when ``target`` is None.
        field_fraction: Field point for the PSF and illumination (0 = axis).
            Ignored for the PSF when ``full_field`` is True.
        full_field: Model the whole field: blend the axis and edge PSFs
            radially, apply the radial illumination map and remap distortion.
        with_diffraction: Include diffraction (the PSF from the pupil).
        with_aberration: Include the real wavefront aberrations.
        with_vignetting: Apply the relative illumination (vignetting and
            obliquity, from the real ray bundle).
        with_distortion: Include radial distortion remapping (full field only).
        with_noise: Apply shot, dark and read noise.
        peak_fraction_of_full_well: Exposure level of the brightest pixel.
        num_rays: Unused (kept for compatibility); sampling is automatic.
        seed: RNG seed for reproducible noise.
        target_kwargs: Extra keyword arguments for :func:`test_target`.

    Returns:
        A :class:`SimulationResult`.
    """
    if sensor is None:
        sensor = SensorConfig()
    n = sensor.resolution
    wavelength = system.analysis_settings.wavelength

    if target is None:
        target = test_target(kind=target_kind, size=n, **(target_kwargs or {}))
    ideal = np.asarray(target, dtype=float)
    if ideal.shape != (n, n):
        ideal = np.resize(ideal, (n, n))
    ideal = np.clip(ideal, 0.0, 1.0)

    f_number = effective_f_number(system, wavelength)
    mag = magnification(system, wavelength)

    # --- distortion -------------------------------------------------------
    curve = distortion_curve(system) if full_field else None
    working = _distort(ideal, sensor, curve) if (full_field and with_distortion
                                                and curve) else ideal.copy()

    # --- point spread function -------------------------------------------
    def make_psf(ff, size=None):
        if with_diffraction and with_aberration:
            return psf_for_system(system, ff, sensor, wavelength, size=size)
        if with_diffraction:
            return airy_psf(working_f_number(system, wavelength), wavelength,
                            sensor.pixel_pitch, size)
        if with_aberration:
            return geometric_psf(system, ff, sensor, size)
        p = np.zeros((size or 1, size or 1))
        p[p.shape[0] // 2, p.shape[1] // 2] = 1.0
        return p

    psf_axis = make_psf(0.0 if full_field else field_fraction)
    if full_field:
        psf_edge = make_psf(1.0)
        size = max(psf_axis.shape[0], psf_edge.shape[0])
        psf_axis, psf_edge = _pad_psf(psf_axis, size), _pad_psf(psf_edge, size)
        blurred_axis = _convolve_psf(working, psf_axis)
        blurred_edge = _convolve_psf(working, psf_edge)
        half = (n - 1) / 2.0
        ax = (np.arange(n, dtype=float) - half) / max(half, 1e-12)
        w = np.clip(np.hypot(ax[None, :], ax[:, None]), 0.0, 1.0)
        blurred = (1.0 - w) * blurred_axis + w * blurred_edge
    else:
        blurred = _convolve_psf(working, psf_axis)

    # --- illumination -----------------------------------------------------
    if with_vignetting:
        if full_field:
            illum_map = relative_illumination_map(system, sensor)
        else:
            prof = relative_illumination_profile(system)
            idx = int(round(np.clip(field_fraction, 0.0, 1.0)
                            * (len(prof["relative_illumination"]) - 1)))
            level = prof["relative_illumination"][idx] if prof["relative_illumination"] else 1.0
            illum_map = np.full((n, n), level, dtype=float)
    else:
        illum_map = np.ones((n, n), dtype=float)

    lit = np.clip(blurred * illum_map, 0.0, None)

    # --- sensor -----------------------------------------------------------
    response = sensor_response(lit, sensor,
                               peak_fraction_of_full_well=peak_fraction_of_full_well,
                               seed=seed, noise=with_noise)

    metadata = {
        "sensor": {
            "resolution": sensor.resolution,
            "pixel_pitch_um": sensor.pixel_pitch * 1e6,
            "full_well": sensor.full_well,
            "read_noise": sensor.read_noise,
            "bit_depth": sensor.bit_depth,
            "gain": sensor.gain,
            "quantum_efficiency": sensor.quantum_efficiency,
        },
        "f_number": f_number,
        "working_f_number": working_f_number(system, wavelength),
        "magnification": mag,
        "object_pixel_pitch_um": object_pixel_pitch(system, sensor, wavelength) * 1e6,
        "field_of_view_mm": field_of_view(system, sensor, wavelength) * 1e3,
        "image_pixel_pitch_um": sensor.pixel_pitch * 1e6,
        "wavelength_m": wavelength,
        "field_fraction": field_fraction,
        "full_field": full_field,
        "with_diffraction": with_diffraction,
        "with_aberration": with_aberration,
        "with_vignetting": with_vignetting,
        "with_distortion": with_distortion,
        "with_noise": with_noise,
        "psf_fwhm_pixels": _psf_fwhm_pixels(psf_axis),
        "edge_distortion_percent": (curve or {}).get("edge_distortion_percent", 0.0),
        "min_relative_illumination": float(illum_map.min()),
        "saturated_pixels": response["saturated_pixels"],
        "mean_snr": response["mean_snr"],
        "peak_snr": response["peak_snr"],
        "peak_electrons": response["peak_electrons"],
    }

    return SimulationResult(
        image=response["image"],
        adu=response["adu"],
        electrons=response["electrons"],
        ideal=ideal,
        psf=psf_axis,
        illumination=illum_map,
        sensor=sensor,
        metadata=metadata,
    )


# =============================================================================
# PSF helpers
# =============================================================================

def _gaussian_psf(size: int, sigma_pixels: float) -> np.ndarray:
    """Normalised sampled Gaussian PSF of the given grid size."""
    size = max(1, int(size))
    if size % 2 == 0:
        size += 1
    half = size // 2
    axis = np.arange(size, dtype=float) - half
    if sigma_pixels <= 1e-9:
        psf = np.zeros((size, size), dtype=float)
        psf[half, half] = 1.0
        return psf
    rr = np.hypot(axis[None, :], axis[:, None])
    psf = np.exp(-0.5 * (rr / sigma_pixels) ** 2)
    return psf / psf.sum()


def _pad_psf(psf: np.ndarray, size: int) -> np.ndarray:
    """Centre-pad a PSF onto a larger grid, keeping the origin on a pixel."""
    psf = np.asarray(psf, dtype=float)
    size = max(1, int(size))
    if size % 2 == 0:
        size += 1
    n = psf.shape[0]
    if n % 2 == 0:
        psf = np.pad(psf, ((0, 1), (0, 1)))
        n = psf.shape[0]
    if size <= n:
        return psf
    out = np.zeros((size, size), dtype=float)
    offset = (size - n) // 2
    out[offset:offset + n, offset:offset + n] = psf
    return out


def _psf_fwhm_pixels(psf: np.ndarray) -> float:
    """Full width at half maximum of a PSF, in pixels."""
    psf = np.asarray(psf, dtype=float)
    if psf.ndim != 2 or min(psf.shape) < 2:
        return 0.0
    half = psf.shape[0] // 2
    profile = psf[half, half:]
    if profile.size < 2 or profile[0] <= 0:
        return 0.0
    target = profile[0] / 2.0
    below = np.where(profile <= target)[0]
    if below.size == 0:
        return float(profile.size - 1)
    k = int(below[0])
    if k == 0:
        return 0.0
    r0, r1 = float(profile[k - 1]), float(profile[k])
    frac = 0.0 if r0 == r1 else (r0 - target) / (r0 - r1)
    return 2.0 * ((k - 1) + frac)


# =============================================================================
# Analysis of the simulated image
# =============================================================================

def _fundamental_amplitude(profile, period_pixels: float) -> float:
    """Amplitude of the fundamental at the given period along a 1D profile."""
    x = np.asarray(profile, dtype=float)
    n = x.size
    if n < 4 or period_pixels <= 0:
        return 0.0
    x = x - x.mean()
    idx = np.arange(n, dtype=float)
    c = np.sum(x * np.exp(-2j * np.pi * idx / period_pixels)) / n
    return float(2.0 * abs(c))


def bars_band_rows(size: int, index: int, count: int) -> range:
    """Row range of band ``index`` of a ``count``-band bar target."""
    band_h = max(1, size // max(1, count))
    r0 = index * band_h
    r1 = size if index == count - 1 else min(size, r0 + band_h)
    lo = r0 + max(1, (r1 - r0) // 4)
    hi = max(lo + 1, r0 + max(2, 3 * (r1 - r0) // 4))
    return range(lo, min(hi, size))


def mtf_from_bar_target(ideal, simulated, periods=(4, 8, 16, 32),
                        pixel_pitch: float = 5.0e-6) -> dict:
    """
    Measure the achieved MTF from a simulated bar target.

    Each band of the target is a square wave, so the ratio of the image
    fundamental amplitude to the object fundamental amplitude is the MTF at
    that spatial frequency.

    Args:
        ideal: The object pattern (bar chart) in image-plane pixels.
        simulated: The simulated image of the same pattern.
        periods: Band periods in pixels, matching :func:`test_target`.
        pixel_pitch: Sensor pixel pitch in meters, used to report the
            frequency in cycles/mm.

    Returns:
        Dict with "periods_pixels", "frequency_cyc_per_mm", "mtf",
        "object_modulation" and "image_modulation".
    """
    obj = np.asarray(ideal, dtype=float)
    img = np.asarray(simulated, dtype=float)
    if obj.shape != img.shape:
        raise ValueError("ideal and simulated must have the same shape")

    size = obj.shape[0]
    num = max(1, len(periods))
    freqs, mtfs, obj_mod, img_mod = [], [], [], []
    for i, p in enumerate(periods):
        rows = list(bars_band_rows(size, i, num))
        a_obj = float(np.mean([_fundamental_amplitude(obj[r], float(p))
                               for r in rows])) if rows else 0.0
        a_img = float(np.mean([_fundamental_amplitude(img[r], float(p))
                               for r in rows])) if rows else 0.0
        # period (pixels) -> period (mm) -> cycles/mm
        period_mm = float(p) * pixel_pitch * 1e3
        freqs.append(1.0 / period_mm if period_mm > 0 else 0.0)
        obj_mod.append(a_obj)
        img_mod.append(a_img)
        mtfs.append((a_img / a_obj) if a_obj > 1e-12 else 0.0)

    return {
        "periods_pixels": [float(p) for p in periods],
        "frequency_cyc_per_mm": freqs,
        "object_modulation": obj_mod,
        "image_modulation": img_mod,
        "mtf": mtfs,
    }


def image_quality_metrics(ideal, simulated,
                          period_pixels: Optional[float] = None) -> dict:
    """
    Compare a simulated image against the ideal object.

    Args:
        ideal: Ideal (object) image.
        simulated: Simulated image.
        period_pixels: Optional bar period for a targeted modulation
            measurement.

    Returns:
        Dict with "rmse", "psnr_db", "correlation", "contrast_ideal",
        "contrast_simulated" and, when ``period_pixels`` is given,
        "modulation_ideal", "modulation_simulated", "mtf_measured".
    """
    obj = np.asarray(ideal, dtype=float)
    img = np.asarray(simulated, dtype=float)
    if obj.shape != img.shape:
        raise ValueError("ideal and simulated must have the same shape")

    diff = img - obj
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    peak = float(np.max(np.abs(obj)))
    psnr = (20.0 * math.log10(peak / rmse)) if rmse > 1e-12 and peak > 0 else float("inf")

    obj_flat = obj.ravel()
    img_flat = img.ravel()
    so, si = float(np.std(obj_flat)), float(np.std(img_flat))
    if so > 1e-12 and si > 1e-12:
        corr = float(np.corrcoef(obj_flat, img_flat)[0, 1])
    else:
        corr = 1.0

    def _contrast(a):
        lo, hi = float(a.min()), float(a.max())
        return (hi - lo) / (hi + lo) if (hi + lo) > 1e-12 else 0.0

    out = {
        "rmse": rmse,
        "psnr_db": psnr,
        "correlation": corr,
        "contrast_ideal": _contrast(obj),
        "contrast_simulated": _contrast(img),
    }

    if period_pixels is not None and period_pixels > 0:
        rows = range(max(1, obj.shape[0] // 3), max(2, 2 * obj.shape[0] // 3))
        a_obj = float(np.mean([_fundamental_amplitude(obj[r], period_pixels)
                               for r in rows]))
        a_img = float(np.mean([_fundamental_amplitude(img[r], period_pixels)
                               for r in rows]))
        out["modulation_ideal"] = a_obj
        out["modulation_simulated"] = a_img
        out["mtf_measured"] = (a_img / a_obj) if a_obj > 1e-12 else 0.0

    return out


# =============================================================================
# Output helpers (no image library required)
# =============================================================================

def _to_uint8(image: np.ndarray, invert: bool = False,
              normalize: bool = True) -> np.ndarray:
    """Scale a float image to 8 bits, optionally stretching the range."""
    arr = np.asarray(image, dtype=float)
    if arr.ndim != 2:
        raise ValueError("expected a 2D image array")
    if normalize:
        lo, hi = float(arr.min()), float(arr.max())
        arr = (arr - lo) / (hi - lo) if hi > lo else np.zeros_like(arr)
    data = (np.clip(arr, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return (255 - data) if invert else data


def encode_png_gray(image: np.ndarray, invert: bool = False,
                    normalize: bool = True) -> bytes:
    """
    Encode a 2D array as an 8-bit greyscale PNG.

    Implemented with the standard library only (``zlib`` + ``struct``), so
    the simulator can write images without pulling in an image library.

    Args:
        image: 2D array of intensities.
        invert: Invert the greyscale (dark becomes bright).
        normalize: Stretch the array range to 0-255 before encoding.

    Returns:
        The PNG file contents as bytes.
    """
    data = _to_uint8(image, invert=invert, normalize=normalize)
    height, width = data.shape

    raw = bytearray()
    for row in data:
        raw.append(0)              # per-scanline filter: None
        raw.extend(row.tobytes())

    def _chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def save_png(path: str, image: np.ndarray, invert: bool = False,
             normalize: bool = True) -> str:
    """Write a 2D array to an 8-bit greyscale PNG; returns the path."""
    with open(path, "wb") as fh:
        fh.write(encode_png_gray(image, invert=invert, normalize=normalize))
    return path


def ascii_preview(image: np.ndarray, width: int = 56,
                  height: Optional[int] = None,
                  chars: str = " .:-=+*#%@") -> str:
    """
    Render a 2D array as ASCII art for terminal inspection.

    Terminal cells are roughly twice as tall as they are wide, so the
    default height is half the width scaled by the aspect ratio.
    """
    arr = np.asarray(image, dtype=float)
    if arr.ndim != 2:
        raise ValueError("ascii_preview expects a 2D array")
    h, w = arr.shape
    width = max(4, int(width))
    if height is None:
        height = max(2, int(round(width * (h / max(w, 1)) * 0.5)))
    height = max(1, int(height))

    lo, hi = float(arr.min()), float(arr.max())
    span = (hi - lo) if hi > lo else 1.0
    ys = np.linspace(0, h, height + 1).astype(int)
    xs = np.linspace(0, w, width + 1).astype(int)
    last = len(chars) - 1

    lines = []
    for i in range(height):
        y0, y1 = ys[i], max(ys[i] + 1, ys[i + 1])
        row = []
        for j in range(width):
            x0, x1 = xs[j], max(xs[j] + 1, xs[j + 1])
            block = arr[y0:y1, x0:x1]
            v = float(block.mean()) if block.size else 0.0
            k = int(round((v - lo) / span * last))
            row.append(chars[max(0, min(last, k))])
        lines.append("".join(row))
    return "\n".join(lines)


def image_statistics(image: np.ndarray) -> dict:
    """Basic statistics of an image array."""
    arr = np.asarray(image, dtype=float)
    return {
        "shape": list(arr.shape),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
    }
