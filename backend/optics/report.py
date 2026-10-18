"""
Project tools: design comparison, exportable plots, and engineering
reports (Phase 8).

This module produces human-facing artifacts from the validated optics
engine output:

    - compare_systems(): a side-by-side comparison of two designs.
    - system_spot_svg(): an SVG string of the spot diagram (exportable).
    - engineering_report_markdown(): a Markdown engineering report.

No optical math lives here; every number comes from the optics modules.

All values are in SI base units (meters, radians).
"""

from typing import Optional

from .models import OpticalSystem
from .analysis import analyze_system


def _summary_dict(system: OpticalSystem, label: str) -> dict:
    """Build a compact summary of one system's analysis."""
    analysis = analyze_system(system)
    return {
        "label": label,
        "magnification": analysis.magnification,
        "efl_mm": analysis.effective_focal_length * 1000.0,
        "f_number": analysis.f_number,
        "numerical_aperture": analysis.numerical_aperture,
        "rms_spot_um": analysis.rms_spot_radius * 1e6,
        "image_distance_mm": analysis.image_distance * 1000.0,
        "working_distance_mm": analysis.working_distance * 1000.0,
        "is_image_real": analysis.is_image_real,
        "is_image_inverted": analysis.is_image_inverted,
        "num_components": len(system.components),
    }


# ---------------------------------------------------------------------------
# Design comparison
# ---------------------------------------------------------------------------


def compare_systems(
    system_a: OpticalSystem,
    system_b: OpticalSystem,
    label_a: str = "Design A",
    label_b: str = "Design B",
) -> dict:
    """
    Compare two optical systems side by side.

    Args:
        system_a: First design.
        system_b: Second design.
        label_a: Name for the first design.
        label_b: Name for the second design.

    Returns:
        Dict with:
            - "rows": list of {"metric", "a", "b", "advantage"} where
              advantage is 'a', 'b', or 'tie'
            - "summary_a", "summary_b": the per-system summaries
    """
    sa = _summary_dict(system_a, label_a)
    sb = _summary_dict(system_b, label_b)

    # Metrics where lower is better (RMS spot); the rest higher/equal is
    # not obviously "better" so we leave advantage neutral except for RMS.
    rows: list[dict] = []
    for key, label in [
        ("magnification", "Magnification"),
        ("efl_mm", "Effective focal length (mm)"),
        ("f_number", "F-number"),
        ("numerical_aperture", "Numerical aperture"),
        ("rms_spot_um", "RMS spot radius (um)"),
        ("image_distance_mm", "Image distance (mm)"),
        ("working_distance_mm", "Working distance (mm)"),
        ("num_components", "Number of components"),
    ]:
        av, bv = sa[key], sb[key]
        advantage = "a" if av < bv else ("b" if bv < av else "tie")
        rows.append(
            {
                "metric": label,
                "a": av,
                "b": bv,
                "advantage": advantage,
            }
        )

    return {"rows": rows, "summary_a": sa, "summary_b": sb}


# ---------------------------------------------------------------------------
# Exportable plot (SVG spot diagram)
# ---------------------------------------------------------------------------


