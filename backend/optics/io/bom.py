"""
Bill of materials (BOM).

One row per lens element: glass, diameter, centre thickness, radii, blank
mass (from the vendor's published density) and, when a price basis exists,
material cost (see :mod:`optics.glass_catalog`: a recorded quote or a
reference price times the vendor's relative price index). Fabrication cost,
coatings and tolerances are not part of the optical design and are not
invented here.

A ThinLens is an ideal lens with no geometry; its row reports the
equiconvex lens of the same focal length and glass with zero edge
thickness (the thinnest possible element), and is marked as such.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..models import OpticalSystem
from ..materials import refractive_index, get_material
from ..glass_catalog import element_blank_mass, unit_price_per_kg, get_glass_data


@dataclass
class BOMItem:
    """A single BOM item (lengths in mm, mass in kg)."""

    item_number: int
    description: str
    material: str
    quantity: int
    diameter_mm: float
    thickness_mm: float
    radius1_mm: Optional[float]
    radius2_mm: Optional[float]
    mass_kg: Optional[float]
    cost_estimate: Optional[float]
    notes: str


def generate_bom(system: OpticalSystem, filepath, format: str = "text") -> None:
    """Write the BOM as text or CSV."""
    items = _build_bom_items(system)
    filepath = Path(filepath)
    if format == "csv":
        _write_csv_bom(items, filepath)
    else:
        _write_text_bom(items, filepath)


def _build_bom_items(system: OpticalSystem) -> list:
    items = []
    k = 0
    for comp in system.components:
        if comp.type not in ("thin_lens", "thick_lens"):
            continue
        k += 1
        D = comp.aperture_diameter
        notes = []
        if comp.type == "thick_lens":
            t = comp.thickness
            r1 = comp.radius1 * 1e3 if comp.radius1 else None
            r2 = comp.radius2 * 1e3 if comp.radius2 else None
        else:
            n = refractive_index(comp.material, system.analysis_settings.wavelength)
            R = 2.0 * (n - 1.0) * comp.focal_length
            h = D / 2.0
            t = (
                2.0 * (abs(R) - math.sqrt(R * R - h * h))
                if abs(R) > h
                else float("nan")
            )
            r1, r2 = R * 1e3, -R * 1e3
            notes.append("ideal thin lens: equiconvex equivalent, zero edge thickness")
        density = get_material(comp.material).density
        mass = (
            element_blank_mass(D, t, density)
            if density is not None and math.isfinite(t)
            else None
        )
        price = unit_price_per_kg(comp.material)
        cost = mass * price if (mass is not None and price is not None) else None
        data = get_glass_data(comp.material)
        if data is not None and data.relative_price is not None:
            notes.append(f"vendor relative price {data.relative_price:g}")
        items.append(
            BOMItem(
                item_number=k,
                description=f"Lens element {comp.id}",
                material=comp.material,
                quantity=1,
                diameter_mm=D * 1e3,
                thickness_mm=t * 1e3,
                radius1_mm=r1,
                radius2_mm=r2,
                mass_kg=mass,
                cost_estimate=cost,
                notes="; ".join(notes),
            )
        )
    return items


def _fmt(v, spec, none="-"):
    return format(v, spec) if v is not None else none


def _write_text_bom(items: list, filepath: Path) -> None:
    L = [
        "=" * 96,
        "BILL OF MATERIALS",
        "=" * 96,
        "",
        f"{'Item':<5} {'Description':<22} {'Material':<12} {'Dia(mm)':>9} {'T(mm)':>8} "
        f"{'R1(mm)':>10} {'R2(mm)':>10} {'Mass(kg)':>9} {'Cost':>9}",
        "-" * 96,
    ]
    total, priced = 0.0, True
    for it in items:
        L.append(
            f"{it.item_number:<5} {it.description:<22} {it.material:<12} {it.diameter_mm:>9.3f} "
            f"{it.thickness_mm:>8.3f} {_fmt(it.radius1_mm, '10.3f', 'flat'):>10} "
            f"{_fmt(it.radius2_mm, '10.3f', 'flat'):>10} {_fmt(it.mass_kg, '9.4f'):>9} "
            f"{_fmt(it.cost_estimate, '9.2f'):>9}"
        )
        if it.notes:
            L.append(f"      {it.notes}")
        if it.cost_estimate is None:
            priced = False
        else:
            total += it.cost_estimate
    L += [
        "-" * 96,
        (
            f"{'TOTAL material cost':<80} {total:>9.2f}"
            if priced and items
            else "TOTAL material cost: not available (record quotes or a reference price)"
        ),
        "",
        "Masses are bare cylindrical blanks from the vendor density. Surface quality,",
        "coatings and tolerances are not specified by the optical design.",
    ]
    filepath.write_text("\n".join(L))


def _write_csv_bom(items: list, filepath: Path) -> None:
    L = [
        "Item,Description,Material,Quantity,Diameter_mm,Thickness_mm,Radius1_mm,Radius2_mm,Mass_kg,Cost,Notes"
    ]
    for it in items:
        L.append(
            ",".join(
                [
                    str(it.item_number),
                    it.description,
                    it.material,
                    str(it.quantity),
                    f"{it.diameter_mm:.4f}",
                    f"{it.thickness_mm:.4f}",
                    _fmt(it.radius1_mm, ".4f", ""),
                    _fmt(it.radius2_mm, ".4f", ""),
                    _fmt(it.mass_kg, ".6f", ""),
                    _fmt(it.cost_estimate, ".2f", ""),
                    '"' + it.notes.replace('"', "'") + '"',
                ]
            )
        )
    filepath.write_text("\n".join(L))
