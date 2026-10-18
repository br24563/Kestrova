"""Advanced Surface Types for Sequential Optical Design.

Provides professional-grade surface types that go beyond simple spheres.
All values are in SI base units (meters, radians).
"""

import math
from typing import Optional, Literal
from pydantic import Field

import numpy as np

from .base import OpticalComponentBase
from .materials import refractive_index

# =============================================================================
# Aspheric Surface Types
# =============================================================================


class AsphericSurface(OpticalComponentBase):
    """Even aspheric surface for sequential ray tracing.

    Sag equation:
        z(r) = r^2/(R(1+sqrt(1-(1+k)r^2/R^2))) + sum(A_i * r^(2i))
    """

    type: Literal["aspheric"] = "aspheric"
    radius: float = 0.1
    conic: float = 0.0
    aspheric_coeffs: list[float] = Field(default_factory=list)
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0

    def sag(self, r: float) -> float:
        """Calculate sag at radial distance r from optical axis."""
        R, k = self.radius, self.conic
        r_sq = r * r
        if abs(R) < 1e-15:
            z = 0.0
        else:
            disc = 1.0 - (1.0 + k) * r_sq / (R * R)
            z = r_sq / (R * (1.0 + math.sqrt(max(0, disc)))) if disc >= 0 else 0.0
        for i, A in enumerate(self.aspheric_coeffs):
            z += A * r ** (2 * (i + 2))
        return z

    def sag_derivative(self, r: float) -> float:
        """Calculate dz/dr."""
        dr = 1e-8
        return (self.sag(r + dr) - self.sag(r - dr)) / (2.0 * dr)

    def normal_at(self, r: float) -> tuple[float, float]:
        """Returns (nz, ny) unit normal vector."""
        dz_dr = self.sag_derivative(r)
        norm = math.sqrt(1.0 + dz_dr * dz_dr)
        return 1.0 / norm, -dz_dr / norm

    def intersect(
        self, z0: float, y0: float, dz: float, dy: float
    ) -> Optional[tuple[float, float]]:
        """Find intersection using Newton method."""
        t = (self.position - z0) / dz if abs(dz) > 1e-15 else 0.0
        for _ in range(100):
            z, y = z0 + t * dz, y0 + t * dy
            r = abs(y)
            if r > self.aperture_diameter / 2.0:
                return None
            error = z - (self.position + self.sag(r))
            if abs(error) < 1e-12:
                return z, y
            dz_dr = self.sag_derivative(r)
            dr_dt = (y * dy) / max(r, 1e-15) if r > 1e-15 else 0.0
            de_dt = dz - dz_dr * dr_dt
            if abs(de_dt) < 1e-15:
                break
            t -= error / de_dt
        return None


class OddAsphericSurface(OpticalComponentBase):
    """Odd aspheric surface with additional odd-power terms."""

    type: Literal["odd_aspheric"] = "odd_aspheric"
    radius: float = 0.1
    conic: float = 0.0
    aspheric_coeffs: list[float] = Field(default_factory=list)
    odd_coeffs: list[float] = Field(default_factory=list)
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0

    def sag(self, r: float) -> float:
        R, k = self.radius, self.conic
        r_sq = r * r
        if abs(R) < 1e-15:
            z = 0.0
        else:
            disc = 1.0 - (1.0 + k) * r_sq / (R * R)
            z = r_sq / (R * (1.0 + math.sqrt(max(0, disc)))) if disc >= 0 else 0.0
        for i, A in enumerate(self.aspheric_coeffs):
            z += A * r ** (2 * (i + 2))
        for i, B in enumerate(self.odd_coeffs):
            z += B * r ** (2 * i + 1)
        return z

    def sag_derivative(self, r: float) -> float:
        dr = 1e-8
        return (self.sag(r + dr) - self.sag(r - dr)) / (2.0 * dr)

    def normal_at(self, r: float) -> tuple[float, float]:
        dz_dr = self.sag_derivative(r)
        norm = math.sqrt(1.0 + dz_dr * dz_dr)
        return 1.0 / norm, -dz_dr / norm

    def intersect(
        self, z0: float, y0: float, dz: float, dy: float
    ) -> Optional[tuple[float, float]]:
        t = (self.position - z0) / dz if abs(dz) > 1e-15 else 0.0
        for _ in range(100):
            z, y = z0 + t * dz, y0 + t * dy
            r = abs(y)
            if r > self.aperture_diameter / 2.0:
                return None
            error = z - (self.position + self.sag(r))
            if abs(error) < 1e-12:
                return z, y
            dz_dr = self.sag_derivative(r)
            dr_dt = (y * dy) / max(r, 1e-15) if r > 1e-15 else 0.0
            de_dt = dz - dz_dr * dr_dt
            if abs(de_dt) < 1e-15:
                break
            t -= error / de_dt
        return None


