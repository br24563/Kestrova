"""
Thermal properties of optical materials.

All values come from :mod:`optics.materials`, i.e. from the glass
manufacturers' catalogs (dn/dT constants of the Schott formula, CTE
-30..+70 C, thermal conductivity, specific heat, density, Young's modulus,
Poisson's ratio). A property the source does not publish is ``None``.

Index change with temperature uses the Schott formula for the *absolute*
index (relative to vacuum):

    dn_abs(lambda, dT) = (n^2 - 1)/(2n) [D0 dT + D1 dT^2 + D2 dT^3
                         + (E0 dT + E1 dT^2) / (lambda^2 - lambda_tk^2)]

with dT = T - 20 C. The small change of the air index with temperature
(about -0.9e-6 /K at room temperature) is not included.
"""

from dataclasses import dataclass
from typing import Optional

from ..materials import get_material, refractive_index, D_LINE


@dataclass
class ThermalProperties:
    """Thermal properties of an optical material (None = not published)."""
    name: str
    dn_dT: Optional[float]                 # 1e-6/K, absolute, d-line, 20 C
    CTE: Optional[float]                   # 1e-6/K
    thermal_conductivity: Optional[float]  # W/(m K)
    specific_heat: Optional[float]         # J/(kg K)
    density: Optional[float]               # kg/m^3
    poisson_ratio: Optional[float] = None
    youngs_modulus: Optional[float] = None  # GPa


def get_thermal_properties(material_name: str) -> Optional[ThermalProperties]:
    """Thermal properties of a catalog material, or None if unknown."""
    try:
        m = get_material(material_name)
    except ValueError:
        return None
    return ThermalProperties(
        name=m.name, dn_dT=m.dn_dT, CTE=m.cte,
        thermal_conductivity=m.thermal_conductivity, specific_heat=m.specific_heat,
        density=m.density * 1000.0 if m.density is not None else None,
        poisson_ratio=m.poissons_ratio, youngs_modulus=m.youngs_modulus,
    )


def index_change(material_name: str, wavelength: float, temperature: float,
                 reference_temperature: float = 20.0) -> float:
    """
    Change of the absolute refractive index from ``reference_temperature``
    to ``temperature`` (C) by the Schott formula. The constants are defined
    about 20 C; raises ValueError if the material has none.
    """
    m = get_material(material_name)
    k = m.dn_dT_constants
    if not k:
        raise ValueError(f"No published dn/dT constants for '{material_name}'")
    n = refractive_index(material_name, wavelength)
    lam2 = (wavelength * 1e6) ** 2
    denom = lam2 - k["lambda_tk"] ** 2

    def dn(T):
        dT = T - 20.0
        return (n * n - 1.0) / (2.0 * n) * (
            k["D0"] * dT + k["D1"] * dT ** 2 + k["D2"] * dT ** 3
            + (k["E0"] * dT + k["E1"] * dT ** 2) / denom)

    return dn(temperature) - dn(reference_temperature)


def index_at_temperature(material_name: str, base_index: float,
                         base_temp: float = 20.0, target_temp: float = 20.0,
                         wavelength: float = D_LINE) -> float:
    """Index at ``target_temp`` given its value at ``base_temp``."""
    return base_index + index_change(material_name, wavelength, target_temp, base_temp)


def thermal_expansion(material_name: str, base_length: float,
                      base_temp: float = 20.0, target_temp: float = 20.0) -> float:
    """Length after linear expansion with the catalog CTE."""
    props = get_thermal_properties(material_name)
    if props is None or props.CTE is None:
        raise ValueError(f"No published CTE for '{material_name}'")
    return base_length * (1.0 + props.CTE * 1e-6 * (target_temp - base_temp))
