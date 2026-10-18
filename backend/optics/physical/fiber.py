"""
Fiber coupling.

- Single-mode fibre: the fundamental mode is approximated by a Gaussian of
  radius w_f from Marcuse's formula for a step-index fibre,
  w_f / a = 0.65 + 1.619 V^-1.5 + 2.879 V^-6 (D. Marcuse, Bell Syst. Tech.
  J. 56, 703 (1977); accurate for 0.8 < V < 2.5). The coupling efficiency
  is the normalised overlap integral |<E_beam|E_fibre>|^2 of the incident
  TEM00 field (with its size, wavefront curvature, lateral offset and tilt
  at the fibre face) and the mode, evaluated numerically.
- Multimode fibre: geometric acceptance, the fraction of the beam's power
  falling on the core times the fraction of its angular spectrum inside
  the acceptance cone asin(NA). Fresnel losses are not included.

Lengths in meters, angles in radians.
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

from .gaussian import GaussianBeam, lens_transform


@dataclass
class Fiber:
    """Step-index fibre."""
    name: str = "Fiber"
    core_radius: float = 4.1e-6        # m (Corning SMF-28: 8.2 um core)
    cladding_radius: float = 62.5e-6   # m
    NA: float = 0.14                   # (SMF-28 nominal)
    length: float = 1.0
    wavelength: float = 1550e-9

    @property
    def V_number(self) -> float:
        return 2.0 * math.pi * self.core_radius * self.NA / self.wavelength

    @property
    def is_single_mode(self) -> bool:
        """Single-mode below the LP11 cutoff V = 2.405."""
        return self.V_number < 2.405


@dataclass
class SingleModeFiber(Fiber):
    """Single-mode step-index fibre."""
    mode_field_radius: float = field(init=False, default=0.0)

    def __post_init__(self):
        V = self.V_number
        if not 0.8 <= V <= 2.5:
            raise ValueError(f"V = {V:.3f} is outside the range of Marcuse's mode-size "
                             "formula (0.8-2.5); the fibre is not single-mode here")
        self.mode_field_radius = self.core_radius * (0.65 + 1.619 / V ** 1.5 + 2.879 / V ** 6)

    @property
    def mode_field_diameter(self) -> float:
        return 2.0 * self.mode_field_radius

    def mode_field(self, z: float = 0.0) -> GaussianBeam:
        """The mode as a Gaussian beam with its waist at the fibre face z."""
        return GaussianBeam(w0=self.mode_field_radius, wavelength=self.wavelength,
                            M2=1.0, position=z)


@dataclass
class MultiModeFiber(Fiber):
    """Multimode step-index fibre."""
    core_radius: float = 25e-6
    NA: float = 0.22

    @property
    def num_modes(self) -> int:
        """Approximate number of guided modes of a step-index fibre, V^2/2."""
        return int(self.V_number ** 2 / 2)

    @property
    def etendue(self) -> float:
        """Etendue of the core and acceptance cone, pi * A * NA^2 (m^2 sr)."""
        return math.pi * (math.pi * self.core_radius ** 2) * self.NA ** 2


def _overlap(w, R, w_f, wavelength, dx, theta) -> float:
    """Normalised overlap of a Gaussian beam (radius w, curvature R, offset dx,
    tilt theta about y) with a flat Gaussian mode of radius w_f."""
    k = 2.0 * math.pi / wavelength
    ext = 4.0 * max(w, w_f) + abs(dx)
    n = 401
    x = np.linspace(-ext, ext, n)
    X, Y = np.meshgrid(x, x)
    r2 = (X - dx) ** 2 + Y ** 2
    phase = -k * r2 / (2.0 * R) if math.isfinite(R) else 0.0
    Eb = np.exp(-r2 / w ** 2) * np.exp(1j * (phase + k * math.sin(theta) * X))
    Ef = np.exp(-(X ** 2 + Y ** 2) / w_f ** 2)
    num = abs(np.sum(Eb * Ef)) ** 2
    den = np.sum(abs(Eb) ** 2) * np.sum(Ef ** 2)
    return float(num / den)


def _gaussian_power_in_circle(w: float, a: float, d: float) -> float:
    """Fraction of a Gaussian beam's power (1/e^2 radius w) inside a circle
    of radius a whose centre is offset by d from the beam."""
    n = 401
    ext = max(a, 3 * w) + abs(d)
    x = np.linspace(-ext, ext, n)
    X, Y = np.meshgrid(x, x)
    I = np.exp(-2.0 * ((X - d) ** 2 + Y ** 2) / w ** 2)
    inside = X ** 2 + Y ** 2 <= a * a
    return float(I[inside].sum() / (math.pi * w * w / 2.0) * (x[1] - x[0]) ** 2)


def _beam_at_face(beam, fiber, lens_focal_length, defocus):
    if lens_focal_length:
        beam = lens_transform(beam, lens_focal_length, 0.0)
    z_face = beam.position + defocus      # fibre face at the beam waist plus defocus
    return beam, beam.beam_radius(z_face), beam.curvature(z_face)


def coupling_efficiency(beam: GaussianBeam, fiber: Fiber,
                        lens_focal_length: Optional[float] = None,
                        lateral_offset: float = 0.0, angular_misalignment: float = 0.0,
                        defocus: float = 0.0) -> float:
    """
    Power coupling efficiency (0..1) of a beam into a fibre whose face sits
    at the beam's waist (after the optional focusing lens) plus ``defocus``.
    """
    if beam.wavelength != fiber.wavelength:
        raise ValueError("Beam and fibre wavelengths differ")
    b, w, R = _beam_at_face(beam, fiber, lens_focal_length, defocus)
    if isinstance(fiber, SingleModeFiber):
        if beam.M2 != 1.0:
            raise ValueError("Single-mode coupling is defined here for a TEM00 beam (M^2 = 1)")
        return _overlap(w, R, fiber.mode_field_radius, fiber.wavelength,
                        lateral_offset, angular_misalignment)
    # multimode: spatial and angular acceptance
    spatial = _gaussian_power_in_circle(w, fiber.core_radius, lateral_offset)
    theta0 = b.divergence()                         # 1/e^2 half-angle
    accept = math.asin(min(1.0, fiber.NA))
    angular = _gaussian_power_in_circle(theta0, accept, angular_misalignment)
    return max(0.0, min(1.0, spatial * angular))


def alignment_sensitivity(beam: GaussianBeam, fiber: Fiber, scan_range: float = 10e-6,
                          num_points: int = 51, lens_focal_length: Optional[float] = None,
                          angle_range: float = 0.01) -> dict:
    """Coupling versus lateral offset, tilt and defocus, with the offsets at
    which the coupling falls 1, 3 and 5 dB below its peak."""
    offsets = np.linspace(-scan_range, scan_range, num_points)
    angles = np.linspace(-angle_range, angle_range, num_points)
    lateral = [coupling_efficiency(beam, fiber, lens_focal_length, float(o)) for o in offsets]
    angular = [coupling_efficiency(beam, fiber, lens_focal_length, 0.0, float(a)) for a in angles]
    defoc = [coupling_efficiency(beam, fiber, lens_focal_length, 0.0, 0.0, float(d)) for d in offsets]

    def tol(values, xs, db):
        peak = max(values)
        lim = peak * 10 ** (-db / 10.0)
        i0 = int(np.argmax(values))
        for i in range(i0, len(values)):
            if values[i] < lim:
                # linear interpolation between samples
                x0, x1, v0, v1 = xs[i - 1], xs[i], values[i - 1], values[i]
                return float(abs(x0 + (lim - v0) * (x1 - x0) / (v1 - v0)))
        return None   # not reached within the scan

    return {
        "lateral_offsets": offsets.tolist(), "lateral_efficiency": lateral,
        "angular_offsets": angles.tolist(), "angular_efficiency": angular,
        "defocus_offsets": offsets.tolist(), "defocus_efficiency": defoc,
        "peak_efficiency": max(lateral),
        "1dB_lateral_tolerance": tol(lateral, offsets, 1),
        "3dB_lateral_tolerance": tol(lateral, offsets, 3),
        "5dB_lateral_tolerance": tol(lateral, offsets, 5),
    }


def optimal_coupling_lens(beam: GaussianBeam, fiber: Fiber,
                          available_focal_lengths: list) -> Tuple[float, float]:
    """Focal length (from those given) with the highest coupling efficiency."""
    if not available_focal_lengths:
        raise ValueError("No focal lengths given")
    best_f, best = float(available_focal_lengths[0]), -1.0
    for f in available_focal_lengths:
        eff = coupling_efficiency(beam, fiber, f)
        if eff > best:
            best, best_f = eff, f
    return best_f, best