class QAsphericSurface(OpticalComponentBase):
    """Q-type aspheric surface for better optimization behavior."""

    type: Literal["q_aspheric"] = "q_aspheric"
    radius: float = 0.1
    conic: float = 0.0
    q_type: str = "Qbfs"
    coefficients: list[float] = Field(default_factory=list)
    norm_radius: float = 0.025
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0

    def sag(self, r: float) -> float:
        R, k = self.radius, self.conic
        r_sq = r * r
        if abs(R) < 1e-15:
            return 0.0
        disc = 1.0 - (1.0 + k) * r_sq / (R * R)
        if disc < 0:
            return 0.0
        sqrt_term = math.sqrt(disc)
        z = r_sq / (R * (1.0 + sqrt_term))
        u_sq = r_sq / (R * R * (1.0 + sqrt_term) ** 2)
        nr = self.norm_radius
        for i, c in enumerate(self.coefficients):
            if self.q_type == "Qbfs":
                z += (c / nr) * u_sq ** (i + 1)
            else:
                z += c * (r / nr) ** (2 * (i + 1))
        return z

    def sag_derivative(self, r: float) -> float:
        dr = 1e-8
        return (self.sag(r + dr) - self.sag(r - dr)) / (2.0 * dr)

    def normal_at(self, r: float) -> tuple[float, float]:
        dz_dr = self.sag_derivative(r)
        norm = math.sqrt(1.0 + dz_dr * dz_dr)
        return 1.0 / norm, -dz_dr / norm

    def intersect(
        self, z0: float, y0: float, dz: float, dy: float
    ) -> Optional[tuple[float, float]]:
        t = (self.position - z0) / dz if abs(dz) > 1e-15 else 0.0
        for _ in range(100):
            z, y = z0 + t * dz, y0 + t * dy
            r = abs(y)
            if r > self.aperture_diameter / 2.0:
                return None
            error = z - (self.position + self.sag(r))
            if abs(error) < 1e-12:
                return z, y
            dz_dr = self.sag_derivative(r)
            dr_dt = (y * dy) / max(r, 1e-15) if r > 1e-15 else 0.0
            de_dt = dz - dz_dr * dr_dt
            if abs(de_dt) < 1e-15:
                break
            t -= error / de_dt
        return None


