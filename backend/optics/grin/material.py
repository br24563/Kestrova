"""
GRIN material definitions.

Provides material properties for gradient index optics.
"""

from typing import Optional
from dataclasses import dataclass
import numpy as np
from .profile import GRINProfile, RadialGRIN


@dataclass
class GRINMaterial:
    """GRIN material: index profile plus optional published properties."""
    name: str
    profile: GRINProfile
    abbe_number: Optional[float] = None
    transmission_range: Optional[tuple] = None   # nm
    density: Optional[float] = None              # g/cm^3
    thermal_expansion: Optional[float] = None    # 1e-6/K
    dn_dT: Optional[float] = None                # 1e-6/K

    def index_at(self, *args) -> float:
        return self.profile.index(*args)

    def gradient_at(self, *args) -> np.ndarray:
        return self.profile.gradient(*args)


def create_grin_material(
    name: str,
    profile_type: str = 'radial',
    n0: float = 1.5,
    g: float = 0.1,
    **kwargs
) -> GRINMaterial:
    """
    Create a GRIN material.

    Args:
        name: Material name
        profile_type: 'axial', 'radial', or '3d'
        n0: Base refractive index
        g: Gradient constant (for radial)
        **kwargs: Additional parameters

    Returns:
        GRINMaterial instance
    """
    if profile_type == 'radial':
        profile: GRINProfile = RadialGRIN(n0=n0, g=g)
    elif profile_type == 'axial':
        from .profile import AxialGRIN
        coefficients = kwargs.get('coefficients', [n0, 0.0, 0.0])
        profile = AxialGRIN(n0=n0, coefficients=coefficients)
    elif profile_type == '3d':
        from .profile import GRIN3D
        gradient = kwargs.get('gradient', np.zeros(3))
        profile = GRIN3D(n0=n0, gradient_vector=gradient)
    else:
        raise ValueError(f"Unknown profile type: {profile_type}")

    return GRINMaterial(name=name, profile=profile, **kwargs)


# No predefined commercial GRIN materials are shipped: vendor profiles
# (e.g. gradient constants of GRIN rods) must be entered from the supplier's
# data sheet with create_grin_material.
GRIN_MATERIALS: dict = {}
