"""
Data models for the optical design engine.

All models use Pydantic v2 for type safety, validation, and JSON
serialization. The models are independent of any UI framework.

Sign convention (optics, used in optical design software):
    - Light travels from left to right (z-axis).
    - Heights above the optical axis are positive (y-axis).
    - Angles measured counterclockwise from the axis are positive.
    - Object distance (s): NEGATIVE if object is to the LEFT of the lens.
    - Object distance (s): POSITIVE if object is to the RIGHT of the lens.
    - Image distance (s'): NEGATIVE if image is to the LEFT of the lens.
    - Image distance (s'): POSITIVE if image is to the RIGHT of the lens.
    - Focal length: positive for converging, negative for diverging.

All length values are in meters (SI base unit).
All angle values are in radians (SI base unit).
All wavelength values are in meters.
"""

from typing import Union, Literal, Annotated, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Optical Components
# ---------------------------------------------------------------------------

class OpticalComponentBase(BaseModel):
    """
    Base model for all optical components.

    Every component has a unique ID and a position along the optical axis
    (z-axis, in meters). The position is measured from the origin, which
    is typically the object position or the left edge of the optical bench.
    """

    id: str = Field(..., description="Unique identifier for this component")
    position: float = Field(..., description="Position along optical axis (meters)")


class ThinLens(OpticalComponentBase):
    """
    A thin lens optical component.

    A thin lens has no thickness; all refraction is assumed to occur at
    a single plane. This is an approximation valid when the lens
    thickness is small compared to the focal length.

    Sign convention:
        - focal_length > 0: converging lens
        - focal_length < 0: diverging lens
    """

    type: Literal["thin_lens"] = "thin_lens"
    focal_length: float = Field(..., description="Focal length in meters (positive=converging)")
    aperture_diameter: float = Field(..., description="Aperture diameter in meters")
    material: str = Field(default="N-BK7", description="Glass material name")


class SphericalSurface(OpticalComponentBase):
    """
    A spherical refractive surface.

    This component represents a single spherical surface of a lens or
    window. It is included in the architecture for future use (Phase 2)
    but may not be fully implemented in the MVP.

    Sign convention:
        - radius > 0: center of curvature is to the right of the surface
        - radius < 0: center of curvature is to the left of the surface
    """

    type: Literal["spherical_surface"] = "spherical_surface"
    radius: float = Field(..., description="Radius of curvature in meters")
    thickness: float = Field(..., description="Thickness of the element in meters")
    material: str = Field(default="N-BK7", description="Glass material name")


class ApertureStop(OpticalComponentBase):
    """
    An aperture stop (iris diaphragm).

    Limits the cone of light passing through the system.
    """

    type: Literal["aperture"] = "aperture"
    diameter: float = Field(..., description="Aperture diameter in meters")


class Mirror(OpticalComponentBase):
    """
    A flat mirror.

    Included in the architecture for future use.
    """

    type: Literal["mirror"] = "mirror"
    width: float = Field(..., description="Mirror width in meters")


# Discriminated union: allows the system to hold any component type
# and automatically deserialize the correct type based on the "type" field.
OpticalComponent = Annotated[
    Union[ThinLens, SphericalSurface, ApertureStop, Mirror],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Object and Image Plane
# ---------------------------------------------------------------------------

class Object(BaseModel):
    """
    The object being imaged.

    The object is a point or extended source placed at a position along
    the optical axis. Its height determines the size of the object.
    """

    position: float = Field(..., description="Object position along axis (meters)")
    height: float = Field(..., description="Object height (meters)")
    orientation: float = Field(default=0.0, description="Object orientation (radians)")


class ImagePlane(BaseModel):
    """
    The image plane where the image is formed.

    In the MVP, the image plane position is calculated by the engine.
    The user can also set it manually.
    """

    position: float = Field(..., description="Image plane position along axis (meters)")


# ---------------------------------------------------------------------------
# Analysis Settings
# ---------------------------------------------------------------------------

class AnalysisSettings(BaseModel):
    """
    Settings that control ray tracing and analysis.

    These settings determine how many rays are traced, what types of
    rays are included, and how the aperture is sampled.
    """

    num_rays: int = Field(default=11, ge=1, description="Number of rays to trace")
    ray_types: list[str] = Field(
        default=["chief", "marginal", "fill"],
        description="Types of rays to trace: chief, marginal, fill"
    )
    aperture_fraction: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Fraction of aperture diameter to use (0.0 to 1.0)"
    )
    wavelength: float = Field(
        default=550e-9,
        description="Wavelength for ray tracing (meters, default 550nm green)"
    )