class ZernikeSurface(OpticalComponentBase):
    """Zernike polynomial surface for freeform wavefront correction."""

    type: Literal["zernike"] = "zernike"
    zernike_coeffs: list[float] = Field(default_factory=list)
    norm_radius: float = 0.025
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0

    def sag(self, r: float) -> float:
        from .zernike import zernike_standard

        rho = r / self.norm_radius if self.norm_radius > 1e-15 else 0.0
        if rho > 1.0:
            return 0.0
        z = 0.0
        theta = 0.0
        for i, coeff in enumerate(self.zernike_coeffs):
            z += coeff * float(
                zernike_standard(i + 1, np.array([rho]), np.array([theta]))[0]
            )
        return z

    def sag_derivative(self, r: float) -> float:
        dr = 1e-8
        return (self.sag(r + dr) - self.sag(r - dr)) / (2.0 * dr)

    def normal_at(self, r: float) -> tuple[float, float]:
        dz_dr = self.sag_derivative(r)
        norm = math.sqrt(1.0 + dz_dr * dz_dr)
        return 1.0 / norm, -dz_dr / norm

    def intersect(
        self, z0: float, y0: float, dz: float, dy: float
    ) -> Optional[tuple[float, float]]:
        t = (self.position - z0) / dz if abs(dz) > 1e-15 else 0.0
        for _ in range(100):
            z, y = z0 + t * dz, y0 + t * dy
            r = abs(y)
            if r > self.aperture_diameter / 2.0:
                return None
            error = z - (self.position + self.sag(r))
            if abs(error) < 1e-12:
                return z, y
            dz_dr = self.sag_derivative(r)
            dr_dt = (y * dy) / max(r, 1e-15) if r > 1e-15 else 0.0
            de_dt = dz - dz_dr * dr_dt
            if abs(de_dt) < 1e-15:
                break
            t -= error / de_dt
        return None


class DiffractiveOpticalElement(OpticalComponentBase):
    """Diffractive Optical Element (DOE) surface."""

    type: Literal["doe"] = "doe"
    doe_type: str = "kinoform"
    design_wavelength: float = 550e-9
    diffraction_order: int = 1
    phase_coeffs: list[float] = Field(default_factory=list)
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0

    def phase(self, r: float) -> float:
        r_sq = r * r
        phi = 0.0
        for i, c in enumerate(self.phase_coeffs):
            phi += c * r_sq ** (i + 1)
        return phi

    def sag(self, r: float) -> float:
        if self.doe_type == "binary":
            return self._binary_sag(r)
        elif self.doe_type == "kinoform":
            return self._kinoform_sag(r)
        return self._holographic_sag(r)

    def _binary_sag(self, r: float) -> float:
        phi = self.phase(r)
        step = self.design_wavelength / 4.0
        return step * round(phi / (2 * math.pi)) if step > 0 else 0.0

    def _kinoform_sag(self, r: float) -> float:
        phi = self.phase(r)
        m = self.diffraction_order
        wl = self.design_wavelength
        n = refractive_index(self.material, self.design_wavelength)
        return (m * wl * phi / (2 * math.pi * (n - 1))) if abs(n - 1) > 1e-10 else 0.0

    def _holographic_sag(self, r: float) -> float:
        return self._kinoform_sag(r)

    def sag_derivative(self, r: float) -> float:
        dr = 1e-8
        return (self.sag(r + dr) - self.sag(r - dr)) / (2.0 * dr)

    def normal_at(self, r: float) -> tuple[float, float]:
        dz_dr = self.sag_derivative(r)
        norm = math.sqrt(1.0 + dz_dr * dz_dr)
        return 1.0 / norm, -dz_dr / norm

    def intersect(
        self, z0: float, y0: float, dz: float, dy: float
    ) -> Optional[tuple[float, float]]:
        t = (self.position - z0) / dz if abs(dz) > 1e-15 else 0.0
        for _ in range(100):
            z, y = z0 + t * dz, y0 + t * dy
            r = abs(y)
            if r > self.aperture_diameter / 2.0:
                return None
            error = z - (self.position + self.sag(r))
            if abs(error) < 1e-12:
                return z, y
            dz_dr = self.sag_derivative(r)
            dr_dt = (y * dy) / max(r, 1e-15) if r > 1e-15 else 0.0
            de_dt = dz - dz_dr * dr_dt
            if abs(de_dt) < 1e-15:
                break
            t -= error / de_dt
        return None


