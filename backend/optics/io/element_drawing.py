"""
ISO 10110 element drawings of a prescription.

Each glass element (a pair of surfaces with glass between them; a
cemented group gives one drawing per glass) gets:

- a to-scale cross-section (SVG) with the clear aperture, the outer
  diameter, centre and edge thickness;
- the ISO 10110 data table: per surface the radius with its sense (CX/CC),
  the clear aperture (⌀e), 3/ surface form, 4/ centring, 5/ surface
  imperfections and the coating; for the material the glass, nd and νd
  with their tolerances and 0/ 1/ 2/ material imperfections.

Design values come from the lens. Tolerance values come from the
tolerance set (``optics.tolerancing``, default_tolerances unless given):
DLF -> 3/ power in fringes, DLT -> thickness, DLN/DLV -> index and Abbe
tolerance, TRX/TRY and the element tilts -> 4/ centring (arc minutes).
Codes the design does not set (surface imperfections, bubbles,
inhomogeneity, stress birefringence, irregularity) print as "—" unless
supplied in ``notes``, keyed "5/", "1/", "2/", "0/", "irregularity".
"""

from __future__ import annotations

import math
from html import escape
from typing import Optional

from ..lens_data import LensData, LensSurface


def _glass_elements(lens: LensData) -> list[tuple[int, int]]:
    """(front, back surface) of each glass: a surface followed by glass."""
    out = []
    surfaces = lens.surfaces
    for i in range(len(surfaces) - 1):
        s = surfaces[i]
        if s.surface_type in ("coordinate_break", "component", "paraxial"):
            continue
        if s.material is None or s.material == "MIRROR":
            continue
        j = i + 1
        while j < len(surfaces) and surfaces[j].surface_type == "coordinate_break":
            j += 1
        if j < len(surfaces):
            out.append((i, j))
    return out


def _sag(surface: LensSurface, h: float) -> float:
    """Sag at height h; beyond the surface's clear aperture the element
    continues as a flat land (the sag at the clear aperture)."""
    from ..lens_optimize import _surface_sag

    semi = surface.semi_diameter
    return float(_surface_sag(surface, min(h, semi) if semi else h))


def _semi(surface: LensSurface) -> float:
    return float(surface.semi_diameter or 0.0)


def _sense(radius: float, front: bool) -> str:
    """CX/CC for a surface as seen from outside the element."""
    if not radius:
        return "plano"
    convex = radius > 0 if front else radius < 0
    return "CX" if convex else "CC"


def _tolerance_index(tolerances: list) -> dict:
    out: dict = {}
    for t in tolerances:
        d = t if isinstance(t, dict) else t.model_dump()
        out.setdefault((d["kind"], d["surface"]), d["limit"])
        if d.get("last_surface") is not None:
            out.setdefault((d["kind"], "element", d["surface"]), d["limit"])
    return out


def _minutes(rad: float) -> str:
    return f"{math.degrees(rad) * 60:.1f}′"


def _profile(surface: LensSurface, z0: float, h_max: float, n: int = 41) -> list:
    """(z, h) points of a surface profile from -h_max to h_max."""
    pts = []
    for k in range(n):
        h = -h_max + 2 * h_max * k / (n - 1)
        pts.append((z0 + _sag(surface, abs(h)), h))
    return pts


