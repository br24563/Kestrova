"""
Zemax OpticStudio sequential lens file (.zmx, text) import and export.

Supported keywords:

    UNIT MM|CM|IN|METER     lens units
    ENPD d                  entrance pupil diameter
    WAVM n w weight         wavelength n in micrometres;  PWAV n  primary
    YFLN v1 v2 ...          field y values (angles in degrees for FTYP 0,
                            object heights for FTYP 1);  FTYP t ...
    SURF n                  start of surface n (0 = object)
      TYPE STANDARD | EVENASPH | PARAXIAL
      CURV c                curvature (1/lens unit)
      CONI k                conic
      PARM i v              EVENASPH: i = 1 is the r^2 term, 2 is r^4, ...
                            PARAXIAL: 1 is the focal length
      DISZ t | INFINITY     thickness to the next surface
      GLAS name ...         glass after the surface (MIRROR = reflecting)
      DIAM d                clear semi-diameter
      STOP                  aperture stop

Field definitions beyond the maximum y field are not carried over.
Coordinate breaks and other surface types raise ValueError. The writer
emits no VERS header and a minimal FTYP record (field type, telecentric
flag, number of fields, number of wavelengths); check the file after
opening it in OpticStudio.
"""

import math
import re
from pathlib import Path

from ..materials import MATERIALS, D_LINE
from ..models import OpticalSystem
from .prescription import Row, system_to_rows, rows_to_system, resolve_glass

_UNITS = {"MM": 1e-3, "CM": 1e-2, "IN": 25.4e-3, "METER": 1.0, "M": 1.0}


def _float(tok: str) -> float:
    return math.inf if tok.upper().startswith("INF") else float(tok)