class ToricSurface(OpticalComponentBase):
    """Toric/Cylindrical surface for astigmatism correction."""

    type: Literal["toric"] = "toric"
    radius_tangential: float = 0.1
    radius_sagittal: float = 0.1
    conic: float = 0.0
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0

    def sag(self, r: float) -> float:
        R, k = self.radius_tangential, self.conic
        r_sq = r * r
        if abs(R) < 1e-15:
            return 0.0
        disc = 1.0 - (1.0 + k) * r_sq / (R * R)
        return r_sq / (R * (1.0 + math.sqrt(max(0, disc)))) if disc >= 0 else 0.0

    def sag_derivative(self, r: float) -> float:
        dr = 1e-8
        return (self.sag(r + dr) - self.sag(r - dr)) / (2.0 * dr)

    def normal_at(self, r: float) -> tuple[float, float]:
        dz_dr = self.sag_derivative(r)
        norm = math.sqrt(1.0 + dz_dr * dz_dr)
        return 1.0 / norm, -dz_dr / norm

    def intersect(
        self, z0: float, y0: float, dz: float, dy: float
    ) -> Optional[tuple[float, float]]:
        t = (self.position - z0) / dz if abs(dz) > 1e-15 else 0.0
        for _ in range(100):
            z, y = z0 + t * dz, y0 + t * dy
            r = abs(y)
            if r > self.aperture_diameter / 2.0:
                return None
            error = z - (self.position + self.sag(r))
            if abs(error) < 1e-12:
                return z, y
            dz_dr = self.sag_derivative(r)
            dr_dt = (y * dy) / max(r, 1e-15) if r > 1e-15 else 0.0
            de_dt = dz - dz_dr * dr_dt
            if abs(de_dt) < 1e-15:
                break
            t -= error / de_dt
        return None


class CoordinateBreak(OpticalComponentBase):
    """Coordinate break for decenter and tilt."""

    type: Literal["coordinate_break"] = "coordinate_break"
    decenter_x: float = 0.0
    decenter_y: float = 0.0
    decenter_z: float = 0.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    tilt_z: float = 0.0
    order: str = "decenter_then_tilt"

    def apply(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        if self.order == "decenter_then_tilt":
            x -= self.decenter_x
            y -= self.decenter_y
            x, y, z = self._apply_tilt(x, y, z)
        else:
            x, y, z = self._apply_tilt(x, y, z)
            x -= self.decenter_x
            y -= self.decenter_y
        return x, y, z

    def _apply_tilt(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        tx, ty, tz = self.tilt_x, self.tilt_y, self.tilt_z
        if abs(tx) > 1e-15:
            cos_tx, sin_tx = math.cos(tx), math.sin(tx)
            y, z = y * cos_tx - z * sin_tx, y * sin_tx + z * cos_tx
        if abs(ty) > 1e-15:
            cos_ty, sin_ty = math.cos(ty), math.sin(ty)
            x, z = x * cos_ty + z * sin_ty, -x * sin_ty + z * cos_ty
        if abs(tz) > 1e-15:
            cos_tz, sin_tz = math.cos(tz), math.sin(tz)
            x, y = x * cos_tz - y * sin_tz, x * sin_tz + y * cos_tz
        return x, y, z

    def reverse(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        if self.order == "decenter_then_tilt":
            x, y, z = self._reverse_tilt(x, y, z)
            x += self.decenter_x
            y += self.decenter_y
        else:
            x += self.decenter_x
            y += self.decenter_y
            x, y, z = self._reverse_tilt(x, y, z)
        return x, y, z

    def _reverse_tilt(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        tx, ty, tz = -self.tilt_x, -self.tilt_y, -self.tilt_z
        if abs(tz) > 1e-15:
            cos_tz, sin_tz = math.cos(tz), math.sin(tz)
            x, y = x * cos_tz - y * sin_tz, x * sin_tz + y * cos_tz
        if abs(ty) > 1e-15:
            cos_ty, sin_ty = math.cos(ty), math.sin(ty)
            x, z = x * cos_ty + z * sin_ty, -x * sin_ty + z * cos_ty
        if abs(tx) > 1e-15:
            cos_tx, sin_tx = math.cos(tx), math.sin(tx)
            y, z = y * cos_tx - z * sin_tx, y * sin_tx + z * cos_tx
        return x, y, z
