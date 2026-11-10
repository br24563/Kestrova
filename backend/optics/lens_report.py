"""
Design report of a prescription: one self-contained HTML page (inline
CSS and SVG, no external files) laid out for printing to PDF.

Sections: system data, first-order properties, the prescription, field
performance (chief ray, distortion, RMS spot, vignetting), polychromatic
MTF, third-order aberrations, the tolerance budget (sensitivities and the
predicted RMS wavefront) and ISO 10110 element drawings.

No optical math lives here; every number comes from the optics modules.
"""

from __future__ import annotations

import datetime as _dt
import math
from html import escape
from typing import Optional

from .lens_data import LensData, resolve, to_system

_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]

_CSS = """
body{font-family:Helvetica,Arial,sans-serif;color:#111;margin:24px;font-size:11px}
h1{font-size:20px;margin:0 0 2px}h2{font-size:14px;border-bottom:1px solid #999;
margin:22px 0 8px;padding-bottom:2px;break-after:avoid}h3{font-size:12px;margin:12px 0 4px}
.meta{color:#555;margin-bottom:12px}
table{border-collapse:collapse;margin:4px 0}th,td{border:1px solid #ccc;padding:2px 6px}
th{background:#f3f4f6;text-align:left;font-weight:600}td.n{text-align:right;
font-family:Consolas,Menlo,monospace}
.kv th{width:200px}.drawing{break-inside:avoid;margin-bottom:14px}
.iso-columns{display:flex;gap:8px;align-items:flex-start}.iso caption{font-weight:600;
text-align:left}.iso th{width:110px}.note{color:#555;font-size:10px}
section{break-inside:auto}svg{max-width:100%}
@media print{body{margin:0}h2{break-after:avoid}.drawing,.plot{break-inside:avoid}}
"""


def _mm(v: Optional[float], digits: int = 4) -> str:
    if v is None or not math.isfinite(v):
        return "∞" if v is not None else "—"
    return f"{v * 1e3:.{digits}f}"


def _num(v: Optional[float], fmt: str = ".5g") -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and not math.isfinite(v):
        return "∞"
    return format(v, fmt)


def _table(header: list[str], rows: list[list], numeric_from: int = 1) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in header)
    body = []
    for r in rows:
        cells = "".join(
            f'<td class="{"n" if k >= numeric_from else ""}">{escape(str(c))}</td>'
            for k, c in enumerate(r)
        )
        body.append(f"<tr>{cells}</tr>")
    return f"<table><tr>{head}</tr>{''.join(body)}</table>"


def _kv(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<tr><th>{escape(k)}</th><td class="n">{escape(v)}</td></tr>' for k, v in rows
    )
    return f'<table class="kv">{body}</table>'


