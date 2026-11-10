"""
Gaussian beam propagation through the prescription (paraxial, in the
spirit of Code V's beam synthesis for well-behaved beams).

The system's ray-transfer matrix from its first surface to its image plane
comes from two paraxial traces (y, u) = (1, 0) and (0, 1) of the
engine's own paraxial ray trace, so it includes every thickness, curvature,
index, mirror and ideal lens of the prescription exactly. The beam's
complex parameter q = z + i z_R (z_R = pi w0^2 / (M^2 lambda), M^2 the beam
quality) goes through it as q' = (A q + B) / (C q + D) (H. Kogelnik and
T. Li, Appl. Opt. 5, 1550 (1966); A. E. Siegman, Lasers, ch. 20), giving
the output waist's size and position and the beam radius anywhere after
the system. Object and image space are taken as air.

This is the paraxial (ABCD) model: it ignores aberrations and truncation
by apertures, which a diffraction propagation would include.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from . import raytrace as rt
from .models import OpticalSystem


def system_matrix(system: OpticalSystem, wavelength: Optional[float] = None):
    """(A, B, C, D) from the first surface's vertex plane to the image plane
    (lengths in m, angles as slopes), along the light."""
    seq = rt.build_sequence(system, wavelength)
    rows = []
    for y0, u0 in ((1.0, 0.0), (0.0, 1.0)):
        r = rt.paraxial_trace(seq, y0, u0)
        last = seq.surfaces[-1]
        u = r.u_after[-1]
        # from the last surface to the image plane, along the travel
        d = (seq.image_z - last.z) * last.direction
        rows.append((r.y[-1] + u * d, u))
    (A, C), (B, D) = rows
    return A, B, C, D


def beam_through(
    system: OpticalSystem,
    waist_radius: float,
    waist_distance: float,
    wavelength: Optional[float] = None,
    m2: float = 1.0,
    samples: int = 101,
) -> dict:
    """
    A beam with waist ``waist_radius`` (1/e^2 radius, m) a distance
    ``waist_distance`` in front of the first surface (negative: behind it,
    a converging input) through the system.

    Returns the output waist radius and its position from the image plane
    (along the light; negative = before it), the beam radius and wavefront
    radius at the image plane, the output Rayleigh range and divergence, and
    the beam radius along the axis around the output waist.
    """
    wl = wavelength or system.analysis_settings.wavelength
    if waist_radius <= 0 or m2 < 1:
        raise ValueError("The waist radius must be positive and M^2 at least 1")
    zr = math.pi * waist_radius**2 / (m2 * wl)
    q_in = complex(waist_distance, zr)
    A, B, C, D = system_matrix(system, wl)
    q = (A * q_in + B) / (C * q_in + D)
    zr_out = q.imag
    if zr_out <= 0:
        raise ValueError("The beam does not propagate through the system")
    w0_out = math.sqrt(zr_out * m2 * wl / math.pi)
    z_waist = -q.real  # the waist lies this far after the image plane
    w_img = w0_out * math.sqrt(1 + (q.real / zr_out) ** 2)
    R_img = q.real * (1 + (zr_out / q.real) ** 2) if q.real else math.inf
    span = max(3 * zr_out, abs(z_waist) * 1.2, 1e-6)
    z = np.linspace(z_waist - span, z_waist + span, int(samples))
    w = w0_out * np.sqrt(1 + ((z - z_waist) / zr_out) ** 2)
    return {
        "wavelength": wl,
        "m2": m2,
        "matrix": [A, B, C, D],
        "waist_radius": w0_out,
        "waist_position": z_waist,
        "rayleigh_range": zr_out,
        "divergence": m2 * wl / (math.pi * w0_out),
        "beam_radius_at_image": w_img,
        "wavefront_radius_at_image": R_img,
        "z": z.tolist(),
        "beam_radius": w.tolist(),
    }
