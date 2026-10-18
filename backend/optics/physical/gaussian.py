"""
Gaussian beam propagation.

Convention: a :class:`GaussianBeam` is described in a fixed global frame;
``position`` is the z coordinate of its waist. The complex beam parameter at
a plane z is q(z) = (z - position) + i z_R. Optical elements are placed at
explicit z positions. For M^2 > 1 the embedded-Gaussian model is used:
z_R = pi w0^2 / (M^2 lambda).

Implements:
- Complex beam parameter (q-parameter)
- Free space propagation
- Lens transformation
- Beam waist tracking
- M² factor calculation
- ABCD matrix method
"""

from typing import Optional, Union
from dataclasses import dataclass
import numpy as np
from numpy import pi, sqrt, exp, angle, abs, conj


@dataclass
class BeamParameter:
    """Complex beam parameter q = z + i*z_R."""
    q: complex  # Complex beam parameter
    wavelength: float = 550e-9  # m
    
    @property
    def z(self) -> float:
        """Distance from waist."""
        return self.q.real
    
    @property
    def z_R(self) -> float:
        """Rayleigh range."""
        return self.q.imag
    
    @property
    def w0(self) -> float:
        """Beam waist radius."""
        return sqrt(self.wavelength * self.z_R / pi)
    
    @property
    def w(self) -> float:
        """Beam radius at current position."""
        return self.w0 * sqrt(1 + (self.z / self.z_R)**2)
    
    @property
    def R(self) -> float:
        """Radius of curvature."""
        if abs(self.z) < 1e-15:
            return float('inf')
        return self.z * (1 + (self.z_R / self.z)**2)
    
    @property
    def divergence(self) -> float:
        """Half-angle divergence."""
        return self.wavelength / (pi * self.w0)
    
    @property
    def gouy_phase(self) -> float:
        """Gouy phase."""
        return np.arctan2(self.z, self.z_R)
    
    @classmethod
    def from_waist(cls, w0: float, wavelength: float = 550e-9, z: float = 0) -> 'BeamParameter':
        """Create beam parameter from waist size."""
        z_R = pi * w0**2 / wavelength
        q = complex(z, z_R)
        return cls(q=q, wavelength=wavelength)
    
    @classmethod
    def from_beam_radius(cls, w: float, R: float, wavelength: float = 550e-9) -> 'BeamParameter':
        """Create beam parameter from beam radius and curvature."""
        # 1/q = 1/R - i*lambda/(pi*w^2)
        inv_q = 1/R - 1j * wavelength / (pi * w**2)
        q = 1 / inv_q
        return cls(q=q, wavelength=wavelength)


@dataclass
class GaussianBeam:
    """Complete Gaussian beam description."""
    w0: float  # Beam waist radius (m)
    wavelength: float = 550e-9  # Wavelength (m)
    M2: float = 1.0  # Beam quality factor
    position: float = 0.0  # Waist position (m)
    power: float = 1.0  # Beam power (W)
    
    def __post_init__(self):
        self.z_R = pi * self.w0**2 / (self.wavelength * self.M2)
    
    def beam_radius(self, z: float) -> float:
        """Calculate beam radius at position z."""
        dz = z - self.position
        return self.w0 * sqrt(1 + (dz / self.z_R)**2)
    
    def curvature(self, z: float) -> float:
        """Calculate radius of curvature at position z."""
        dz = z - self.position
        if abs(dz) < 1e-15:
            return float('inf')
        return dz * (1 + (self.z_R / dz)**2)
    
    def divergence(self) -> float:
        """Calculate half-angle divergence."""
        return self.M2 * self.wavelength / (pi * self.w0)
    
    def intensity(self, z: float, r: float) -> float:
        """Calculate intensity at (z, r)."""
        w = self.beam_radius(z)
        I0 = 2 * self.power / (pi * w**2)
        return I0 * exp(-2 * r**2 / w**2)
    
    def copy(self) -> 'GaussianBeam':
        """Create a copy of this beam."""
        return GaussianBeam(
            w0=self.w0,
            wavelength=self.wavelength,
            M2=self.M2,
            position=self.position,
            power=self.power
        )


@dataclass
class ABCDMatrix:
    """ABCD ray transfer matrix."""
    A: float = 1.0
    B: float = 0.0
    C: float = 0.0
    D: float = 1.0
    
    def __matmul__(self, other: 'ABCDMatrix') -> 'ABCDMatrix':
        """Matrix multiplication."""
        return ABCDMatrix(
            A=self.A * other.A + self.B * other.C,
            B=self.A * other.B + self.B * other.D,
            C=self.C * other.A + self.D * other.C,
            D=self.C * other.B + self.D * other.D
        )
    
    def transform_q(self, q: complex) -> complex:
        """Transform beam parameter through this matrix."""
        return (self.A * q + self.B) / (self.C * q + self.D)
    
    @classmethod
    def free_space(cls, d: float) -> 'ABCDMatrix':
        """Free space propagation matrix."""
        return cls(A=1, B=d, C=0, D=1)
    
    @classmethod
    def thin_lens(cls, f: float) -> 'ABCDMatrix':
        """Thin lens matrix."""
        return cls(A=1, B=0, C=-1/f, D=1)
    
    @classmethod
    def flat_interface(cls, n1: float = 1.0, n2: float = 1.5) -> 'ABCDMatrix':
        """Flat refractive interface."""
        return cls(A=1, B=0, C=0, D=n1/n2)
    
    @classmethod
    def curved_interface(cls, R: float, n1: float = 1.0, n2: float = 1.5) -> 'ABCDMatrix':
        """Curved refractive interface."""
        return cls(A=1, B=0, C=(n1-n2)/(n2*R), D=n1/n2)
    
    @classmethod
    def thick_lens(cls, R1: float, R2: float, t: float, n: float) -> 'ABCDMatrix':
        """Thick lens matrix."""
        M1 = cls.curved_interface(R1, 1.0, n)
        M2 = cls.free_space(t)
        M3 = cls.curved_interface(R2, n, 1.0)
        return M3 @ M2 @ M1


