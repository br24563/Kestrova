"""
Base model for optical components.

This module is deliberately dependency-free (it imports only Pydantic)
so that both ``models.py`` and ``advanced_surfaces.py`` can import
``OpticalComponentBase`` without creating a circular import.

All length values are in meters (SI base unit).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class OpticalComponentBase(BaseModel):
    """
    Base model for all optical components.

    Every component has a unique ID and a position along the optical axis
    (z-axis, in meters). The position is measured from the origin, which
    is typically the object position or the left edge of the optical bench.
    """

    id: str = Field(..., description="Unique identifier for this component")
    position: float = Field(..., description="Position along optical axis (meters)")
    # Clear-aperture shape beyond the component's circular aperture (applied
    # to every surface of the component when rays are clipped).
    obscuration_diameter: Optional[float] = Field(
        default=None, description="Central circular obscuration diameter (m)"
    )
    aperture_shape: Literal["circular", "rectangular", "elliptical"] = Field(
        default="circular",
        description="rectangular / elliptical use aperture_half_x and aperture_half_y",
    )
    aperture_half_x: Optional[float] = Field(
        default=None,
        description="Half-width in x of a rectangular/elliptical aperture (m)",
    )
    aperture_half_y: Optional[float] = Field(
        default=None,
        description="Half-width in y of a rectangular/elliptical aperture (m)",
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        if not v or not v.strip():
            raise ValueError("Component ID cannot be empty")
        return v.strip()

    @field_validator("position")
    @classmethod
    def validate_position(cls, v):
        if not isinstance(v, (int, float)):
            raise ValueError("Position must be a number")
        if abs(v) > 1e6:
            raise ValueError(
                "Position must be within reasonable bounds (|z| < 1000 km)"
            )
        return float(v)