def system_spot_svg(
    system: OpticalSystem,
    width: int = 320,
    height: int = 320,
) -> str:
    """
    Render the spot diagram as an SVG string.

    Draws the real-ray spot (2D, about its centroid) at full field. The returned SVG can be saved to a file or
    embedded in an HTML/Markdown document.

    Args:
        system: The optical system.
        width: SVG width in pixels.
        height: SVG height in pixels.

    Returns:
        An SVG XML string.
    """
    analysis = analyze_system(system)
    pts = analysis.spot_points  # real rays, relative to the centroid
    margin = 24
    half = max((max(abs(p[0]), abs(p[1])) for p in pts), default=0.0) or 1e-9
    scale = (min(width, height) / 2.0 - margin) / half
    cx, cy = width / 2.0, height / 2.0
    circles = "".join(
        f'<circle cx="{cx + p[0] * scale:.1f}" cy="{cy - p[1] * scale:.1f}" r="2" fill="#2563eb"/>'
        for p in pts
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
        f'<line x1="{margin}" y1="{cy:.1f}" x2="{width - margin}" y2="{cy:.1f}" '
        f'stroke="#d1d5db" stroke-dasharray="4 4"/>'
        f'<line x1="{cx:.1f}" y1="{margin}" x2="{cx:.1f}" y2="{height - margin}" '
        f'stroke="#d1d5db" stroke-dasharray="4 4"/>'
        f'<text x="{margin}" y="{height - 6}" font-size="10" fill="#6b7280">'
        f"{len(pts)} real rays at full field, RMS {analysis.rms_spot_radius * 1e6:.2f} um, "
        f"half-width {half * 1e6:.2f} um</text>"
        f"{circles}"
        f"</svg>"
    )


# ---------------------------------------------------------------------------
# Engineering report (Markdown)
# ---------------------------------------------------------------------------


def engineering_report_markdown(
    system_a: Optional[OpticalSystem] = None,
    system_b: Optional[OpticalSystem] = None,
    label_a: str = "Design A",
    label_b: str = "Design B",
    include_svg: bool = False,
) -> str:
    """
    Generate a Markdown engineering report for one or two designs.

    Args:
        system_a: The primary design (required).
        system_b: Optional second design for a comparison report.
        label_a: Name for the primary design.
        label_b: Name for the second design.
        include_svg: Whether to embed the spot-diagram SVG.

    Returns:
        A Markdown string suitable for saving to a .md file.
    """
    if system_a is None:
        raise ValueError("system_a is required for an engineering report.")

    sa = _summary_dict(system_a, label_a)
    lines: list[str] = []
    lines.append(f"# Engineering Report")
    lines.append("")
    lines.append(
        "Values at the analysis wavelength; spot and NA from real rays, other quantities paraxial."
    )
    lines.append("")

    def add_summary(s, title):
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| Magnification | {s['magnification']:.3f} |")
        lines.append(f"| Effective focal length | {s['efl_mm']:.1f} mm |")
        lines.append(f"| F-number | f/{s['f_number']:.1f} |")
        lines.append(f"| Numerical aperture | {s['numerical_aperture']:.3f} |")
        lines.append(f"| RMS spot radius | {s['rms_spot_um']:.2f} um |")
        lines.append(f"| Image distance | {s['image_distance_mm']:.1f} mm |")
        lines.append(f"| Working distance | {s['working_distance_mm']:.1f} mm |")
        lines.append(f"| Image is real | {'yes' if s['is_image_real'] else 'no'} |")
        lines.append(
            f"| Image is inverted | {'yes' if s['is_image_inverted'] else 'no'} |"
        )
        lines.append(f"| Components | {s['num_components']} |")
        lines.append("")

    add_summary(sa, label_a)
    if include_svg:
        lines.append(f"### Spot diagram")
        lines.append("")
        lines.append(f"```svg")
        lines.append(system_spot_svg(system_a))
        lines.append("```")
        lines.append("")

    if system_b is not None:
        sb = _summary_dict(system_b, label_b)
        add_summary(sb, label_b)
        cmp = compare_systems(system_a, system_b, label_a, label_b)
        lines.append(f"## Comparison")
        lines.append("")
        lines.append("| Metric | {0} | {1} | Advantage |".format(label_a, label_b))
        lines.append("| --- | --- | --- | --- |")
        for row in cmp["rows"]:
            a = f"{row['a']:.3f}"
            b = f"{row['b']:.3f}"
            adv = {"a": label_a, "b": label_b, "tie": "tie"}[row["advantage"]]
            lines.append(f"| {row['metric']} | {a} | {b} | {adv} |")
        lines.append("")

    return "\n".join(lines)
