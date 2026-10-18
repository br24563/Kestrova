"""
Glass availability, relative price and compliance data.

Everything here comes from what the glass manufacturers publish in their
catalogs (see ``tools/build_glass_catalog.py``):

- **Availability** is the vendor's own classification: Schott "preferred" or
  "inquiry" glass, Ohara and Hoya "recommended" glass, and CDGM's melt
  frequency code (MA = stocked all year; A/B/C/D = melted twice a year to
  less than once in two years, limited stock). Nothing is inferred from
  price or position on the glass map.
- **Price** is the vendor's *relative* price index (Schott: N-BK7 = 1;
  CDGM: H-K9L = 1). Absolute prices are never invented: a figure in
  currency is only produced from a quote recorded with
  :func:`set_vendor_quote`, or from a reference price per kilogram the
  caller supplies with :func:`set_reference_price`.
- **Lead content** is flagged only for the Schott lead-silicate flint
  families (F, LF, LLF, SF without the "N-" prefix). Schott's "N-" glasses,
  Ohara "S-" glasses and the current Hoya and CDGM catalogs are marketed as
  lead- and arsenic-free. Vendor material declarations remain the authority.

Masses are in kilograms; lengths in meters.
"""

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .materials import refractive_index
from .materials_expanded import ALL_MATERIALS, MaterialProperties


# =============================================================================
# Enumerations
# =============================================================================

class Availability(str, Enum):
    """How readily a glass can be sourced, from the vendor's classification."""

    IN_STOCK = "in_stock"            # CDGM "MA": in stock all year round
    STANDARD = "standard"            # vendor preferred / recommended glass
    MADE_TO_ORDER = "made_to_order"  # Schott inquiry glass; CDGM melt A-D
    LIMITED = "limited"
    OBSOLETE = "obsolete"
    UNKNOWN = "unknown"              # vendor publishes no classification


class RestrictionClass(str, Enum):
    """Regulatory restriction applying to a material."""

    UNRESTRICTED = "unrestricted"
    DECLARABLE = "declarable"   # must be declared, may still be used
    RESTRICTED = "restricted"   # restricted under RoHS / REACH
    PROHIBITED = "prohibited"   # do not use in new designs

    @property
    def is_compliant(self) -> bool:
        """True when the class allows unrestricted use in a new design."""
        return self in (RestrictionClass.UNRESTRICTED,
                        RestrictionClass.DECLARABLE)


# =============================================================================
# Restricted substances
# =============================================================================

@dataclass(frozen=True)
class RestrictedSubstance:
    """One regulated substance and what it means for a glass choice."""

    symbol: str
    name: str
    restriction: RestrictionClass
    regulation: str
    limit_ppm: Optional[float] = None   # maximum concentration, ppm by weight
    comment: str = ""


#: RoHS (Directive 2011/65/EU, Annex II as amended by 2015/863) limits lead,
#: mercury and hexavalent chromium to 0.1 % and cadmium to 0.01 % by weight
#: in homogeneous materials. Lead in optical glass is exempted under RoHS
#: Annex III item 13(a); it is still reported here so a design can avoid it.
RESTRICTED_SUBSTANCES: dict[str, RestrictedSubstance] = {
    "Pb": RestrictedSubstance(
        "Pb", "Lead", RestrictionClass.RESTRICTED,
        "RoHS 2011/65/EU Annex II (optical glass exempt under Annex III 13(a))",
        1000.0,
        "Constituent of the classic lead-silicate flints (F, LF, LLF, SF)."),
    "Cd": RestrictedSubstance(
        "Cd", "Cadmium", RestrictionClass.RESTRICTED,
        "RoHS 2011/65/EU Annex II", 100.0),
    "Hg": RestrictedSubstance(
        "Hg", "Mercury", RestrictionClass.RESTRICTED,
        "RoHS 2011/65/EU Annex II", 1000.0),
    "Cr6+": RestrictedSubstance(
        "Cr6+", "Hexavalent chromium", RestrictionClass.RESTRICTED,
        "RoHS 2011/65/EU Annex II", 1000.0),
}


# =============================================================================
# Per-glass data
# =============================================================================

@dataclass(frozen=True)
class GlassData:
    """Availability, compliance and price data for one glass."""

    name: str
    availability: Availability = Availability.UNKNOWN
    restriction: RestrictionClass = RestrictionClass.UNRESTRICTED
    relative_price: Optional[float] = None   # vendor index, reference glass = 1
    lead_time_days: Optional[float] = None   # only from a recorded quote
    suppliers: tuple = ()
    substances: tuple = ()
    vendor_status: Optional[str] = None      # as published by the vendor
    melt_frequency: Optional[str] = None     # CDGM code, as published
    notes: str = ""

    @property
    def is_compliant(self) -> bool:
        return self.restriction.is_compliant

    @property
    def supplier_count(self) -> int:
        return len(self.suppliers)


