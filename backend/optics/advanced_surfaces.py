"""Advanced Surface Types for Sequential Optical Design.

These are the prescription models only. The sequential engine
(:mod:`optics.raytrace`, ``_shape_for`` and ``build_sequence``) turns each
into its exact 3D surface: even/odd aspheres into ``Conicoid``, Q-type
aspheres into Forbes Qbfs/Qcon polynomials, Zernike sag surfaces into
``ZernikeShape``, toric surfaces into a ``YToroid``, DOEs into a phase
surface and coordinate breaks into frame changes.

All values are in SI base units (meters, radians).
"""

from typing import Literal

from pydantic import Field

from .base import OpticalComponentBase

# =============================================================================
# Aspheric Surface Types
# =============================================================================


class AsphericSurface(OpticalComponentBase):
    """Even aspheric surface.

    Sag: z(r) = c r^2 / (1 + sqrt(1 - (1+k) c^2 r^2)) + sum_i A_i r^(2i+4),
    with c = 1/radius (``aspheric_coeffs`` start at r^4).
    """

    type: Literal["aspheric"] = "aspheric"
    radius: float = 0.1
    conic: float = 0.0
    aspheric_coeffs: list[float] = Field(default_factory=list)
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0


class OddAsphericSurface(OpticalComponentBase):
    """Odd aspheric surface: the even asphere plus odd terms
    sum_i B_i r^(2i+1) (``odd_coeffs`` start at r^1)."""

    type: Literal["odd_aspheric"] = "odd_aspheric"
    radius: float = 0.1
    conic: float = 0.0
    aspheric_coeffs: list[float] = Field(default_factory=list)
    odd_coeffs: list[float] = Field(default_factory=list)
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0


class QAsphericSurface(OpticalComponentBase):
    """Forbes Q-type asphere (``q_type`` "Qbfs" or "Qcon") with polynomial
    ``coefficients`` normalised to ``norm_radius``."""

    type: Literal["q_aspheric"] = "q_aspheric"
    radius: float = 0.1
    conic: float = 0.0
    q_type: str = "Qbfs"
    coefficients: list[float] = Field(default_factory=list)
    norm_radius: float = 0.025
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0


class ZernikeSurface(OpticalComponentBase):
    """Zernike sag surface (standard/Noll-ordered coefficients over
    ``norm_radius``)."""

    type: Literal["zernike"] = "zernike"
    zernike_coeffs: list[float] = Field(default_factory=list)
    norm_radius: float = 0.025
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0


class DiffractiveOpticalElement(OpticalComponentBase):
    """Diffractive surface: phase phi(r) = sum_i c_i r^(2i+2) (radians) in
    the given diffraction order."""

    type: Literal["doe"] = "doe"
    doe_type: str = "kinoform"
    design_wavelength: float = 550e-9
    diffraction_order: int = 1
    phase_coeffs: list[float] = Field(default_factory=list)
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0


class ToricSurface(OpticalComponentBase):
    """Toric surface (Y-toroid): tangential and sagittal radii."""

    type: Literal["toric"] = "toric"
    radius_tangential: float = 0.1
    radius_sagittal: float = 0.1
    conic: float = 0.0
    aperture_diameter: float = 0.025
    material: str = "N-BK7"
    thickness: float = 0.0


class CoordinateBreak(OpticalComponentBase):
    """Coordinate break: decenter and tilt the frame of every following
    surface."""

    type: Literal["coordinate_break"] = "coordinate_break"
    decenter_x: float = 0.0
    decenter_y: float = 0.0
    decenter_z: float = 0.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    tilt_z: float = 0.0
    order: str = "decenter_then_tilt"