def line_plot_svg(
    series: list[dict],
    x_label: str,
    y_label: str,
    width: int = 560,
    height: int = 300,
    y_range: Optional[tuple[float, float]] = None,
) -> str:
    """A simple SVG line plot. Each series: label, x, y, color, dashed."""
    pad_l, pad_r, pad_t, pad_b = 48, 140, 12, 36
    xs = [x for s in series for x in s["x"]]
    ys = [y for s in series for y in s["y"]]
    if not xs:
        return ""
    x0, x1 = min(xs), max(xs)
    y0, y1 = y_range if y_range else (min(ys), max(ys))
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y1 = y0 + 1
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b

    def px(x):
        return pad_l + (x - x0) / (x1 - x0) * pw

    def py(y):
        return pad_t + (1 - (y - y0) / (y1 - y0)) * ph

    parts = [
        f'<svg class="plot" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="sans-serif" font-size="10">',
        f'<rect x="{pad_l}" y="{pad_t}" width="{pw}" height="{ph}" fill="none" stroke="#999"/>',
    ]
    for k in range(6):
        gx = x0 + (x1 - x0) * k / 5
        gy = y0 + (y1 - y0) * k / 5
        parts.append(
            f'<line x1="{px(gx):.1f}" y1="{pad_t}" x2="{px(gx):.1f}" y2="{pad_t + ph}" '
            'stroke="#eee"/>'
            f'<text x="{px(gx):.1f}" y="{pad_t + ph + 12}" text-anchor="middle">{gx:.3g}</text>'
            f'<line x1="{pad_l}" y1="{py(gy):.1f}" x2="{pad_l + pw}" y2="{py(gy):.1f}" '
            'stroke="#eee"/>'
            f'<text x="{pad_l - 4}" y="{py(gy) + 3:.1f}" text-anchor="end">{gy:.3g}</text>'
        )
    for k, s in enumerate(series):
        pts = " ".join(
            f"{px(x):.1f},{py(min(max(y, y0), y1)):.1f}" for x, y in zip(s["x"], s["y"])
        )
        dash = ' stroke-dasharray="5 3"' if s.get("dashed") else ""
        color = s.get("color", _COLORS[k % len(_COLORS)])
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.4"{dash}/>'
        )
        ly = pad_t + 10 + 13 * k
        parts.append(
            f'<line x1="{width - pad_r + 8}" y1="{ly - 3}" x2="{width - pad_r + 26}" '
            f'y2="{ly - 3}" stroke="{color}" stroke-width="1.4"{dash}/>'
            f'<text x="{width - pad_r + 30}" y="{ly}">{escape(s["label"])}</text>'
        )
    parts.append(
        f'<text x="{pad_l + pw / 2}" y="{height - 6}" text-anchor="middle">'
        f"{escape(x_label)}</text>"
        f'<text transform="translate(12,{pad_t + ph / 2}) rotate(-90)" '
        f'text-anchor="middle">{escape(y_label)}</text></svg>'
    )
    return "".join(parts)


def _system_section(lens: LensData) -> str:
    wl = ", ".join(f"{w * 1e9:.2f}" for w in lens.wavelengths)
    weights = getattr(lens, "wavelength_weights", None)
    rows = [
        ("Wavelengths (nm)", wl),
        (
            "Wavelength weights",
            ", ".join(f"{w:g}" for w in weights) if weights else "equal",
        ),
        (
            "Object distance (mm)",
            "infinity" if lens.object_distance is None else _mm(lens.object_distance),
        ),
        (
            "Entrance pupil diameter (mm)",
            (
                "from the stop"
                if lens.entrance_pupil_diameter is None
                else _mm(lens.entrance_pupil_diameter)
            ),
        ),
    ]
    if lens.num_configurations > 1:
        rows.append(
            (
                "Configurations",
                ", ".join(lens.configuration_names) or str(lens.num_configurations),
            )
        )
    return "<h2>System data</h2>" + _kv(rows)


def _first_order_section(system) -> str:
    from . import raytrace as rt

    fo = rt.first_order(system)
    rows = [
        ("Effective focal length (mm)", _mm(fo.efl)),
        ("Back focal length (mm)", _mm(fo.bfl)),
        ("F-number", _num(fo.f_number)),
        ("Working F-number", _num(fo.working_f_number)),
        ("Image-space NA", _num(fo.na_image)),
        ("Entrance pupil diameter (mm)", _mm(2 * fo.entrance_pupil_semi_diameter)),
        ("Exit pupil position (mm, from image)", _mm(fo.exit_pupil_z - fo.image_z)),
        ("Paraxial image height (mm)", _mm(fo.image_height)),
        ("Magnification", _num(fo.magnification)),
    ]
    if fo.object_infinite:
        rows.append(("Half field angle (deg)", _num(math.degrees(fo.field_angle))))
    return "<h2>First-order properties</h2>" + _kv(rows)