def _svg(
    front: LensSurface, back: LensSurface, ct: float, outer: float, clear: float
) -> str:
    """To-scale cross-section with dimensions (mm labels)."""
    h = outer / 2
    p1 = _profile(front, 0.0, h)
    p2 = _profile(back, ct, h)
    zs = [p[0] for p in p1 + p2]
    zmin, zmax = min(zs), max(zs)
    W, H, pad = 360.0, 260.0, 48.0
    scale = min(
        (W - 2 * pad) / max(zmax - zmin, 1e-9), (H - 2 * pad) / max(outer, 1e-9)
    )
    cx = W / 2 - (zmin + zmax) / 2 * scale
    cy = H / 2

    def xy(z, y):
        return f"{cx + z * scale:.2f},{cy - y * scale:.2f}"

    outline = (
        " ".join(xy(z, y) for z, y in p1)
        + " "
        + " ".join(xy(z, y) for z, y in reversed(p2))
    )
    ca1 = (_sag(front, clear / 2), clear / 2)
    edge = ct - _sag(front, h) + _sag(back, h)
    top = cy - h * scale
    bottom = cy + h * scale
    xa, xb = cx, cx + ct * scale
    e1 = cx + _sag(front, h) * scale
    e2 = cx + (ct + _sag(back, h)) * scale
    right = max(e2, xb) + 22
    mm = 1e3
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
        f'width="{W:.0f}" height="{H:.0f}" font-family="sans-serif" font-size="10">',
        '<defs><marker id="a" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z"/></marker></defs>',
        f'<polygon points="{outline}" fill="#dbeafe" stroke="#1e3a8a" stroke-width="1.2"/>',
        f'<line x1="{cx + zmin * scale - 14:.1f}" y1="{cy}" x2="{cx + zmax * scale + 14:.1f}" '
        f'y2="{cy}" stroke="#555" stroke-dasharray="8 3 2 3" stroke-width="0.6"/>',
        # centre thickness, below the element
        f'<line x1="{xa:.1f}" y1="{bottom + 18:.1f}" x2="{xb:.1f}" y2="{bottom + 18:.1f}" '
        'stroke="#000" stroke-width="0.6" marker-start="url(#a)" marker-end="url(#a)"/>',
        f'<text x="{(xa + xb) / 2:.1f}" y="{bottom + 31:.1f}" text-anchor="middle">'
        f"{ct * mm:.3f}</text>",
        # edge thickness, above
        f'<line x1="{e1:.1f}" y1="{top - 12:.1f}" x2="{e2:.1f}" y2="{top - 12:.1f}" '
        'stroke="#000" stroke-width="0.6" marker-start="url(#a)" marker-end="url(#a)"/>',
        f'<text x="{(e1 + e2) / 2:.1f}" y="{top - 17:.1f}" text-anchor="middle">'
        f"{edge * mm:.3f} edge</text>",
        # outer diameter, right
        f'<line x1="{right:.1f}" y1="{top:.1f}" x2="{right:.1f}" y2="{bottom:.1f}" '
        'stroke="#000" stroke-width="0.6" marker-start="url(#a)" marker-end="url(#a)"/>',
        f'<text x="{right + 4:.1f}" y="{cy - 3:.1f}">⌀{outer * mm:.3f}</text>',
        # clear aperture marks on the front surface
        f'<line x1="{cx + ca1[0] * scale - 8:.1f}" y1="{cy - ca1[1] * scale:.1f}" '
        f'x2="{cx + ca1[0] * scale - 2:.1f}" y2="{cy - ca1[1] * scale:.1f}" stroke="#b91c1c"/>',
        f'<line x1="{cx + ca1[0] * scale - 8:.1f}" y1="{cy + ca1[1] * scale:.1f}" '
        f'x2="{cx + ca1[0] * scale - 2:.1f}" y2="{cy + ca1[1] * scale:.1f}" stroke="#b91c1c"/>',
        "</svg>",
    ]
    return "".join(lines)


def _coating_text(surface: LensSurface) -> str:
    c = surface.coating
    if c is None:
        return "uncoated"
    layers = getattr(c, "layers", None) or []
    names = [getattr(layer, "material", None) or f"n={layer.n:g}" for layer in layers]
    return f"{len(layers)}-layer AR ({', '.join(names)})" if layers else "coated"