#: Schott's own lead-free replacements for its legacy lead flints (same
#: designation with the "N-" prefix, and both present in the current catalog).
LEAD_FREE_EQUIVALENTS = {
    old: "N-" + old
    for old in ("F2", "SF1", "SF2", "SF4", "SF5", "SF6", "SF10", "SF11", "SF57")
    if old in ALL_MATERIALS and "N-" + old in ALL_MATERIALS
}

#: Old designations that are written without the vendor's current prefix.
LEGACY_GLASS_ALIASES = {
    "BK7": "N-BK7",
}

_LEAD_FAMILY = re.compile(r"^(SF|F|LF|LLF)\d")


def resolve_glass_name(name: str) -> str:
    """Map a legacy designation onto its catalog name (identity otherwise)."""
    return LEGACY_GLASS_ALIASES.get(name, name)


def _availability(props: MaterialProperties) -> Availability:
    if props.melt_frequency:
        return (Availability.IN_STOCK if props.melt_frequency == "MA"
                else Availability.MADE_TO_ORDER)
    return {
        "preferred": Availability.STANDARD,
        "recommended": Availability.STANDARD,
        "inquiry": Availability.MADE_TO_ORDER,
    }.get(props.status or "", Availability.UNKNOWN)


def catalog_glass_data(props: MaterialProperties) -> GlassData:
    """Build the :class:`GlassData` for a catalog material from vendor data."""
    substances = ()
    restriction = RestrictionClass.UNRESTRICTED
    if props.manufacturer == "Schott" and _LEAD_FAMILY.match(props.name):
        substances = ("Pb",)
        restriction = RestrictionClass.RESTRICTED
    vendor = props.manufacturer if props.manufacturer in (
        "Schott", "Ohara", "Hoya", "CDGM") else None
    return GlassData(
        name=props.name,
        availability=_availability(props),
        restriction=restriction,
        relative_price=props.relative_price,
        suppliers=(vendor,) if vendor else (),
        substances=substances,
        vendor_status=props.status,
        melt_frequency=props.melt_frequency,
        notes=props.source,
    )


# =============================================================================
# Recorded quotes and vendor overrides
# =============================================================================

_VENDOR_QUOTES: dict[str, dict] = {}
_VENDOR_DATA: dict[str, GlassData] = {}
_REFERENCE_PRICE: dict[str, Optional[float]] = {"per_kg": None}


def set_vendor_quote(name: str, price_per_kg: float,
                     supplier: Optional[str] = None,
                     lead_time_days: Optional[float] = None,
                     minimum_order_kg: Optional[float] = None) -> dict:
    """Record a real supplier quotation for a glass."""
    quote = {
        "glass": name,
        "price_per_kg": float(price_per_kg),
        "supplier": supplier,
        "lead_time_days": None if lead_time_days is None else float(lead_time_days),
        "minimum_order_kg": None if minimum_order_kg is None else float(minimum_order_kg),
    }
    _VENDOR_QUOTES[name] = quote
    return quote


def clear_vendor_quotes() -> None:
    _VENDOR_QUOTES.clear()


def get_vendor_quote(name: str) -> Optional[dict]:
    return _VENDOR_QUOTES.get(name)


def set_reference_price(price_per_kg: Optional[float]) -> None:
    """
    Set the price per kilogram of the vendors' reference glass (N-BK7 /
    H-K9L). With it, a glass's price is estimated as relative_price times
    this figure. Pass None to clear.
    """
    _REFERENCE_PRICE["per_kg"] = None if price_per_kg is None else float(price_per_kg)


def get_glass_data(name: str) -> Optional[GlassData]:
    """Vendor data for a glass, or None if it is not in the catalog."""
    name = resolve_glass_name(name)
    if name in _VENDOR_DATA:
        return _VENDOR_DATA[name]
    props = ALL_MATERIALS.get(name)
    if props is None:
        return None
    return catalog_glass_data(props)