def _prescription_section(lens: LensData) -> str:
    rows = []
    for i, s in enumerate(lens.surfaces):
        extra = []
        if s.conic:
            extra.append(f"k={s.conic:.6g}")
        if s.aspheric_coefficients:
            terms = [
                f"A{4 + 2 * k}={c:.4e}"
                for k, c in enumerate(s.aspheric_coefficients)
                if c
            ]
            extra.extend(terms)
        if s.coating is not None:
            extra.append("coated")
        if s.decenter_x or s.decenter_y or s.tilt_x or s.tilt_y:
            extra.append("decentred/tilted")
        name = f"{i}{' (stop)' if s.is_stop else ''}"
        rows.append(
            [
                name,
                s.surface_type,
                "∞" if not s.radius else _mm(s.radius),
                _mm(s.thickness),
                s.material or "",
                _mm(s.semi_diameter, 3) if s.semi_diameter else "auto",
                " ".join(extra),
            ]
        )
    return "<h2>Prescription</h2>" + _table(
        [
            "Surface",
            "Type",
            "Radius (mm)",
            "Thickness (mm)",
            "Material",
            "Semi-diameter (mm)",
            "Notes",
        ],
        rows,
        numeric_from=2,
    )


def _field_section(system) -> str:
    from .fields import field_summary

    fs = field_summary(system)
    angle = fs["field_type"] == "angle"
    rows = []
    for f in fs["fields"]:
        value = math.hypot(f["x"], f["y"])
        rows.append(
            [
                f["index"] + 1,
                f"{math.degrees(value):.3f}" if angle else _mm(value),
                _mm(math.hypot(*f["chief_ray"])),
                "—" if f["distortion"] is None else f"{f['distortion'] * 100:.4f}",
                f"{f['rms_spot'] * 1e6:.3f}",
                f"{f['vignetted_fraction'] * 100:.1f}",
            ]
        )
    return (
        "<h2>Field performance</h2>"
        + _table(
            [
                "Field",
                "Field (deg)" if angle else "Object height (mm)",
                "Chief ray height (mm)",
                "Distortion (%)",
                "RMS spot (µm)",
                "Vignetted (%)",
            ],
            rows,
        )
        + f'<p class="note">Weighted RMS spot: {fs["weighted_rms_spot"] * 1e6:.3f} µm (polychromatic).</p>'
    )


def _mtf_section(system, frequencies: Optional[list[float]]) -> str:
    from .fields import field_mtf, resolve_fields
    from .mtf_analysis import diffraction_limited_mtf

    _, fields = resolve_fields(system)
    series = []
    cutoff = None
    for k in range(len(fields)):
        m = field_mtf(system, k, frequencies)
        f = m["frequency_cyc_per_mm"]
        cutoff = m.get("cutoff_cyc_per_mm", cutoff)
        color = _COLORS[k % len(_COLORS)]
        series.append(
            {"label": f"F{k + 1} T", "x": f, "y": m["tangential"], "color": color}
        )
        series.append(
            {
                "label": f"F{k + 1} S",
                "x": f,
                "y": m["sagittal"],
                "color": color,
                "dashed": True,
            }
        )
    if cutoff:
        xs = series[0]["x"]
        dl = diffraction_limited_mtf([x / cutoff for x in xs])
        series.append({"label": "Diffraction", "x": xs, "y": list(dl), "color": "#111"})
    svg = line_plot_svg(
        series, "Spatial frequency (cycles/mm)", "MTF", y_range=(0.0, 1.0)
    )
    return "<h2>Polychromatic MTF</h2>" + svg


def _seidel_section(system) -> str:
    from .seidel import seidel_analysis

    s = seidel_analysis(system)
    sums = s.get("seidel_sums", {})
    names = {
        "S1": "Spherical",
        "S2": "Coma",
        "S3": "Astigmatism",
        "S4": "Petzval",
        "S5": "Distortion",
        "CL": "Axial colour",
        "CT": "Lateral colour",
    }
    rows = [[f"{k} {names.get(k, '')}", f"{v:.4e}"] for k, v in sums.items()]
    return "<h2>Third-order aberrations (Seidel sums, m)</h2>" + _table(
        ["Coefficient", "Value"], rows
    )