def element_drawings(
    lens: LensData,
    tolerances: Optional[list] = None,
    edge_margin: float = 1e-3,
    notes: Optional[dict] = None,
) -> list[dict]:
    """
    ISO 10110 drawing data for every glass element.

    Args:
        lens: The prescription (semi-diameters are resolved if automatic).
        tolerances: Tolerance set (default: tolerancing.default_tolerances).
        edge_margin: Added to the clear diameter for the outer diameter (m).
        notes: Values for codes the design does not set: "0/", "1/",
            "2/", "5/", "irregularity".

    Returns:
        Per element: name, surfaces, glass, centre/edge thickness, clear and
        outer diameter (m), the ISO rows {"left", "material", "right"} as
        (label, value) pairs, the SVG and an HTML fragment.
    """
    from ..lens_data import resolve
    from ..materials import abbe_number, refractive_index
    from .. import tolerancing as tol

    lens = resolve(lens)
    if tolerances is None:
        tolerances = tol.default_tolerances(lens)
    tix = _tolerance_index(tolerances)
    notes = notes or {}
    irr = notes.get("irregularity", "—")
    dash = "—"
    out = []
    for n, (i, j) in enumerate(_glass_elements(lens), start=1):
        front, back = lens.surfaces[i], lens.surfaces[j]
        glass = front.material or ""
        clear = 2 * max(_semi(front), _semi(back))
        if clear <= 0:
            continue
        outer = clear + edge_margin
        ct = front.thickness
        edge = ct - _sag(front, outer / 2) + _sag(back, outer / 2)
        element_tilt = tix.get(("BTX", "element", i)) or tix.get(("BTY", "element", i))

        def surface_rows(s: LensSurface, k: int, is_front: bool) -> list:
            fr = tix.get(("DLF", k))
            r_tol = tix.get(("DLR", k))
            tilt = tix.get(("TRX", k)) or tix.get(("TRY", k)) or element_tilt
            radius = (
                "∞ (plano)"
                if not s.radius
                else f"R {abs(s.radius) * 1e3:.4f} {_sense(s.radius, is_front)}"
                + (f" ±{r_tol * 1e3:.4f}" if r_tol else "")
            )
            return [
                ("Surface", f"S{k}" + (f" {s.label}" if s.label else "")),
                ("Radius (mm)", radius),
                ("⌀e (mm)", f"{2 * _semi(s) * 1e3:.3f}"),
                ("3/", f"3/{fr:g}({irr})" if fr else dash),
                ("4/", f"4/{_minutes(tilt)}" if tilt else dash),
                ("5/", notes.get("5/", dash)),
                ("Coating", _coating_text(s)),
            ]

        ct_tol = tix.get(("DLT", i))
        dn = tix.get(("DLN", i))
        dv = tix.get(("DLV", i))
        try:
            nd = float(refractive_index(glass, 587.5618e-9))
        except Exception:
            nd = float("nan")
        vd = abbe_number(glass) if glass else None
        material = [
            ("Glass", glass),
            ("nd", f"{nd:.5f}" + (f" ±{dn:g}" if dn else "")),
            ("νd", (f"{vd:.2f}" if vd else dash) + (f" ±{dv:.2f}" if dv else "")),
            ("0/", notes.get("0/", dash)),
            ("1/", notes.get("1/", dash)),
            ("2/", notes.get("2/", dash)),
            (
                "Centre thickness (mm)",
                f"{ct * 1e3:.3f}" + (f" ±{ct_tol * 1e3:.3f}" if ct_tol else ""),
            ),
            ("Outer ⌀ (mm)", f"{outer * 1e3:.3f}"),
        ]
        left = surface_rows(front, i, True)
        right = surface_rows(back, j, False)
        svg = _svg(front, back, ct, outer, clear)
        out.append(
            {
                "name": front.element or f"Element {n}",
                "surfaces": [i, j],
                "glass": glass,
                "center_thickness": ct,
                "edge_thickness": edge,
                "clear_diameter": clear,
                "outer_diameter": outer,
                "left": left,
                "material": material,
                "right": right,
                "svg": svg,
                "html": _html(
                    front.element or f"Element {n}", svg, left, material, right
                ),
            }
        )
    return out


def _column(title: str, rows: list) -> str:
    body = "".join(
        f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in rows
    )
    return f'<table class="iso"><caption>{escape(title)}</caption>{body}</table>'


def _html(name: str, svg: str, left: list, material: list, right: list) -> str:
    return (
        f'<section class="drawing"><h3>{escape(name)}</h3>{svg}'
        '<div class="iso-columns">'
        f"{_column('Left surface', left)}{_column('Material', material)}"
        f"{_column('Right surface', right)}</div>"
        '<p class="note">Dimensions in mm. ISO 10110: 3/ power (irregularity) in '
        "fringes at 546 nm; 4/ centring tilt; — = not specified by the design.</p>"
        "</section>"
    )