def load_vendor_data(payload, replace: bool = False) -> int:
    """
    Load purchased or supplier-provided availability data, overriding the
    catalog-derived values::

        {"glasses": {"N-BK7": {"availability": "in_stock",
                               "lead_time_days": 3,
                               "suppliers": ["Schott"],
                               "price_per_kg": 120.0}}}

    ``price_per_kg`` is stored as a quote.
    """
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("vendor data must be a mapping")
    glasses = payload.get("glasses", payload)
    if not isinstance(glasses, dict):
        raise ValueError("vendor data must contain a 'glasses' mapping")
    if replace:
        _VENDOR_DATA.clear()

    loaded = 0
    for name, entry in glasses.items():
        if not isinstance(entry, dict):
            raise ValueError(f"vendor entry for {name!r} must be a mapping")
        base = get_glass_data(name) or GlassData(name)
        _VENDOR_DATA[name] = GlassData(
            name=name,
            availability=Availability(entry.get("availability", base.availability)),
            restriction=RestrictionClass(entry.get("restriction", base.restriction)),
            relative_price=entry.get("relative_price", base.relative_price),
            lead_time_days=entry.get("lead_time_days", base.lead_time_days),
            suppliers=tuple(entry.get("suppliers", base.suppliers)),
            substances=tuple(entry.get("substances", base.substances)),
            vendor_status=entry.get("vendor_status", base.vendor_status),
            melt_frequency=entry.get("melt_frequency", base.melt_frequency),
            notes=entry.get("notes", "Loaded from vendor data."),
        )
        if "price_per_kg" in entry:
            set_vendor_quote(name, entry["price_per_kg"],
                             lead_time_days=entry.get("lead_time_days"))
        loaded += 1
    return loaded


def clear_vendor_data() -> None:
    _VENDOR_DATA.clear()


# =============================================================================
# Pricing
# =============================================================================

def unit_price_per_kg(name: str) -> Optional[float]:
    """
    Price of a glass per kilogram, or None when no basis exists.

    A recorded quote wins; otherwise the vendor's relative price index is
    scaled by the reference price set with :func:`set_reference_price`.
    """
    name = resolve_glass_name(name)
    quote = _VENDOR_QUOTES.get(name)
    if quote is not None:
        return quote["price_per_kg"]
    data = get_glass_data(name)
    ref = _REFERENCE_PRICE["per_kg"]
    if data is None or data.relative_price is None or ref is None:
        return None
    return data.relative_price * ref


def element_blank_mass(diameter: float, thickness: float,
                       density: float, blank_factor: float = 1.0) -> float:
    """
    Mass in kilograms of a cylindrical blank (density in g/cm^3).

    ``blank_factor`` scales the ideal cylinder for material lost to edging and
    curve generation; it is the caller's input (default 1, the bare cylinder).
    """
    radius_m = max(0.0, diameter) / 2.0
    volume_m3 = math.pi * radius_m ** 2 * max(0.0, thickness)
    return volume_m3 * density * 1000.0 * max(0.0, blank_factor)


def element_material_cost(diameter: float, thickness: float, glass: str,
                          blank_factor: float = 1.0) -> Optional[float]:
    """Material cost of one element, or None without density or price data."""
    props = ALL_MATERIALS.get(resolve_glass_name(glass))
    price = unit_price_per_kg(glass)
    if props is None or props.density is None or price is None:
        return None
    return element_blank_mass(diameter, thickness, props.density, blank_factor) * price


# =============================================================================
# System-level summaries
# =============================================================================

def _component_glass(component) -> Optional[str]:
    material = getattr(component, "material", None)
    if not material:
        return None
    material = resolve_glass_name(material)
    return material if material in ALL_MATERIALS else None


def _component_geometry(component) -> tuple:
    """(diameter, centre thickness) in meters.

    A thin lens has no thickness; it is given the centre thickness of an
    equiconvex lens of the same focal length and glass with zero edge
    thickness, the minimum physically possible.
    """
    diameter = getattr(component, "aperture_diameter", 0.0) or 0.0
    if not diameter:
        diameter = getattr(component, "width", 0.0) or 0.0
    thickness = getattr(component, "thickness", None)
    if thickness is None:
        f = getattr(component, "focal_length", None)
        material = getattr(component, "material", None)
        thickness = 0.0
        if f and material:
            n = refractive_index(material)
            radius = 2.0 * (n - 1.0) * abs(f)
            semi = diameter / 2.0
            if 0.0 < semi < radius:
                thickness = 2.0 * (radius - math.sqrt(radius ** 2 - semi ** 2))
    return diameter, thickness


