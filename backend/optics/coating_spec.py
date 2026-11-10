"""
Thin-film coatings on lens surfaces (the prescription side; the physics is
in :mod:`optics.coatings.transfer_matrix` and :mod:`optics.polarization_trace`).

A coating is a stack of layers listed in the order light meets them, from
the medium before the surface to the medium after it. Each layer has a
physical thickness and either a material (its index from the database at
each traced wavelength) or an explicit index n - i k. A surface without a
coating is a bare Fresnel interface.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class CoatingLayer(BaseModel):
    material: Optional[str] = Field(
        default=None, description="Database material (index at each wavelength)"
    )
    n: Optional[float] = Field(default=None, gt=0, description="Explicit real index")
    k: float = Field(default=0.0, ge=0, description="Extinction coefficient")
    thickness: float = Field(..., gt=0, description="Physical thickness (m)")

    @model_validator(mode="after")
    def _check(self):
        if self.material is None and self.n is None:
            raise ValueError("A coating layer needs a material or an index n")
        return self


class CoatingSpec(BaseModel):
    """A thin-film stack, layers in the order light meets them."""

    name: str = ""
    layers: list[CoatingLayer] = Field(default_factory=list)

    @classmethod
    def quarter_wave(
        cls, material: str, wavelength: float, n: Optional[float] = None
    ) -> "CoatingSpec":
        """A single quarter-wave layer (optical thickness lambda / 4) at
        ``wavelength``; ``n`` overrides the database index."""
        if n is None:
            from .materials import refractive_index

            n = refractive_index(material, wavelength)
        return cls(
            name=f"QW {material} @ {wavelength * 1e9:.0f} nm",
            layers=[CoatingLayer(material=material, thickness=wavelength / (4 * n))],
        )