# ---------------------------------------------------------------------------
# Optical System
# ---------------------------------------------------------------------------

class OpticalSystem(BaseModel):
    """
    A complete optical system.

    The system consists of:
        - A list of optical components (lenses, surfaces, apertures, etc.)
        - An object to be imaged
        - An image plane where the image forms
        - Wavelength(s) of light
    """

    components: list[OpticalComponent] = Field(
        default_factory=list,
        description="Ordered list of optical components (left to right)"
    )
    wavelengths: list[float] = Field(
        default_factory=lambda: [550e-9],
        description="Wavelengths of light in meters (default: 550nm green)"
    )
    object: Object = Field(..., description="The object being imaged")
    image_plane: ImagePlane = Field(..., description="The image plane")
    analysis_settings: AnalysisSettings = Field(
        default_factory=AnalysisSettings,
        description="Settings for ray tracing and analysis"
    )


# ---------------------------------------------------------------------------
# Ray Tracing Models
# ---------------------------------------------------------------------------

class Ray(BaseModel):
    """
    A single ray in the optical system.

    A ray is defined by its height (y) above the optical axis and its
    angle (theta) from the optical axis. The position (z) along the
    axis is tracked as the ray propagates.

    All values are in SI base units (meters, radians).
    """

    y: float = Field(..., description="Ray height above axis (meters)")
    theta: float = Field(..., description="Ray angle from axis (radians)")
    z: float = Field(..., description="Position along axis (meters)")
    wavelength: float = Field(..., description="Wavelength (meters)")
    ray_type: str = Field(
        default="fill",
        description="Ray type: 'chief', 'marginal', or 'fill'"
    )


class RayPath(BaseModel):
    """
    The path of a single ray through the optical system.

    The path is a series of (z, y) points where the ray intersects
    optical elements or changes direction.
    """

    points: list[list[float]] = Field(
        ...,
        description="List of [z, y] points along the ray path (meters)"
    )
    ray_type: str = Field(..., description="Ray type: 'chief', 'marginal', or 'fill'")
    wavelength: float = Field(..., description="Wavelength (meters)")
    initial_y: float = Field(..., description="Initial ray height (meters)")
    initial_theta: float = Field(..., description="Initial ray angle (radians)")
    final_y: float = Field(..., description="Final ray height at image plane (meters)")
    final_theta: float = Field(..., description="Final ray angle (radians)")


class RayTraceResult(BaseModel):
    """
    Results of tracing rays through an optical system.

    Contains the ray paths, the calculated image position, and the
    image height.
    """

    ray_paths: list[RayPath] = Field(
        default_factory=list,
        description="Paths of all traced rays"
    )
    image_position: float = Field(
        ...,
        description="Calculated image position along axis (meters)"
    )
    image_height: float = Field(
        ...,
        description="Calculated image height (meters)"
    )
    paraxial_image_height: float = Field(
        ...,
        description="Paraxial image height (meters)"
    )


# ---------------------------------------------------------------------------
# Analysis Result Models
# ---------------------------------------------------------------------------

class AnalysisResult(BaseModel):
    """
    Results of optical analysis for a system.

    All values are in SI base units (meters, radians).
    """

    effective_focal_length: float = Field(
        ...,
        description="Effective focal length of the system (meters)"
    )
    magnification: float = Field(
        ...,
        description="Transverse magnification (dimensionless, negative=inverted)"
    )
    image_distance: float = Field(
        ...,
        description="Distance from last lens to image (meters)"
    )
    object_distance: float = Field(
        ...,
        description="Distance from first lens to object (meters)"
    )
    f_number: float = Field(
        ...,
        description="F-number (f/D, dimensionless)"
    )
    numerical_aperture: float = Field(
        ...,
        description="Numerical aperture (dimensionless)"
    )
    aperture_diameter: float = Field(
        ...,
        description="Effective aperture diameter (meters)"
    )
    working_distance: float = Field(
        ...,
        description="Distance from last lens to image plane (meters)"
    )
    rms_spot_radius: float = Field(
        ...,
        description="RMS spot radius at image plane (meters)"
    )
    spot_points: list[list[float]] = Field(
        default_factory=list,
        description="List of [y, z] spot positions at image plane (meters)"
    )
    is_image_real: bool = Field(
        ...,
        description="True if the image is real (can be projected on a screen)"
    )
    is_image_inverted: bool = Field(
        ...,
        description="True if the image is inverted relative to the object"
    )
