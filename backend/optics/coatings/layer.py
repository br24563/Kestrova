"""
Thin-film layer definition.

A layer is a material, a physical thickness in nm and a complex index
N = n - i k (Macleod's convention). The index is either given explicitly or
taken from the material database (:mod:`optics.materials`) at
``design_wavelength``; those are bulk values, and deposited films can
differ, so give measured film indices where they matter. A material with no
data raises ValueError rather than receiving a default.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Layer:
    """A single thin-film layer."""
    material: str
    thickness: float                     # physical thickness, nm
    n: Optional[complex] = None          # complex index n - ik
    design_wavelength: float = 550.0     # nm, used only for the database lookup

    def __post_init__(self):
        if self.n is None:
            self.n = self._get_refractive_index()
        self.n = complex(self.n)

    def _get_refractive_index(self) -> complex:
        from optics.materials import refractive_index
        try:
            return complex(refractive_index(self.material, self.design_wavelength * 1e-9))
        except ValueError as e:
            raise ValueError(
                f"No index data for coating material '{self.material}' at "
                f"{self.design_wavelength} nm; pass n explicitly ({e})") from e

    @property
    def optical_thickness(self) -> float:
        """Optical thickness n d (nm)."""
        assert self.n is not None   # set in __post_init__
        return self.n.real * self.thickness


@dataclass
class MaterialLayer(Layer):
    """Layer with an explicit extinction coefficient and roughness."""
    absorption: float = 0.0     # extinction coefficient k
    roughness: float = 0.0      # RMS roughness (nm), informational

    def __post_init__(self):
        super().__post_init__()
        if self.absorption:
            self.n = complex(self.n.real, -abs(self.absorption))