def free_space_propagation(beam: GaussianBeam, d: float) -> GaussianBeam:
    """
    Translate the beam by ``d`` along z (its waist moves from z0 to z0 + d).

    In the fixed global frame free-space propagation does not change a beam;
    this helper re-positions it, which is equivalent to moving every element
    by -d. Evaluate the beam at any plane with :meth:`GaussianBeam.beam_radius`.
    """
    new_beam = beam.copy()
    new_beam.position = beam.position + d
    return new_beam


def _beam_from_q(q: complex, z_plane: float, beam: GaussianBeam) -> GaussianBeam:
    """Beam whose parameter at z_plane is q (same wavelength, M^2, power)."""
    z_r = q.imag
    if z_r <= 0:
        raise ValueError("Invalid beam parameter (non-positive Rayleigh range)")
    w0 = sqrt(beam.M2 * beam.wavelength * z_r / pi)
    return GaussianBeam(w0=w0, wavelength=beam.wavelength, M2=beam.M2,
                        position=z_plane - q.real, power=beam.power)


def lens_transform(beam: GaussianBeam, f: float, lens_position: float = 0.0) -> GaussianBeam:
    """
    Transform a beam by a thin lens of focal length f located at
    ``lens_position``: q' = q / (1 - q / f) at the lens.
    """
    q = complex(lens_position - beam.position, beam.z_R)
    q_new = ABCDMatrix.thin_lens(f).transform_q(q)
    return _beam_from_q(q_new, lens_position, beam)


def propagate_beam(beam: GaussianBeam, elements: list, start: float = 0.0) -> GaussianBeam:
    """
    Propagate a beam through a sequence of elements, starting at the plane
    z = ``start``:

        ('free_space', d)          advance the reference plane by d
        ('lens', f)                thin lens at the current plane
        ('interface', n1, n2, R)   refracting surface at the current plane

    Inside a medium of index n the beam parameter uses the reduced
    wavelength lambda/n; the returned beam is described in the final medium
    with its waist position in the global frame.
    """
    z = start
    n = 1.0
    q = complex(z - beam.position, beam.z_R)
    for elem_type, *params in elements:
        if elem_type == "free_space":
            q = q + params[0]
            z += params[0]
        elif elem_type == "lens":
            q = ABCDMatrix.thin_lens(params[0]).transform_q(q)
        elif elem_type == "interface":
            n1, n2, R = params
            # q / n is invariant in form: transform the reduced parameter
            M = (ABCDMatrix.flat_interface(n1, n2) if not np.isfinite(R) or R == 0
                 else ABCDMatrix.curved_interface(R, n1, n2))
            q = M.transform_q(q)
            n = n2
        else:
            raise ValueError(f"Unknown element '{elem_type}'")
    out = _beam_from_q(q, z, beam) if n == 1.0 else None
    if out is None:
        # in a medium: Rayleigh range z_R = pi w0^2 n / (M^2 lambda)
        w0 = sqrt(beam.M2 * beam.wavelength * q.imag / (pi * n))
        out = GaussianBeam(w0=w0, wavelength=beam.wavelength / n, M2=beam.M2,
                           position=z - q.real, power=beam.power)
    return out


def calculate_M2(beam_radii: list, positions: list, wavelength: float = 550e-9) -> float:
    """
    M^2 from beam radii measured along z (ISO 11146 style hyperbolic fit).

    Fits w^2(z) = a + b z + c z^2; then w0^2 = a - b^2/(4c) and
    M^2 = (pi / lambda) sqrt(w0^2 c). Needs at least three measurements
    spanning the waist; raises ValueError otherwise.
    """
    z = np.asarray(positions, dtype=float)
    w2 = np.asarray(beam_radii, dtype=float) ** 2
    if len(z) < 3:
        raise ValueError("At least three beam-radius measurements are needed")
    c, b, a = np.polyfit(z, w2, 2)
    if c <= 0:
        raise ValueError("Measurements do not describe a beam waist (curvature <= 0)")
    w0_sq = a - b * b / (4.0 * c)
    if w0_sq <= 0:
        raise ValueError("Fit gives a non-positive waist")
    return float(pi / wavelength * np.sqrt(w0_sq * c))
