"""
Lens drawing generation.

Generates:
- 2D lens element drawings with dimensions
- ISO 10110 optical drawings
- Sag tables
- Manufacturing notes
"""

from typing import Optional
from pathlib import Path
import math

from ..models import OpticalSystem, ThinLens, ThickLens


def generate_lens_drawing(
    system: OpticalSystem,
    filepath: str | Path,
    format: str = 'svg',
) -> None:
    """
    Generate a 2D lens element drawing.
    
    Args:
        system: The optical system
        filepath: Output file path
        format: Output format ('svg' or 'text')
    """
    filepath = Path(filepath)
    
    if format == 'svg':
        _generate_svg_drawing(system, filepath)
    else:
        _generate_text_drawing(system, filepath)


def _generate_svg_drawing(system: OpticalSystem, filepath: Path) -> None:
    """Generate SVG lens drawing."""
    width = 800
    height = 400
    margin = 50
    
    # Calculate scale
    all_positions = [c.position for c in system.components]
    min_z = min(all_positions) if all_positions else 0
    max_z = max(all_positions) if all_positions else 1
    system_length = max_z - min_z if max_z > min_z else 1
    scale = (width - 2 * margin) / system_length
    
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{width//2}" y="30" text-anchor="middle" font-size="16" font-weight="bold">Lens Element Drawing</text>',
    ]
    
    # Draw optical axis
    axis_y = height // 2
    svg_lines.append(f'<line x1="{margin}" y1="{axis_y}" x2="{width-margin}" y2="{axis_y}" stroke="#999" stroke-width="1" stroke-dasharray="5,5"/>')
    
    # Draw each component
    for i, comp in enumerate(system.components):
        x = margin + (comp.position - min_z) * scale
        
        if comp.type in ('thin_lens', 'thick_lens'):
            aperture = comp.aperture_diameter / 2
            half_height = min(aperture * scale, 100)
            
            # Draw lens outline
            svg_lines.append(f'<rect x="{x-5}" y="{axis_y - half_height}" width="10" height="{half_height*2}" fill="#bfdbfe" stroke="#3b82f6" stroke-width="2"/>')
            
            # Label
            svg_lines.append(f'<text x="{x}" y="{axis_y + half_height + 20}" text-anchor="middle" font-size="12">{comp.id}</text>')
            
            # Dimensions
            if comp.type == 'thick_lens':
                svg_lines.append(f'<text x="{x}" y="{axis_y - half_height - 10}" text-anchor="middle" font-size="10" fill="#666">t={comp.thickness*1000:.2f}mm</text>')
    
    svg_lines.append('</svg>')
    filepath.write_text('\n'.join(svg_lines))


def _generate_text_drawing(system: OpticalSystem, filepath: Path) -> None:
    """Generate text-based lens drawing."""
    lines = []
    lines.append("=" * 60)
    lines.append("LENS ELEMENT DRAWING")
    lines.append("=" * 60)
    lines.append("")
    
    for i, comp in enumerate(system.components):
        lines.append(f"Surface {i + 1}: {comp.id}")
        lines.append(f"  Type: {comp.type}")
        lines.append(f"  Position: {comp.position * 1000:.4f} mm")
        
        if comp.type == 'thin_lens':
            lines.append(f"  Focal Length: {comp.focal_length * 1000:.4f} mm")
            lines.append(f"  Aperture: {comp.aperture_diameter * 1000:.4f} mm")
            lines.append(f"  Material: {comp.material}")
        elif comp.type == 'thick_lens':
            lines.append(f"  Radius 1: {comp.radius1 * 1000:.4f} mm")
            lines.append(f"  Radius 2: {comp.radius2 * 1000:.4f} mm")
            lines.append(f"  Thickness: {comp.thickness * 1000:.4f} mm")
            lines.append(f"  Aperture: {comp.aperture_diameter * 1000:.4f} mm")
            lines.append(f"  Material: {comp.material}")
        elif comp.type == 'aperture':
            lines.append(f"  Diameter: {comp.diameter * 1000:.4f} mm")
        
        lines.append("")
    
    filepath.write_text('\n'.join(lines))


def generate_iso10110_drawing(
    system: OpticalSystem,
    filepath,
    tolerances: Optional[dict] = None,
) -> None:
    """
    ISO 10110-style element data sheet.

    Design values (radii with CX/CC sense, centre thickness, diameter, glass)
    come from the system. Manufacturing tolerances (ISO 10110 codes 3/ form,
    4/ centring, 5/ surface imperfections, and dimensional tolerances) are
    not part of an optical design: they are printed only when supplied in
    ``tolerances`` (keys: "form", "centring", "imperfections", "thickness",
    "radius", "diameter", "coating"), otherwise marked as unspecified.
    """
    filepath = Path(filepath)
    tol = tolerances or {}

    def t(key):
        return tol.get(key, "not specified")

    L = ["=" * 70, "ISO 10110 ELEMENT DATA", "=" * 70, "",
         f"  Surface form (3/):           {t('form')}",
         f"  Centring (4/):               {t('centring')}",
         f"  Surface imperfections (5/):  {t('imperfections')}",
         f"  Coating:                     {t('coating')}", ""]
    for comp in system.components:
        if comp.type not in ("thin_lens", "thick_lens"):
            continue
        L.append(f"Element {comp.id}")
        L.append("-" * 40)
        if comp.type == "thick_lens":
            for k, R in ((1, comp.radius1), (2, comp.radius2)):
                if not R or abs(R) >= 1e9:
                    L.append(f"  Surface {k}: plano")
                else:
                    # convex toward the outside: surface 1 with R > 0, surface 2 with R < 0
                    convex = (R > 0) if k == 1 else (R < 0)
                    L.append(f"  Surface {k}: R {abs(R) * 1e3:.4f} {'CX' if convex else 'CC'}"
                             f"  (tolerance {t('radius')})")
            L.append(f"  Centre thickness: {comp.thickness * 1e3:.4f} mm (tolerance {t('thickness')})")
        else:
            L.append(f"  Ideal thin lens, focal length {comp.focal_length * 1e3:.4f} mm "
                     "(no surface data)")
        L.append(f"  Diameter: {comp.aperture_diameter * 1e3:.4f} mm (tolerance {t('diameter')})")
        L.append(f"  Glass: {comp.material}")
        L.append("")
    filepath.write_text("\n".join(L))


def generate_sag_table(system: OpticalSystem, filepath, n_points: int = 10) -> None:
    """
    Sag of every refracting/reflecting surface versus radial height, from
    the surface's exact shape (sphere, conic or asphere), with sign:
    positive sag is toward +z. Ideal thin lenses have no surface and are
    listed without sag data.
    """
    from .. import raytrace as rt
    import numpy as np
    filepath = Path(filepath)
    seq = rt.build_sequence(system)
    L = ["SAG TABLE", "=" * 60, ""]
    for s in seq.surfaces:
        if s.kind == "ideal":
            L += [f"Surface {s.label}: ideal thin lens (no sag)", ""]
            continue
        if s.kind not in ("refract", "reflect") or s.semi_aperture is None:
            continue
        L.append(f"Surface {s.label}")
        L.append(f"{'Height (mm)':<15} {'Sag (um)':<15}")
        L.append("-" * 30)
        for j in range(n_points + 1):
            r = s.semi_aperture * j / n_points
            z = float(np.asarray(s.shape.sag(np.array([0.0]), np.array([r])))[0])
            L.append(f"{r * 1e3:<15.4f} {z * 1e6:<15.3f}")
        L.append("")
    filepath.write_text("\n".join(L))