def system_glass_cost(system, quantity: int = 1, blank_factor: float = 1.0) -> dict:
    """
    Glass material cost for every element in a system.

    Costs are None for any glass without a recorded quote or reference price;
    fabrication cost is not modelled.
    """
    from .models import ApertureStop

    elements = []
    total = 0.0
    priced = True
    restricted, unknown = [], []
    for comp in sorted(system.components, key=lambda c: c.position):
        if isinstance(comp, ApertureStop):
            continue
        glass = _component_glass(comp)
        if glass is None:
            if getattr(comp, "material", None):
                unknown.append(comp.material)
            continue
        diameter, thickness = _component_geometry(comp)
        data = get_glass_data(glass)
        cost = element_material_cost(diameter, thickness, glass, blank_factor)
        if cost is None:
            priced = False
        else:
            total += cost
        if data is not None and not data.is_compliant:
            restricted.append(glass)
        elements.append({
            "id": getattr(comp, "id", ""),
            "type": getattr(comp, "type", ""),
            "glass": glass,
            "diameter_mm": diameter * 1e3,
            "thickness_mm": thickness * 1e3,
            "relative_price": data.relative_price if data else None,
            "unit_price_per_kg": unit_price_per_kg(glass),
            "material_cost": cost,
            "availability": data.availability.value if data else "unknown",
            "restriction": data.restriction.value if data else "unknown",
            "suppliers": list(data.suppliers) if data else [],
        })
    q = max(1, int(quantity))
    return {
        "elements": elements,
        "element_count": len(elements),
        "material_cost_per_unit": total if priced else None,
        "quantity": q,
        "total_material_cost": total * q if priced else None,
        "restricted_glasses": restricted,
        "unknown_glasses": unknown,
        "is_compliant": not restricted,
        "notes": ("Material cost needs a recorded quote (set_vendor_quote) or a "
                  "reference price (set_reference_price); vendors publish only "
                  "relative price indices."),
    }


SOURCABLE = (Availability.IN_STOCK, Availability.STANDARD, Availability.MADE_TO_ORDER)


def availability_status(name: str) -> dict:
    """Summary of whether a glass is a reasonable choice for a new design."""
    data = get_glass_data(name)
    if data is None:
        return {
            "glass": name, "known": False,
            "availability": Availability.UNKNOWN.value,
            "restriction": RestrictionClass.UNRESTRICTED.value,
            "vendor_status": None, "melt_frequency": None,
            "relative_price": None, "price_per_kg": None,
            "lead_time_days": None, "suppliers": [], "supplier_count": 0,
            "substances": [], "sourcable": False, "compliant": False,
            "lead_free_equivalent": None, "notes": "",
            "warning": "Glass is not present in the materials catalog.",
        }
    quote = get_vendor_quote(resolve_glass_name(name))
    warnings = []
    if data.availability is Availability.UNKNOWN:
        warnings.append("Vendor publishes no availability classification.")
    if data.substances:
        warnings.append("Contains " + ", ".join(
            f"{RESTRICTED_SUBSTANCES[s].name} ({s})" for s in data.substances) + ".")
    return {
        "glass": name, "known": True,
        "availability": data.availability.value,
        "restriction": data.restriction.value,
        "vendor_status": data.vendor_status,
        "melt_frequency": data.melt_frequency,
        "relative_price": data.relative_price,
        "price_per_kg": unit_price_per_kg(name),
        "lead_time_days": quote["lead_time_days"] if quote else data.lead_time_days,
        "suppliers": list(data.suppliers),
        "supplier_count": data.supplier_count,
        "substances": list(data.substances),
        "sourcable": data.availability in SOURCABLE,
        "compliant": data.is_compliant,
        "lead_free_equivalent": LEAD_FREE_EQUIVALENTS.get(resolve_glass_name(name)),
        "notes": data.notes,
        "warning": " ".join(warnings),
    }


def restricted_glasses() -> list:
    """Catalog glasses flagged as containing a restricted substance."""
    found = []
    for name in ALL_MATERIALS:
        data = get_glass_data(name)
        if data is not None and not data.is_compliant:
            found.append({
                "glass": name,
                "restriction": data.restriction.value,
                "substances": list(data.substances),
                "lead_free_equivalent": LEAD_FREE_EQUIVALENTS.get(name),
            })
    return sorted(found, key=lambda row: row["glass"])


def compliance_report(system) -> dict:
    """Compliance summary for every glass in a system."""
    rows = []
    for comp in sorted(system.components, key=lambda c: c.position):
        glass = _component_glass(comp)
        if glass is None:
            continue
        status = availability_status(glass)
        rows.append({
            "id": getattr(comp, "id", ""),
            "glass": glass,
            "compliant": status["compliant"],
            "restriction": status["restriction"],
            "substances": status["substances"],
            "regulation": sorted({RESTRICTED_SUBSTANCES[s].regulation
                                  for s in status["substances"]}),
            "warning": status["warning"],
        })
    non_compliant = [r["glass"] for r in rows if not r["compliant"]]
    return {
        "elements": rows,
        "element_count": len(rows),
        "non_compliant_glasses": non_compliant,
        "is_compliant": not non_compliant,
        "notes": ("Engineering guidance from vendor naming conventions, not a "
                  "legal declaration: confirm with the vendor's material "
                  "declaration."),
    }
