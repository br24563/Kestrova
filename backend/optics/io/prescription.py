"""
Sequential prescription (surface table) <-> OpticalSystem.

A prescription row describes one surface the way Code V and Zemax do:
radius, conic, even aspheric coefficients (A4, A6, ...), the glass after the
surface (None = air, "MIRROR" = reflecting), the thickness to the next
surface, the clear semi-aperture and whether it is the aperture stop. All
lengths are in meters here; the file writers convert units.

Thin lenses (ideal lenses) have no surface form: Zemax has a PARAXIAL
surface for them, Code V does not, so the Code V writer rejects them.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import (
    OpticalSystem, ThinLens, ThickLens, SphericalSurface, ApertureStop, Mirror,
    Object, ImagePlane, AnalysisSettings,
)
from ..advanced_surfaces import AsphericSurface
from ..materials import MATERIALS


@dataclass
class Row:
    radius: float = 0.0               # 0 = flat
    conic: float = 0.0
    asphere: list = field(default_factory=list)   # A4, A6, ...
    glass: Optional[str] = None       # medium after; "MIRROR" for a mirror
    thickness: float = 0.0            # to the next surface (signed)
    semi_aperture: Optional[float] = None
    stop: bool = False
    paraxial_focal_length: Optional[float] = None  # ideal lens (Zemax PARAXIAL)
    label: str = ""


def system_to_rows(system: OpticalSystem) -> tuple[list, float, Any]:
    """
    Surface rows of a system, the object distance (object to first surface)
    and the system's first-order data (:class:`optics.raytrace.FirstOrder`).

    Raises ValueError for components without a Code V/Zemax standard-surface
    equivalent written by these exporters.
    """
    from .. import raytrace as rt
    from ..models import Mirror as _M
    comps = rt.ordered_components(system)
    rows: list[Row] = []
    zs: list[float] = []
    stop_pending = None
    medium = None
    direction = 1
    for c in comps:
        if isinstance(c, ThinLens):
            rows.append(Row(semi_aperture=c.aperture_diameter / 2, glass=medium,
                            paraxial_focal_length=c.focal_length, label=c.id))
            zs.append(c.position)
        elif isinstance(c, ThickLens):
            outer = medium
            rows.append(Row(radius=c.radius1, glass=c.material,
                            semi_aperture=c.aperture_diameter / 2, label=f"{c.id}.front"))
            zs.append(c.position)
            rows.append(Row(radius=c.radius2, glass=outer,
                            semi_aperture=c.aperture_diameter / 2, label=f"{c.id}.back"))
            zs.append(c.position + direction * c.thickness)
        elif isinstance(c, SphericalSurface):
            medium = None if c.material.lower() == "air" else c.material
            rows.append(Row(radius=c.radius, glass=medium,
                            semi_aperture=(c.aperture_diameter / 2 if c.aperture_diameter else None),
                            label=c.id))
            zs.append(c.position)
            continue
        elif isinstance(c, AsphericSurface):
            medium = None if (not c.material or c.material.lower() == "air") else c.material
            rows.append(Row(radius=c.radius, conic=c.conic, asphere=list(c.aspheric_coeffs),
                            glass=medium, semi_aperture=c.aperture_diameter / 2, label=c.id))
            zs.append(c.position)
            continue
        elif isinstance(c, ApertureStop):
            rows.append(Row(semi_aperture=c.diameter / 2, glass=medium, stop=True, label=c.id))
            zs.append(c.position)
        elif isinstance(c, _M):
            rows.append(Row(radius=c.radius, conic=c.conic, glass="MIRROR",
                            semi_aperture=(c.aperture_diameter or c.width) / 2, label=f"{c.id}.mirror"))
            zs.append(c.position)
            direction = -direction
        else:
            raise ValueError(
                f"Component '{c.id}' ({type(c).__name__}) has no standard-surface "
                "equivalent in this exporter")
    if not rows:
        raise ValueError("System has no surfaces")
    for k in range(len(rows) - 1):
        rows[k].thickness = zs[k + 1] - zs[k]
    rows[-1].thickness = system.image_plane.position - zs[-1]
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    # mark the stop actually used by the engine
    if not any(r.stop for r in rows):
        rows[_row_of_surface(seq, fo.stop_index, rows)].stop = True
    return rows, zs[0] - system.object.position, fo


def _row_of_surface(seq, surface_index, rows) -> int:
    label = seq.surfaces[surface_index].label
    for k, r in enumerate(rows):
        if r.label == label:
            return k
    raise ValueError(f"Stop surface '{label}' not found in the prescription")


_VENDOR_SUFFIX = re.compile(r"_(SCHOTT|OHARA|HOYA|CDGM|HIKARI|SUMITA)$", re.I)


def resolve_glass(name: str) -> str:
    """
    Map a glass name from a design file to a catalog name: exact match,
    else without a vendor suffix (Code V 'NBK7_SCHOTT'), ignoring hyphens
    and case. Raises ValueError if the glass is not in the catalog.
    """
    if name in MATERIALS:
        return name
    base = _VENDOR_SUFFIX.sub("", name)
    key = re.sub(r"[-_ ]", "", base).upper()
    matches = [m for m in MATERIALS if re.sub(r"[-_ ]", "", m).upper() == key]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"Glass '{name}' is not in the material catalog")
    raise ValueError(f"Glass '{name}' is ambiguous: {matches}")


def rows_to_system(rows: list, object_distance: float, object_height: float,
                   wavelengths: list, reference_index: int = 0,
                   name: str = "") -> OpticalSystem:
    """
    Build an OpticalSystem from surface rows. The first surface is placed at
    z = 0. Singlets in air become ThickLens; other refracting surfaces become
    SphericalSurface / AsphericSurface; reflecting surfaces become Mirror.
    """
    comps: list = []
    z = 0.0
    zs = []
    for r in rows:
        zs.append(z)
        z += r.thickness
    image_z = z
    i = 0
    medium = None
    while i < len(rows):
        r = rows[i]
        cid = r.label.split(".")[0] if r.label else f"S{i + 1}"
        if r.stop and r.radius == 0 and r.paraxial_focal_length is None and (r.glass or None) == medium:
            comps.append(ApertureStop(id=cid, position=zs[i], diameter=2 * (r.semi_aperture or 0.0)))
            i += 1
            continue
        if r.stop and r.semi_aperture:
            comps.append(ApertureStop(id=f"{cid}_stop", position=zs[i], diameter=2 * r.semi_aperture))
        if r.paraxial_focal_length is not None:
            comps.append(ThinLens(id=cid, position=zs[i], focal_length=r.paraxial_focal_length,
                                  aperture_diameter=2 * (r.semi_aperture or 0.0125)))
            i += 1
            continue
        if r.glass == "MIRROR":
            comps.append(Mirror(id=cid, position=zs[i], width=2 * (r.semi_aperture or 0.0125),
                                radius=r.radius, conic=r.conic))
            i += 1
            continue
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        simple = (r.conic == 0 and not r.asphere and r.glass and medium is None and nxt is not None
                  and nxt.glass is None and nxt.conic == 0 and not nxt.asphere and not nxt.stop
                  and nxt.paraxial_focal_length is None and r.thickness > 0)
        if simple:
            assert nxt is not None
            semi = max(r.semi_aperture or 0.0, nxt.semi_aperture or 0.0) or 0.0125
            comps.append(ThickLens(id=cid, position=zs[i], radius1=r.radius, radius2=nxt.radius,
                                   thickness=r.thickness, aperture_diameter=2 * semi,
                                   material=r.glass))
            i += 2
            continue
        mat = r.glass or "air"
        if r.conic or r.asphere:
            comps.append(AsphericSurface(id=cid, position=zs[i], radius=r.radius, conic=r.conic,
                                         aspheric_coeffs=list(r.asphere),
                                         aperture_diameter=2 * (r.semi_aperture or 0.0125),
                                         material=mat))
        else:
            comps.append(SphericalSurface(id=cid, position=zs[i], radius=r.radius, thickness=r.thickness,
                                          material=mat,
                                          aperture_diameter=(2 * r.semi_aperture if r.semi_aperture else None)))
        medium = r.glass
        i += 1
    wl = wavelengths[reference_index] if wavelengths else 587.5618e-9
    return OpticalSystem(
        components=comps, wavelengths=wavelengths or [wl],
        object=Object(position=-object_distance, height=object_height),
        image_plane=ImagePlane(position=image_z),
        analysis_settings=AnalysisSettings(wavelength=wl),
    )