def _tolerance_section(lens: LensData, trials: int) -> str:
    from . import tolerancing as tol

    tols = tol.default_tolerances(lens)
    if not tols:
        return ""
    result = tol.analyze(lens, tols, trials=trials).to_dict()
    sens = sorted(
        result["sensitivities"],
        key=lambda d: -max(abs(d["change_plus"]), abs(d["change_minus"])),
    )
    rows = [
        [
            d["tolerance"],
            f"{d['limit']:.4g}",
            f"{d['change_plus']:+.4f}",
            f"{d['change_minus']:+.4f}",
        ]
        for d in sens[:20]
    ]
    pred = result["predicted"]
    pct = pred.get("percentiles", {})
    pct_rows = [
        (f"{k} % of builds below (waves RMS)", f"{v:.4f}") for k, v in pct.items()
    ]
    summary = _kv(
        [
            ("Nominal RMS wavefront (waves)", f"{result['nominal_rms']:.4f}"),
            ("RSS increase (waves)", f"{result['rss_increase']:.4f}"),
            ("Predicted mean (waves)", f"{pred['mean']:.4f}"),
            *pct_rows,
        ]
    )
    return (
        "<h2>Tolerance budget</h2>"
        + summary
        + "<h3>Largest sensitivities (change of RMS wavefront at the limits, waves)</h3>"
        + _table(["Tolerance", "Limit", "+ limit", "− limit"], rows)
        + f'<p class="note">Default tolerance set with back-focus compensation; '
        f"{result['trials']} Monte Carlo builds from the fitted model. Units: DLF fringes, "
        "DLT/DLX/DLY m, DLN index, DLV Abbe, TRX/TRY/BTX/BTY rad.</p>"
    )


def _drawings_section(lens: LensData) -> str:
    from .io.element_drawing import element_drawings

    drawings = element_drawings(lens)
    if not drawings:
        return ""
    return "<h2>Element drawings (ISO 10110)</h2>" + "".join(
        d["html"] for d in drawings
    )


def lens_report_html(
    lens: LensData,
    title: Optional[str] = None,
    configuration: int = 0,
    mtf: bool = True,
    frequencies: Optional[list[float]] = None,
    tolerances: bool = True,
    trials: int = 2000,
    drawings: bool = True,
    author: str = "",
) -> str:
    """
    The design report of a lens as a self-contained HTML document.

    Args:
        lens: The prescription.
        title: Report title (default: the lens name).
        configuration: Configuration analysed (multi-configuration lenses).
        mtf: Include the MTF plot.
        frequencies: MTF frequencies in cycles/mm (default: up to cutoff).
        tolerances: Include the tolerance budget (default tolerance set).
        trials: Monte Carlo builds for the predicted RMS wavefront.
        drawings: Include ISO 10110 element drawings.
        author: Printed under the title.
    """
    from . import __version__
    from .lens_data import configured

    if lens.num_configurations > 1:
        lens = configured(lens, configuration)
    lens = resolve(lens)
    system = to_system(lens)
    name = title or lens.name or "Lens"
    sections = [
        _system_section(lens),
        _first_order_section(system),
        _prescription_section(lens),
        _field_section(system),
    ]
    if mtf:
        sections.append(_mtf_section(system, frequencies))
    sections.append(_seidel_section(system))
    if tolerances:
        sections.append(_tolerance_section(lens, trials))
    if drawings:
        sections.append(_drawings_section(lens))
    date = _dt.date.today().isoformat()
    meta = f"Kestrova {__version__} · {date}" + (
        f" · {escape(author)}" if author else ""
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{escape(name)}</title><style>{_CSS}</style></head><body>"
        f'<h1>{escape(name)}</h1><div class="meta">{meta}</div>'
        + "".join(sections)
        + "</body></html>"
    )
