"""
Expanded optical materials catalog.

A per-vendor view of :mod:`optics.materials`, which holds the actual data:
every glass is taken from the Schott, Ohara, Hoya or CDGM catalog, and every
crystal, IR material, polymer and liquid from a cited measurement. See that
module and ``tools/build_glass_catalog.py`` for the sources.

Properties a source does not publish are ``None`` rather than a guess.
"""

from typing import Optional

from .materials import (
    MATERIALS, Material, D_LINE,
    refractive_index as _refractive_index,
    refractive_index_sellmeier as _refractive_index_sellmeier,
    get_material,
)

#: Kept for backward compatibility: material records are :class:`Material`.
MaterialProperties = Material


def _by_vendor(vendor: str) -> dict[str, Material]:
    return {k: m for k, m in MATERIALS.items() if m.manufacturer == vendor}


SCHOTT_MATERIALS = _by_vendor("Schott")
OHARA_MATERIALS = _by_vendor("Ohara")
HOYA_MATERIALS = _by_vendor("Hoya")
CDGM_MATERIALS = _by_vendor("CDGM")
SPECIAL_MATERIALS = {
    k: m for k, m in MATERIALS.items()
    if m.manufacturer in ("Literature", "N/A")
}

ALL_MATERIALS: dict[str, Material] = dict(MATERIALS)

REFRACTIVE_INDICES: dict[str, Optional[float]] = {
    name: props.nd for name, props in ALL_MATERIALS.items()
}


def get_material_properties(name: str) -> Optional[Material]:
    """Get full properties for a material, or None if unknown."""
    try:
        return get_material(name)
    except ValueError:
        return None


def search_materials(
    manufacturer: Optional[str] = None,
    material_type: Optional[str] = None,
    min_nd: Optional[float] = None,
    max_nd: Optional[float] = None,
    min_vd: Optional[float] = None,
    max_vd: Optional[float] = None,
) -> list[Material]:
    """Search materials by properties. Materials lacking a value are excluded
    by any filter on that value."""
    results = []
    for props in ALL_MATERIALS.values():
        if manufacturer and props.manufacturer.lower() != manufacturer.lower():
            continue
        if material_type and props.material_type != material_type:
            continue
        nd, vd = props.nd, props.vd
        if min_nd is not None and (nd is None or nd < min_nd):
            continue
        if max_nd is not None and (nd is None or nd > max_nd):
            continue
        if min_vd is not None and (vd is None or vd < min_vd):
            continue
        if max_vd is not None and (vd is None or vd > max_vd):
            continue
        results.append(props)
    return results


def get_glass_map_data() -> list[dict]:
    """Data for a glass map (nd vs Vd) of the catalog glasses."""
    return [
        {
            "name": name,
            "nd": props.nd,
            "vd": props.vd,
            "type": props.material_type,
            "manufacturer": props.manufacturer,
        }
        for name, props in ALL_MATERIALS.items()
        if props.material_type in ("crown", "flint", "lanthanum")
    ]


def refractive_index(material: str, wavelength: float = D_LINE) -> float:
    """Refractive index at a wavelength (meters); see optics.materials."""
    return _refractive_index(material, wavelength)


def refractive_index_sellmeier(material: str, wavelength: float) -> float:
    """Refractive index from the dispersion formula; see optics.materials."""
    return _refractive_index_sellmeier(material, wavelength)