def import_zmx(filepath) -> OpticalSystem:
    """Read a Zemax .zmx (text) lens file into an OpticalSystem."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    text = filepath.read_text(errors="replace")
    unit = 1e-3
    waves, primary = {}, 1
    ftyp = 0
    yfln = []
    surfaces = []          # list of dicts
    cur = None
    for raw in text.splitlines():
        tok = raw.split()
        if not tok:
            continue
        key = tok[0].upper()
        if key == "UNIT":
            unit = _UNITS.get(tok[1].upper(), 1e-3)
        elif key == "WAVM":
            waves[int(tok[1])] = float(tok[2]) * 1e-6
        elif key == "PWAV":
            primary = int(tok[1])
        elif key == "FTYP":
            ftyp = int(tok[1])
        elif key == "YFLN":
            yfln = [float(v) for v in tok[1:]]
        elif key == "SURF":
            cur = {"n": int(tok[1]), "type": "STANDARD", "curv": 0.0, "conic": 0.0,
                   "parm": {}, "disz": 0.0, "glass": None, "diam": None, "stop": False}
            surfaces.append(cur)
        elif cur is not None:
            if key == "TYPE":
                cur["type"] = tok[1].upper()
            elif key == "CURV":
                cur["curv"] = float(tok[1])
            elif key == "CONI":
                cur["conic"] = float(tok[1])
            elif key == "PARM":
                cur["parm"][int(tok[1])] = float(tok[2])
            elif key == "DISZ":
                cur["disz"] = _float(tok[1])
            elif key == "GLAS":
                cur["glass"] = tok[1]
            elif key == "DIAM":
                cur["diam"] = float(tok[1])
            elif key == "STOP":
                cur["stop"] = True
    if len(surfaces) < 3:
        raise ValueError("A lens file needs an object, at least one surface and an image")
    obj, body = surfaces[0], surfaces[1:-1]
    rows = []
    for s in body:
        t = s["type"]
        if t not in ("STANDARD", "EVENASPH", "PARAXIAL"):
            raise ValueError(f"Surface {s['n']}: type {t} is not supported")
        glass = s["glass"]
        if glass is not None:
            glass = "MIRROR" if glass.upper() == "MIRROR" else resolve_glass(glass)
        row = Row(radius=(1.0 / s["curv"] * unit) if s["curv"] else 0.0,
                  conic=s["conic"], glass=glass, thickness=s["disz"] * unit,
                  semi_aperture=(s["diam"] * unit if s["diam"] else None),
                  stop=s["stop"], label=f"S{s['n']}")
        if t == "EVENASPH":
            if s["parm"].get(1, 0.0):
                raise ValueError(f"Surface {s['n']}: an r^2 aspheric term is not supported")
            coeffs = [s["parm"].get(i, 0.0) for i in range(2, 9)]
            while coeffs and coeffs[-1] == 0.0:
                coeffs.pop()
            # parm i multiplies r^(2i): convert from lens units
            row.asphere = [a / unit ** (2 * (k + 2) - 1) for k, a in enumerate(coeffs)]
        if t == "PARAXIAL":
            row.paraxial_focal_length = s["parm"].get(1, 0.0) * unit
            if not row.paraxial_focal_length:
                raise ValueError(f"Surface {s['n']}: paraxial surface needs a focal length")
        rows.append(row)
    wavelengths = [waves[k] for k in sorted(waves)] or [D_LINE]
    ref = sorted(waves).index(primary) if primary in waves else 0
    infinite = not math.isfinite(obj["disz"])
    obj_dist = 1e6 if infinite else obj["disz"] * unit
    ymax = max(yfln, key=abs) if yfln else 0.0
    if ftyp == 0:
        height = obj_dist * math.tan(math.radians(ymax))
    elif ftyp == 1:
        height = ymax * unit
    else:
        raise ValueError(f"Field type {ftyp} is not supported (use angle or object height)")
    return rows_to_system(rows, obj_dist, height, wavelengths, ref)


def export_zmx(system: OpticalSystem, filepath) -> None:
    """Write an OpticalSystem as a Zemax .zmx text file in millimetres."""
    rows, obj_dist, fo = system_to_rows(system)
    mm = 1e3
    wl = system.wavelengths or [system.analysis_settings.wavelength]
    primary = min(range(len(wl)), key=lambda k: abs(wl[k] - system.analysis_settings.wavelength)) + 1
    L = ["MODE SEQ", "NAME Exported design",
         "UNIT MM X W X CM MR CPMM",
         f"ENPD {2 * fo.entrance_pupil_semi_diameter * mm:.6f}"]
    for k, w in enumerate(wl, start=1):
        L.append(f"WAVM {k} {w * 1e6:.6f} 1")
    L.append(f"PWAV {primary}")
    if fo.object_infinite:
        L.append(f"FTYP 0 0 2 {len(wl)} 0 0 0")
        L.append(f"YFLN 0 {math.degrees(fo.field_angle):.6f}")
    else:
        L.append(f"FTYP 1 0 2 {len(wl)} 0 0 0")
        L.append(f"YFLN 0 {system.object.height * mm:.6f}")
    L.append("XFLN 0 0")
    L += ["SURF 0", "  TYPE STANDARD", "  CURV 0.0",
          "  DISZ INFINITY" if fo.object_infinite else f"  DISZ {obj_dist * mm:.6f}"]
    for n, r in enumerate(rows, start=1):
        L.append(f"SURF {n}")
        if r.stop:
            L.append("  STOP")
        if r.paraxial_focal_length is not None:
            L.append("  TYPE PARAXIAL")
            L.append(f"  PARM 1 {r.paraxial_focal_length * mm:.10g}")
            L.append("  PARM 2 0")
        elif r.asphere:
            L.append("  TYPE EVENASPH")
        else:
            L.append("  TYPE STANDARD")
        L.append(f"  CURV {(1.0 / (r.radius * mm)) if r.radius else 0.0:.12g}")
        if r.conic:
            L.append(f"  CONI {r.conic:.10g}")
        for k, a in enumerate(r.asphere):
            L.append(f"  PARM {k + 2} {a * (1e-3) ** (2 * (k + 2) - 1):.10E}")
        L.append(f"  DISZ {r.thickness * mm:.6f}")
        if r.glass == "MIRROR":
            L.append("  GLAS MIRROR 0 0")
        elif r.glass:
            m = MATERIALS[r.glass]
            if m.nd is None or m.vd is None:
                raise ValueError(f"Glass '{r.glass}' has no d-line data for a Zemax model glass")
            L.append(f"  GLAS {r.glass} 0 0 {m.nd:.6f} {m.vd:.4f} 0 0 0 0 0 0")
        if r.semi_aperture:
            L.append(f"  DIAM {r.semi_aperture * mm:.6f} 0 0 0 1 \"\"")
    L += [f"SURF {len(rows) + 1}", "  TYPE STANDARD", "  CURV 0.0", "  DISZ 0.0"]
    Path(filepath).write_text("\n".join(L) + "\n")
