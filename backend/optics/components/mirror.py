"""
Mirror optical components.

Provides fold mirrors and dichroic mirrors.
"""

from typing import Optional
from dataclasses import dataclass
from ..nsc.system import Object3D, Vector3


@dataclass
class FoldMirror(Object3D):
    """Flat fold mirror for beam steering."""

    def __init__(
        self, position=None, normal=None, size=25.4, coating="ProtectedAluminum"
    ):
        super().__init__(
            name="FoldMirror",
            position=position or Vector3(),
            object_type="mirror",
        )
        self.normal = normal or Vector3(0, 0, -1)
        self.size = size
        self.coating = coating
        self.reflectivity = self._get_reflectivity()

    def _get_reflectivity(self) -> float:
        """
        Nominal average reflectance of common commercial mirror coatings in
        their design band (gold: near-IR, above ~700 nm). Indicative only;
        use the vendor's measured curve for real work.
        """
        coatings = {
            "ProtectedAluminum": 0.90,
            "EnhancedAluminum": 0.95,
            "ProtectedSilver": 0.98,
            "ProtectedGold": 0.98,
            "Dielectric": 0.995,
        }
        if self.coating not in coatings:
            raise ValueError(
                f"Unknown coating '{self.coating}'; set reflectivity explicitly"
            )
        return coatings[self.coating]


@dataclass
class DichroicMirror(Object3D):
    """Dichroic/beamsplitter mirror."""

    def __init__(
        self,
        position=None,
        normal=None,
        size=25.4,
        cutoff_wavelength=550.0,
        coating="longpass",
    ):
        super().__init__(
            name="DichroicMirror",
            position=position or Vector3(),
            object_type="mirror",
        )
        self.normal = normal or Vector3(0, 0, -1)
        self.size = size
        self.cutoff_wavelength = cutoff_wavelength  # nm
        self.coating = coating  # 'longpass' or 'shortpass'
        self.reflectivity = 0.95
        self.transmission = 0.95

    def response(self, wavelength: float) -> tuple[float, float]:
        """
        (R, T) of an ideal step-edge dichroic. A longpass dichroic transmits
        wavelengths above the cutoff and reflects those below; a shortpass
        the reverse. ``reflectivity`` and ``transmission`` are the in-band
        levels (no absorption assumed).
        """
        passes = (
            (wavelength > self.cutoff_wavelength)
            if self.coating == "longpass"
            else (wavelength < self.cutoff_wavelength)
        )
        if passes:
            return (1 - self.transmission, self.transmission)
        return (self.reflectivity, 1 - self.reflectivity)
