"""
Prism optical components.

Deviation angles are in degrees. ``path_length`` is the unfolded glass path
(the tunnel-diagram length) for a beam of aperture equal to the prism face
A, from W. J. Smith, *Modern Optical Engineering*, 4th ed., ch. 8:
right-angle prism A, Porro prism 2A, pentaprism 3.414A. Prisms whose path
depends on the glass index (Dove) do not provide one.
"""

from typing import Optional, Tuple, List
from dataclasses import dataclass
import numpy as np
from ..nsc.system import Object3D, Vector3


@dataclass
class Prism(Object3D):
    """Base prism component."""
    prism_type: str = "generic"
    material: str = "N-BK7"
    apex_angle: float = 60.0  # degrees
    base_size: float = 25.4  # mm
    height: float = 25.4  # mm

    def __post_init__(self):
        self.object_type = "prism"
        self.reflection_count = 0  # Number of internal reflections

    def path_length(self, beam_height: float = None) -> float:
        """Unfolded glass path (same units as base_size)."""
        raise NotImplementedError(f"No tunnel-diagram length for a {self.prism_type} prism")

    def deviation_angle(self) -> float:
        """Calculate beam deviation angle."""
        return 0.0  # Override in subclasses


class RightAnglePrism(Prism):
    """Right angle prism (90-45-45 degrees)."""

    def __init__(self, position=None, material="N-BK7", size=25.4, rotation=0.0):
        super().__init__(
            name="RightAnglePrism",
            position=position or Vector3(),
            prism_type="right_angle",
            material=material,
            apex_angle=90.0,
            base_size=size,
            height=size,
        )
        self.rotation = rotation
        self.reflection_count = 1

    def deviation_angle(self) -> float:
        """90 degree deviation."""
        return 90.0

    def path_length(self, beam_height: float = None) -> float:
        """Tunnel length A (90-degree use, reflection at the hypotenuse)."""
        return self.base_size


class PorroPrism(Prism):
    """Porro prism for image inversion."""

    def __init__(self, position=None, material="N-BK7", size=25.4):
        super().__init__(
            name="PorroPrism",
            position=position or Vector3(),
            prism_type="porro",
            material=material,
            apex_angle=90.0,
            base_size=size,
            height=size,
        )
        self.reflection_count = 2

    def deviation_angle(self) -> float:
        """180 degree deviation (image inversion)."""
        return 180.0

    def path_length(self, beam_height: float = None) -> float:
        """Path length."""
        return 2 * self.base_size


class DovePrism(Prism):
    """Dove prism for image rotation."""

    def __init__(self, position=None, material="N-BK7", length=50.8, height=25.4):
        super().__init__(
            name="DovePrism",
            position=position or Vector3(),
            prism_type="dove",
            material=material,
            base_size=length,
            height=height,
        )
        self.reflection_count = 1

    def deviation_angle(self) -> float:
        """Image rotation (2x prism rotation)."""
        return 0.0  # No deviation, just rotation

class RoofPrism(Prism):
    """Roof prism (Amici, Pechan, etc.)."""

    def __init__(self, position=None, material="N-BK7", size=25.4, roof_type="amici"):
        super().__init__(
            name=f"{roof_type.capitalize()}Prism",
            position=position or Vector3(),
            prism_type=f"roof_{roof_type}",
            material=material,
            apex_angle=90.0,
            base_size=size,
            height=size,
        )
        if roof_type not in ("amici", "pechan"):
            raise ValueError("roof_type must be 'amici' or 'pechan'")
        self.roof_type = roof_type
        # Amici: right-angle prism with a roof (the roof adds a reflection).
        # Pechan-Schmidt: in-line erecting prism, 6 reflections incl. the roof.
        self.reflection_count = 2 if roof_type == "amici" else 6

    def deviation_angle(self) -> float:
        """Amici 90 degrees; Pechan-Schmidt 0 (in-line)."""
        return 90.0 if self.roof_type == "amici" else 0.0


class PentaPrism(Prism):
    """Penta prism for 90 degree deviation."""

    def __init__(self, position=None, material="N-BK7", size=25.4):
        super().__init__(
            name="PentaPrism",
            position=position or Vector3(),
            prism_type="penta",
            material=material,
            apex_angle=90.0,
            base_size=size,
            height=size,
        )
        self.reflection_count = 2

    def deviation_angle(self) -> float:
        """Constant 90 degree deviation (insensitive to orientation)."""
        return 90.0

    def path_length(self, beam_height: float = None) -> float:
        """Tunnel length 3.414 A."""
        return self.base_size * (2 + np.sqrt(2))


class WedgePrism(Prism):
    """Wedge prism for beam deviation."""

    def __init__(self, position=None, material="N-BK7", wedge_angle=5.0, size=25.4):
        super().__init__(
            name="WedgePrism",
            position=position or Vector3(),
            prism_type="wedge",
            material=material,
            apex_angle=wedge_angle,
            base_size=size,
            height=size,
        )
        self.wedge_angle = wedge_angle
        self.reflection_count = 0

    def deviation_angle(self, wavelength: float = 587.5618e-9) -> float:
        """
        Deviation (degrees) for light at normal incidence on the first face:
        asin(n sin(alpha)) - alpha (-> (n-1) alpha for a thin wedge).
        """
        from ..materials import refractive_index
        n = refractive_index(self.material, wavelength)
        a = np.radians(self.wedge_angle)
        s = n * np.sin(a)
        if s >= 1.0:
            raise ValueError("Total internal reflection at the second face")
        return float(np.degrees(np.arcsin(s) - a))

    def path_length(self, beam_height: float = None) -> float:
        """The glass path depends on where the beam crosses the wedge and on
        its thin-edge thickness, which this model does not hold."""
        raise NotImplementedError("Wedge glass path needs the edge thicknesses")


def create_prism(prism_type, **kwargs):
    """
    Factory function to build a prism by its common name.

    Args:
        prism_type: One of "right_angle", "porro", "dove", "roof",
            "penta", "wedge" (case-insensitive).
        **kwargs: Constructor arguments forwarded to the prism class.

    Returns:
        An instance of the requested prism subclass.

    Raises:
        ValueError: If the prism type is not recognised.
    """
    mapping = {
        "right_angle": RightAnglePrism,
        "porro": PorroPrism,
        "dove": DovePrism,
        "roof": RoofPrism,
        "penta": PentaPrism,
        "wedge": WedgePrism,
    }
    key = str(prism_type).lower().replace("-", "_").replace(" ", "_")
    cls = mapping.get(key)
    if cls is None:
        raise ValueError(
            "Unknown prism type: " + str(prism_type)
            + ". Known types: " + ", ".join(sorted(mapping))
        )
    return cls(**kwargs)
