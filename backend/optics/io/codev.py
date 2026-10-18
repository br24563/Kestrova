"""
Code V sequence file (.seq) import and export.

Supported commands (lens data in the file's DIM units, default mm):

    LEN, TITLE, DIM M|C|I     units: millimetres, centimetres, inches
    WL w1 w2 ...              wavelengths in nm;  REF k  (1-based)
    EPD d                     entrance pupil diameter
    YAN a1 a2 ...             field angles (deg)   or   YOB h1 h2 ...  object heights
    SO r t                    object surface (t >= 1e10 means infinity)
    S r t [glass]             surface: radius, thickness, glass
    STO r t [glass]           as S, and the surface is the aperture stop
    SI r t                    image surface
    K k                       conic constant of the current surface
    A a4 / B a6 / C a8 / D a10   even aspheric coefficients
    CIR r                     clear semi-aperture of the current surface
    REFL                      current surface reflects
    GO                        end

Glass names are written in Code V's catalog convention, the name without
hyphens followed by the vendor (e.g. N-BK7 -> NBK7_SCHOTT); on import such
names are matched back to the material catalog. Thin (ideal) lenses,
coordinate breaks and non-standard surfaces have no equivalent here and
raise ValueError on export.
"""

import math
import shlex
from pathlib import Path

from ..materials import MATERIALS, D_LINE
from ..models import OpticalSystem
from .prescription import Row, system_to_rows, rows_to_system, resolve_glass

_UNITS = {"M": 1e-3, "C": 1e-2, "I": 25.4e-3}
_INFINITY = 1e10


def _codev_glass(name: str) -> str:
    m = MATERIALS.get(name)
    if m is None or m.manufacturer in ("Literature", "N/A"):
        return name.replace("-", "")
    return f"{name.replace('-', '')}_{m.manufacturer.upper()}"


def import_seq(filepath) -> OpticalSystem:
    """Read a Code V sequence file into an OpticalSystem."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    unit = 1e-3
    wavelengths, ref = [], 1
    epd = None
    yan, yob = [], []
    object_thickness = None
    rows: list[Row] = []
    image_seen = False
    for raw in filepath.read_text().splitlines():
        line = raw.split("!")[0].strip()
        if not line:
            continue
        for stmt in line.split(";"):
            tok = shlex.split(stmt.strip()) if stmt.strip() else []
            if not tok:
                continue
            cmd = tok[0].upper()
            args = tok[1:]
            if cmd == "DIM":
                unit = _UNITS[args[0].upper()[0]]
            elif cmd == "WL":
                wavelengths = [float(a) * 1e-9 for a in args]
            elif cmd == "REF":
                ref = int(args[0])
            elif cmd == "EPD":
                epd = float(args[0]) * unit
            elif cmd == "YAN":
                yan = [float(a) for a in args]
            elif cmd == "YOB":
                yob = [float(a) * unit for a in args]
            elif cmd == "SO":
                t = float(args[1]) if len(args) > 1 else _INFINITY
                object_thickness = t * unit if abs(t) < _INFINITY else math.inf
            elif cmd in ("S", "STO"):
                r = float(args[0]) if args else 0.0
                t = float(args[1]) if len(args) > 1 else 0.0
                glass = args[2] if len(args) > 2 else None
                if glass is not None and glass.upper() == "AIR":
                    glass = None
                rows.append(
                    Row(
                        radius=r * unit,
                        thickness=t * unit,
                        glass=resolve_glass(glass) if glass else None,
                        stop=(cmd == "STO"),
                        label=f"S{len(rows) + 1}",
                    )
                )
            elif cmd == "SI":
                image_seen = True
            elif cmd == "K" and rows:
                rows[-1].conic = float(args[0])
            elif cmd in ("A", "B", "C", "D", "E") and rows:
                k = "ABCDE".index(cmd)
                coeffs = rows[-1].asphere
                while len(coeffs) <= k:
                    coeffs.append(0.0)
                coeffs[k] = float(args[0]) / unit ** (2 * k + 3)
            elif cmd == "CIR" and rows:
                rows[-1].semi_aperture = float(args[0]) * unit
            elif cmd == "REFL" and rows:
                rows[-1].glass = "MIRROR"
    if not rows:
        raise ValueError("No surfaces found in the sequence file")
    if not image_seen:
        raise ValueError("Sequence file has no image surface (SI)")
    if not wavelengths:
        wavelengths = [D_LINE]
    if object_thickness is None:
        raise ValueError("Sequence file has no object surface (SO)")
    infinite = not math.isfinite(object_thickness)
    obj_dist = 1e6 if infinite else object_thickness
    if infinite:
        if yob:
            raise ValueError("YOB fields need a finite object distance")
        height = obj_dist * math.tan(math.radians(max(yan, key=abs))) if yan else 0.0
    else:
        if yan:
            height = obj_dist * math.tan(math.radians(max(yan, key=abs)))
        else:
            height = max(yob, key=abs) if yob else 0.0
    if epd is not None:
        stop = next((r for r in rows if r.stop), None)
        if stop is not None and stop.semi_aperture is None:
            stop.semi_aperture = epd / 2.0  # exact when the stop is the first surface
    return rows_to_system(rows, obj_dist, height, wavelengths, ref - 1)


def export_seq(system: OpticalSystem, filepath) -> None:
    """Write an OpticalSystem as a Code V sequence file (millimetres)."""
    for c in system.components:
        if c.type == "thin_lens":
            raise ValueError(
                f"Thin lens '{c.id}' (ideal lens) has no Code V surface equivalent"
            )
    rows, obj_dist, fo = system_to_rows(system)
    mm = 1e3
    wl = system.wavelengths or [system.analysis_settings.wavelength]
    ref = (
        min(
            range(len(wl)),
            key=lambda k: abs(wl[k] - system.analysis_settings.wavelength),
        )
        + 1
    )
    lines = [
        "LEN NEW",
        "TITLE 'Exported design'",
        "DIM M",
        "WL " + " ".join(f"{w * 1e9:.4f}" for w in wl),
        f"REF {ref}",
        f"EPD {2 * fo.entrance_pupil_semi_diameter * mm:.6f}",
    ]
    if fo.object_infinite:
        lines.append(f"YAN 0.0 {math.degrees(fo.field_angle):.6f}")
        lines.append("SO 0.0 1.0E+20")
    else:
        lines.append(f"YOB 0.0 {system.object.height * mm:.6f}")
        lines.append(f"SO 0.0 {obj_dist * mm:.6f}")
    for r in rows:
        if r.paraxial_focal_length is not None:
            raise ValueError("Ideal lenses cannot be written to a Code V file")
        cmd = "STO" if r.stop else "S"
        glass = "" if r.glass in (None, "MIRROR") else " " + _codev_glass(r.glass)
        lines.append(f"{cmd} {r.radius * mm:.6f} {r.thickness * mm:.6f}{glass}")
        if r.glass == "MIRROR":
            lines.append("  REFL")
        if r.conic:
            lines.append(f"  K {r.conic:.10g}")
        for k, a in enumerate(r.asphere[:5]):
            if a:
                lines.append(f"  {'ABCDE'[k]} {a * (1e-3) ** (2 * k + 3):.10E}")
        if r.semi_aperture:
            lines.append(f"  CIR {r.semi_aperture * mm:.6f}")
    lines += ["SI 0.0 0.0", "GO"]
    Path(filepath).write_text("\n".join(lines) + "\n")
