"""
Lens prescriptions (:class:`optics.lens_data.LensData`) to and from Code V
sequence files (.seq) and Zemax OpticStudio lens files (.zmx, text).

Everything both a format and Kestrova can express is carried over: the
surfaces (standard, even asphere, Zemax paraxial, coordinate breaks), glass
(catalog names and model glasses), the stop, clear semi-apertures, the
entrance pupil, wavelengths with weights, the field table with weights and
vignetting, and the paraxial image solve and variables where the format has
them. Anything else is reported in the returned warnings, never silently
dropped: on reading, commands this module does not interpret; on writing,
solves and pickups that the format cannot express here (written as their
current values).

Code V commands read and written (lens units from DIM):

    LEN, TITLE, DIM M|C|I, WL, WTW, REF, EPD, YAN/XAN, YOB/XOB, YIM/XIM,
    WTF, VUY/VLY/VUX/VLX, SO, S, STO, SI, ASP, K, A..J (r^4 .. r^20),
    CIR, REFL, PIM (paraxial image solve on the last thickness),
    CCY Sk 0 / THC Sk 0 (curvature / thickness variables),
    XDE/YDE/ZDE/ADE/BDE/CDE (decenters, on a dummy surface), GO.

    Glass: catalog names in Code V's convention (N-BK7 -> NBK7_SCHOTT) or a
    model glass written nd:vd.

Zemax keywords read and written:

    NAME, UNIT, ENPD, WAVM n w weight, PWAV, FTYP, XFLN, YFLN, FWGN,
    VDXN/VDYN/VCXN/VCYN, SURF, TYPE STANDARD|EVENASPH|PARAXIAL|COORDBRK,
    COMM, CURV, CONI, PARM, DISZ, GLAS (catalog name, or ___BLANK with nd and
    Vd for a model glass), DIAM, STOP.

    Zemax vignetting (decenter VD, compression VC) maps exactly to Code V's
    factors: VD = (vl - vu) / 2, VC = (vu + vl) / 2.

The decenter and tilt conventions (signs and rotation order) of the two
programs are documented differently from Kestrova's; coordinate breaks
round-trip within Kestrova, but check tilted systems after moving them to
another program.
"""

from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Optional

from ..lens_data import FieldPoint, LensData, LensSurface, Solve, resolve
from ..materials import (
    D_LINE,
    MATERIALS,
    model_glass_name,
    parse_model_glass,
    parse_perturbed_glass,
)
from .prescription import resolve_glass

_CODEV_UNITS = {"M": 1e-3, "C": 1e-2, "I": 25.4e-3}
_ZEMAX_UNITS = {"MM": 1e-3, "CM": 1e-2, "IN": 25.4e-3, "METER": 1.0, "M": 1.0}
_INFINITY = 1e10
_ASPHERE_LETTERS = "ABCDEFGHJ"  # Code V: A = r^4, B = r^6, ..., J = r^20


@dataclass
class LensFileResult:
    lens: LensData
    warnings: list[str] = field(default_factory=list)


# =============================================================================
# Shared
# =============================================================================


def _vignetting_to_zemax(vu: float, vl: float) -> tuple[float, float]:
    """Code V upper/lower factors -> Zemax (decenter, compression)."""
    return (vl - vu) / 2.0, (vu + vl) / 2.0


def _vignetting_from_zemax(vd: float, vc: float) -> tuple[float, float]:
    """Zemax (decenter, compression) -> Code V (upper, lower) factors."""
    return vc - vd, vc + vd


def _glass_for_file(material: Optional[str], warnings: list) -> Optional[str]:
    """The catalog or model glass a file can name (perturbed glasses, used
    only while tolerancing, are written as their base glass)."""
    if material is None or material == "MIRROR":
        return material
    perturbed = parse_perturbed_glass(material)
    if perturbed is not None:
        warnings.append(
            f"Perturbed glass {material} written as its base glass {perturbed[0]}"
        )
        return perturbed[0]
    return material


def _default_wavelength_index(lens: LensData) -> int:
    lam = lens.analysis_settings.wavelength
    return min(
        range(len(lens.wavelengths)), key=lambda k: abs(lens.wavelengths[k] - lam)
    )


def _finish(
    surfaces: list[LensSurface],
    object_distance: Optional[float],
    wavelengths: list[float],
    weights: Optional[list[float]],
    reference: int,
    epd: Optional[float],
    field_type: str,
    fields: list[FieldPoint],
    name: str,
    warnings: list[str],
) -> LensFileResult:
    if not surfaces:
        raise ValueError("No surfaces found in the file")
    if not any(s.is_stop for s in surfaces):
        warnings.append("No stop surface in the file: the first surface is the stop")
        surfaces[0].is_stop = True
    wavelengths = wavelengths or [D_LINE]
    reference = min(max(reference, 0), len(wavelengths) - 1)
    max_field = max((math.hypot(f.x, f.y) for f in fields), default=0.0)
    kwargs: dict[str, Any] = dict(
        name=name,
        surfaces=surfaces,
        object_distance=object_distance,
        wavelengths=wavelengths,
        wavelength_weights=(
            weights if weights and any(w != 1 for w in weights) else None
        ),
        entrance_pupil_diameter=epd,
        analysis_settings={"wavelength": wavelengths[reference]},
    )
    if object_distance is None:
        if field_type == "object_height" and max_field > 0:
            raise ValueError("Object heights need a finite object distance")
        kwargs["field_angle"] = max_field if field_type == "angle" else 0.0
    else:
        kwargs["object_height"] = max_field if field_type == "object_height" else 0.0
    if fields and (len(fields) > 1 or max_field > 0):
        kwargs["fields"] = fields
        kwargs["field_type"] = field_type
    lens = LensData.model_validate(kwargs)
    return LensFileResult(lens, warnings)


def _solve_warnings(lens: LensData, keep: set[tuple[int, str]]) -> list[str]:
    out = []
    for i, s in enumerate(lens.surfaces):
        for name in s.solves:
            if (i, name) not in keep:
                out.append(f"Surface {i}: {name} solve written as its current value")
        for name in s.pickups:
            out.append(f"Surface {i}: {name} pickup written as its current value")
    return out


# =============================================================================
# Code V
# =============================================================================


def _codev_glass_name(name: str) -> str:
    model = parse_model_glass(name)
    if model is not None:
        return f"{model[0]:.6f}:{model[1]:.4f}"
    m = MATERIALS.get(name)
    if m is None or m.manufacturer in ("Literature", "N/A"):
        return name.replace("-", "")
    return f"{name.replace('-', '')}_{m.manufacturer.upper()}"


def _codev_glass_from_file(token: str) -> Optional[str]:
    if token.upper() == "AIR":
        return None
    if re.fullmatch(r"\d+(\.\d*)?:\d+(\.\d*)?", token):
        nd, vd = (float(v) for v in token.split(":"))
        return model_glass_name(nd, vd)
    return resolve_glass(token)


def read_codev(text: str) -> LensFileResult:
    """Read a Code V sequence file."""
    unit = 1e-3
    warnings: list[str] = []
    skipped: dict[str, int] = {}
    name = ""
    wavelengths: list[float] = []
    weights: Optional[list[float]] = None
    reference = 0
    epd = None
    fx: list[float] = []
    fy: list[float] = []
    ftype = "angle"
    fweights: list[float] = []
    vig: dict[str, list[float]] = {}
    object_distance: Optional[float] = 0.0
    seen_object = False
    seen_image = False
    surfaces: list[LensSurface] = []
    decenter: dict[str, float] = {}
    image_solve = False
    variables: list[tuple[str, int]] = []

    def flush_decenter():
        """Turn decenters given on the current (dummy) surface into a
        coordinate break row."""
        if not decenter or not surfaces:
            return
        s = surfaces[-1]
        if s.radius != 0 or s.material not in (None, _medium_before(len(surfaces) - 1)):
            warnings.append(
                f"Decenter on a powered surface {len(surfaces) - 1} is not supported; "
                "ignored"
            )
        else:
            s.surface_type = "coordinate_break"
            s.material = None
            for key, attr in (
                ("XDE", "decenter_x"),
                ("YDE", "decenter_y"),
                ("ZDE", "decenter_z"),
            ):
                setattr(s, attr, decenter.get(key, 0.0) * unit)
            for key, attr in (("ADE", "tilt_x"), ("BDE", "tilt_y"), ("CDE", "tilt_z")):
                setattr(s, attr, math.radians(decenter.get(key, 0.0)))
        decenter.clear()

    def _medium_before(i: int) -> Optional[str]:
        return surfaces[i - 1].material if i > 0 else None

    for raw in text.splitlines():
        line = raw.split("!")[0].strip()
        for stmt in (st.strip() for st in line.split(";")):
            if not stmt:
                continue
            tok = shlex.split(stmt)
            cmd, args = tok[0].upper(), tok[1:]
            if cmd in ("LEN", "GO"):
                continue
            if cmd == "TITLE":
                name = " ".join(args)
            elif cmd == "DIM":
                unit = _CODEV_UNITS[args[0].upper()[0]]
            elif cmd == "WL":
                wavelengths = [float(a) * 1e-9 for a in args]
            elif cmd == "WTW":
                weights = [float(a) for a in args]
            elif cmd == "REF":
                reference = int(args[0]) - 1
            elif cmd == "EPD":
                epd = float(args[0]) * unit
            elif cmd in ("YAN", "XAN"):
                ftype = "angle"
                vals = [math.radians(float(a)) for a in args]
                (fy if cmd == "YAN" else fx)[:] = vals
            elif cmd in ("YOB", "XOB", "YIM", "XIM"):
                ftype = (
                    "object_height" if cmd.endswith("OB") else "paraxial_image_height"
                )
                vals = [float(a) * unit for a in args]
                (fy if cmd.startswith("Y") else fx)[:] = vals
            elif cmd == "WTF":
                fweights = [float(a) for a in args]
            elif cmd in ("VUY", "VLY", "VUX", "VLX"):
                vig[cmd] = [float(a) for a in args]
            elif cmd == "SO":
                seen_object = True
                t = float(args[1]) if len(args) > 1 else _INFINITY
                object_distance = None if abs(t) >= _INFINITY else t * unit
            elif cmd in ("S", "STO", "SI"):
                flush_decenter()
                if cmd == "SI":
                    seen_image = True
                    continue
                r = float(args[0]) if args else 0.0
                t = float(args[1]) if len(args) > 1 else 0.0
                glass = _codev_glass_from_file(args[2]) if len(args) > 2 else None
                surfaces.append(
                    LensSurface(
                        label=f"S{len(surfaces) + 1}",
                        radius=r * unit,
                        thickness=t * unit,
                        material=glass,
                        is_stop=(cmd == "STO"),
                    )
                )
            elif cmd == "ASP" and surfaces:
                surfaces[-1].surface_type = "even_asphere"
            elif cmd == "K" and surfaces:
                surfaces[-1].conic = float(args[0])
            elif cmd in tuple(_ASPHERE_LETTERS) and surfaces and len(cmd) == 1:
                k = _ASPHERE_LETTERS.index(cmd)
                coeffs = list(surfaces[-1].aspheric_coefficients)
                while len(coeffs) <= k:
                    coeffs.append(0.0)
                coeffs[k] = float(args[0]) / unit ** (2 * k + 3)
                surfaces[-1].aspheric_coefficients = coeffs
                surfaces[-1].surface_type = "even_asphere"
            elif cmd == "CIR" and surfaces:
                surfaces[-1].semi_diameter = float(args[0]) * unit
            elif cmd == "REFL" and surfaces:
                surfaces[-1].material = "MIRROR"
            elif cmd == "PIM":
                image_solve = True
            elif cmd in ("CCY", "THC") and len(args) >= 2:
                if float(args[1]) == 0:
                    variables.append((cmd, int(args[0].upper().lstrip("S"))))
            elif cmd in ("XDE", "YDE", "ZDE", "ADE", "BDE", "CDE"):
                decenter[cmd] = float(args[0])
            else:
                skipped[cmd] = skipped.get(cmd, 0) + 1
    flush_decenter()
    if not seen_object:
        raise ValueError("Sequence file has no object surface (SO)")
    if not seen_image:
        raise ValueError("Sequence file has no image surface (SI)")
    for cmd, n in sorted(skipped.items()):
        warnings.append(f"Code V command {cmd} not interpreted ({n}x)")
    for cmd, k in variables:
        i = k - 1  # Code V counts the object as surface 0
        if not 0 <= i < len(surfaces):
            warnings.append(f"{cmd} S{k}: no such surface")
            continue
        surfaces[i].variables.append("radius" if cmd == "CCY" else "thickness")
    if image_solve and surfaces:
        last = surfaces[-1]
        if "thickness" in last.variables:
            last.variables.remove("thickness")
            warnings.append(
                f"Surface {len(surfaces) - 1}: thickness is both solved (PIM) and "
                "variable; kept the solve"
            )
        last.solves["thickness"] = Solve(kind="marginal_height")
    n = max(len(fx), len(fy))
    fields = []
    for k in range(n):
        f = FieldPoint(
            x=fx[k] if k < len(fx) else 0.0,
            y=fy[k] if k < len(fy) else 0.0,
            weight=fweights[k] if k < len(fweights) else 1.0,
        )
        for key, attr in (
            ("VUY", "vuy"),
            ("VLY", "vly"),
            ("VUX", "vux"),
            ("VLX", "vlx"),
        ):
            if key in vig and k < len(vig[key]):
                setattr(f, attr, vig[key][k])
        fields.append(f)
    return _finish(
        surfaces,
        object_distance,
        wavelengths,
        weights,
        reference,
        epd,
        ftype,
        fields,
        name,
        warnings,
    )


_TYPE_NAMES = {
    "q_asphere": "Q-type asphere",
    "toroid": "toroid",
    "zernike": "Zernike",
    "xy_polynomial": "XY polynomial",
    "diffractive": "diffractive",
}


def _unwritten(i: int, s, fmt: str, supported: tuple, warnings: list) -> None:
    """Warn about a surface type or clear aperture the format does not get:
    the surface is written as its base conic and a circular aperture."""
    if s.surface_type in _TYPE_NAMES and s.surface_type not in supported:
        warnings.append(
            f"Surface {i}: {_TYPE_NAMES[s.surface_type]} terms are not written to "
            f"{fmt} files (written as its base conic)"
        )
    if s.obscuration_semi or s.aperture_shape != "circular":
        warnings.append(
            f"Surface {i}: the obscuration / {s.aperture_shape} aperture is not "
            f"written to {fmt} files"
        )


def write_codev(lens: LensData) -> tuple[str, list[str]]:
    """A Code V sequence file of the lens (millimetres) and the warnings."""
    warnings: list[str] = []
    resolved = resolve(lens, fill_apertures=False)
    mm = 1e3
    wl = lens.wavelengths
    lines = [
        "LEN NEW",
        f"TITLE '{lens.name or 'Kestrova design'}'",
        "DIM M",
        "WL " + " ".join(f"{w * 1e9:.4f}" for w in wl),
    ]
    if lens.wavelength_weights:
        lines.append("WTW " + " ".join(f"{w:g}" for w in lens.wavelength_weights))
    lines.append(f"REF {_default_wavelength_index(lens) + 1}")
    if lens.entrance_pupil_diameter is not None:
        lines.append(f"EPD {lens.entrance_pupil_diameter * mm:.6f}")
    fields = lens.fields
    ftype = lens.field_type or (
        "angle" if lens.object_distance is None else "object_height"
    )
    if fields is None:
        top = lens.field_angle if lens.object_distance is None else lens.object_height
        fields = (
            [FieldPoint(y=0.0), FieldPoint(y=0.7 * top), FieldPoint(y=top)]
            if top
            else [FieldPoint()]
        )

    def conv(v: float) -> float:
        return math.degrees(v) if ftype == "angle" else v * mm

    if ftype == "angle":
        ycmd, xcmd = "YAN", "XAN"
    else:
        ycmd, xcmd = ("YOB", "XOB") if ftype == "object_height" else ("YIM", "XIM")
    if any(f.x for f in fields):
        lines.append(xcmd + " " + " ".join(f"{conv(f.x):.6f}" for f in fields))
    lines.append(ycmd + " " + " ".join(f"{conv(f.y):.6f}" for f in fields))
    if any(f.weight != 1 for f in fields):
        lines.append("WTF " + " ".join(f"{f.weight:g}" for f in fields))
    for key in ("vuy", "vly", "vux", "vlx"):
        vals = [getattr(f, key) for f in fields]
        if any(vals):
            lines.append(key.upper() + " " + " ".join(f"{v:g}" for v in vals))
    lines.append(
        "SO 0.0 1.0E+20"
        if lens.object_distance is None
        else f"SO 0.0 {lens.object_distance * mm:.6f}"
    )
    keep: set[tuple[int, str]] = set()
    variables = []
    n = len(resolved.surfaces)
    for i, (s, src) in enumerate(zip(resolved.surfaces, lens.surfaces)):
        if s.surface_type == "paraxial":
            raise ValueError(
                f"Surface {i}: Code V has no paraxial (ideal lens) surface; "
                "export to Zemax or replace it with real surfaces"
            )
        if s.surface_type == "component":
            raise ValueError(f"Surface {i}: a component surface cannot be written")
        if s.surface_type == "coordinate_break":
            lines.append(f"S 0.0 {s.thickness * mm:.6f}")
            for key, attr, scale in (
                ("XDE", "decenter_x", mm),
                ("YDE", "decenter_y", mm),
                ("ZDE", "decenter_z", mm),
            ):
                if getattr(s, attr):
                    lines.append(f"  {key} {getattr(s, attr) * scale:.6f}")
            for key, attr in (("ADE", "tilt_x"), ("BDE", "tilt_y"), ("CDE", "tilt_z")):
                if getattr(s, attr):
                    lines.append(f"  {key} {math.degrees(getattr(s, attr)):.8f}")
            continue
        _unwritten(i, s, "Code V", (), warnings)
        glass = _glass_for_file(s.material, warnings)
        cmd = "STO" if s.is_stop else "S"
        g = "" if glass in (None, "MIRROR") else " " + _codev_glass_name(glass)
        lines.append(f"{cmd} {s.radius * mm:.6f} {s.thickness * mm:.6f}{g}")
        if glass == "MIRROR":
            lines.append("  REFL")
        aspheric = s.surface_type in ("even_asphere", "odd_asphere") and any(
            s.aspheric_coefficients
        )
        if s.surface_type == "odd_asphere" and any(s.odd_coefficients):
            warnings.append(
                f"Surface {i}: odd asphere terms (r^3, r^5, ...) are not written "
                "to Code V files"
            )
        if aspheric:
            lines.append("  ASP")
        if s.conic:
            lines.append(f"  K {s.conic:.10g}")
        if aspheric:
            coeffs = s.aspheric_coefficients
            if len(coeffs) > len(_ASPHERE_LETTERS):
                warnings.append(f"Surface {i}: terms beyond r^20 dropped")
            for k, a in enumerate(coeffs[: len(_ASPHERE_LETTERS)]):
                if a:
                    lines.append(
                        f"  {_ASPHERE_LETTERS[k]} {a * (1e-3) ** (2 * k + 3):.10E}"
                    )
        if src.semi_diameter is not None and not src.semi_diameter_auto:
            lines.append(f"  CIR {src.semi_diameter * mm:.6f}")
        solve = src.solves.get("thickness")
        if (
            i == n - 1
            and solve
            and solve.kind == "marginal_height"
            and solve.target == 0
        ):
            lines.append("  PIM")
            keep.add((i, "thickness"))
        for v in src.variables:
            if v in ("radius", "thickness"):
                variables.append(f"{'CCY' if v == 'radius' else 'THC'} S{i + 1} 0")
            else:
                warnings.append(
                    f"Surface {i}: variable {v} has no Code V equivalent here"
                )
    lines.append("SI 0.0 0.0")
    lines += variables
    lines.append("GO")
    warnings += _solve_warnings(lens, keep)
    return "\n".join(lines) + "\n", warnings


# =============================================================================
# Zemax
# =============================================================================


def _zemax_glass_from_file(args: list[str]) -> Optional[str]:
    name = args[0]
    if name.upper() == "MIRROR":
        return "MIRROR"
    if name == "___BLANK":
        return model_glass_name(float(args[3]), float(args[4]))
    return resolve_glass(name)


def read_zemax(text: str) -> LensFileResult:
    """Read a Zemax OpticStudio sequential lens file (text .zmx)."""
    unit = 1e-3
    warnings: list[str] = []
    skipped: dict[str, int] = {}
    name = ""
    waves: dict[int, tuple[float, float]] = {}
    primary = 1
    epd = None
    ftype = "angle"
    fx: list[float] = []
    fy: list[float] = []
    fw: list[float] = []
    vd: dict[str, list[float]] = {"VDXN": [], "VDYN": [], "VCXN": [], "VCYN": []}
    raw_surfaces: list[dict] = []
    current: Optional[dict] = None
    for raw in text.splitlines():
        tok = raw.split()
        if not tok:
            continue
        key, args = tok[0].upper(), tok[1:]
        if key == "SURF":
            current = {
                "index": int(args[0]),
                "type": "STANDARD",
                "curv": 0.0,
                "coni": 0.0,
                "parm": {},
                "disz": 0.0,
                "glass": None,
                "diam": None,
                "stop": False,
                "comm": "",
            }
            raw_surfaces.append(current)
        elif current is not None and key in (
            "TYPE",
            "CURV",
            "CONI",
            "PARM",
            "DISZ",
            "GLAS",
            "DIAM",
            "STOP",
            "COMM",
        ):
            if key == "TYPE":
                current["type"] = args[0].upper()
            elif key == "CURV":
                current["curv"] = float(args[0])
            elif key == "CONI":
                current["coni"] = float(args[0])
            elif key == "PARM":
                current["parm"][int(args[0])] = float(args[1])
            elif key == "DISZ":
                current["disz"] = (
                    math.inf if args[0].upper() == "INFINITY" else float(args[0])
                )
            elif key == "GLAS":
                current["glass"] = _zemax_glass_from_file(args)
            elif key == "DIAM":
                current["diam"] = float(args[0])
            elif key == "STOP":
                current["stop"] = True
            elif key == "COMM":
                current["comm"] = " ".join(args)
        elif key == "NAME":
            name = " ".join(args)
        elif key == "UNIT":
            unit = _ZEMAX_UNITS[args[0].upper()]
        elif key == "ENPD":
            epd = float(args[0])
        elif key == "WAVM":
            waves[int(args[0])] = (
                float(args[1]) * 1e-6,
                float(args[2]) if len(args) > 2 else 1.0,
            )
        elif key == "PWAV":
            primary = int(args[0])
        elif key == "FTYP":
            ftype = {0: "angle", 1: "object_height", 2: "paraxial_image_height"}.get(
                int(args[0]), "angle"
            )
            if int(args[0]) > 2:
                warnings.append(
                    f"Zemax field type {args[0]} is not supported; read as angles"
                )
        elif key in ("XFLN", "YFLN", "FWGN"):
            vals = [float(a) for a in args]
            {"XFLN": fx, "YFLN": fy, "FWGN": fw}[key][:] = vals
        elif key in vd:
            vd[key] = [float(a) for a in args]
        elif key in ("VERS", "MODE", "NOTE", "GCAT"):
            continue
        else:
            skipped[key] = skipped.get(key, 0) + 1
    if not raw_surfaces or raw_surfaces[0]["index"] != 0:
        raise ValueError("Lens file has no object surface (SURF 0)")
    if len(raw_surfaces) < 2:
        raise ValueError("Lens file has no image surface")
    for key, n in sorted(skipped.items()):
        warnings.append(f"Zemax keyword {key} not interpreted ({n}x)")
    obj = raw_surfaces[0]
    object_distance = (
        None
        if (not math.isfinite(obj["disz"]) or abs(obj["disz"]) >= _INFINITY)
        else obj["disz"] * unit
    )
    surfaces: list[LensSurface] = []
    for rs in raw_surfaces[1:-1]:
        t = rs["disz"] * unit if math.isfinite(rs["disz"]) else 0.0
        s = LensSurface(label=rs["comm"], thickness=t, is_stop=rs["stop"])
        if rs["type"] == "COORDBRK":
            p = rs["parm"]
            s.surface_type = "coordinate_break"
            s.decenter_x = p.get(1, 0.0) * unit
            s.decenter_y = p.get(2, 0.0) * unit
            s.tilt_x = math.radians(p.get(3, 0.0))
            s.tilt_y = math.radians(p.get(4, 0.0))
            s.tilt_z = math.radians(p.get(5, 0.0))
            s.break_order = (
                "tilt_then_decenter" if p.get(6, 0.0) else "decenter_then_tilt"
            )
        elif rs["type"] == "PARAXIAL":
            s.surface_type = "paraxial"
            s.focal_length = rs["parm"].get(1, 0.0) * unit
        elif rs["type"] == "TOROIDAL":
            s.surface_type = "toroid"
            s.radius = 1.0 / (rs["curv"] / unit) if rs["curv"] else 0.0
            s.conic = rs["coni"]
            s.material = rs["glass"]
            p = rs["parm"]
            s.radius_x = p.get(1, 0.0) * unit
            if any(v for k, v in p.items() if k >= 2):
                warnings.append(
                    f"Surface {rs['index']}: toroid aspheric terms are not supported"
                )
        elif rs["type"] == "ODDASPH":
            s.radius = 1.0 / (rs["curv"] / unit) if rs["curv"] else 0.0
            s.conic = rs["coni"]
            s.material = rs["glass"]
            p = rs["parm"]
            for k in (1, 2):
                if p.get(k):
                    warnings.append(
                        f"Surface {rs['index']}: the r^{k} asphere term is not supported"
                    )
            terms = {k: p.get(k, 0.0) / unit ** (k - 1) for k in range(3, 9)}
            even = [terms[k] for k in (4, 6, 8)]
            odd = [terms[k] for k in (3, 5, 7)]
            while even and even[-1] == 0:
                even.pop()
            while odd and odd[-1] == 0:
                odd.pop()
            s.aspheric_coefficients = even
            s.odd_coefficients = odd
            s.surface_type = (
                "odd_asphere" if odd else ("even_asphere" if even else "standard")
            )
        elif rs["type"] in ("STANDARD", "EVENASPH"):
            s.radius = 1.0 / (rs["curv"] / unit) if rs["curv"] else 0.0
            s.conic = rs["coni"]
            s.material = rs["glass"]
            if rs["type"] == "EVENASPH":
                p = rs["parm"]
                if p.get(1):
                    warnings.append(
                        f"Surface {rs['index']}: the r^2 asphere term is not supported"
                    )
                coeffs = [p.get(k, 0.0) / unit ** (2 * k - 1) for k in range(2, 11)]
                while coeffs and coeffs[-1] == 0:
                    coeffs.pop()
                s.aspheric_coefficients = coeffs
                s.surface_type = "even_asphere" if coeffs else "standard"
        else:
            raise ValueError(
                f"Surface {rs['index']}: type {rs['type']} is not supported"
            )
        if rs["diam"] is not None and s.surface_type != "coordinate_break":
            s.semi_diameter = rs["diam"] * unit
        surfaces.append(s)
    order = sorted(waves)
    wavelengths = [waves[k][0] for k in order]
    weights = [waves[k][1] for k in order]
    reference = order.index(primary) if primary in order else 0
    n = max(len(fx), len(fy))
    fields = []
    for k in range(n):
        x = fx[k] if k < len(fx) else 0.0
        y = fy[k] if k < len(fy) else 0.0
        if ftype == "angle":
            x, y = math.radians(x), math.radians(y)
        else:
            x, y = x * unit, y * unit
        f = FieldPoint(x=x, y=y, weight=fw[k] if k < len(fw) else 1.0)
        vdx = vd["VDXN"][k] if k < len(vd["VDXN"]) else 0.0
        vdy = vd["VDYN"][k] if k < len(vd["VDYN"]) else 0.0
        vcx = vd["VCXN"][k] if k < len(vd["VCXN"]) else 0.0
        vcy = vd["VCYN"][k] if k < len(vd["VCYN"]) else 0.0
        f.vux, f.vlx = _vignetting_from_zemax(vdx, vcx)
        f.vuy, f.vly = _vignetting_from_zemax(vdy, vcy)
        fields.append(f)
    return _finish(
        surfaces,
        object_distance,
        wavelengths,
        weights,
        reference,
        None if epd is None else epd * unit,
        ftype,
        fields,
        name,
        warnings,
    )


def _write_zemax_glass(material, lines: list, warnings: list) -> None:
    glass = _glass_for_file(material, warnings)
    if glass == "MIRROR":
        lines.append("  GLAS MIRROR 0 0 1.5 40 0 0 0 0 0 0")
    elif glass is not None:
        model = parse_model_glass(glass)
        if model is not None:
            lines.append(
                f"  GLAS ___BLANK 1 0 {model[0]:.6f} {model[1]:.4f} 0 0 0 0 0 0"
            )
        else:
            lines.append(f"  GLAS {glass} 0 0 1.5 40 0 0 0 0 0 0")


def write_zemax(lens: LensData) -> tuple[str, list[str]]:
    """A Zemax text lens file of the lens (millimetres) and the warnings."""
    warnings: list[str] = []
    resolved = resolve(lens, fill_apertures=False)
    mm = 1e3
    lines = [
        "VERS 0",
        "MODE SEQ",
        f"NAME {lens.name or 'Kestrova design'}",
        "UNIT MM X W X CM MR CPMM",
    ]
    if lens.entrance_pupil_diameter is not None:
        lines.append(f"ENPD {lens.entrance_pupil_diameter * mm:.6f}")
    weights = lens.wavelength_weights or [1.0] * len(lens.wavelengths)
    for k, (w, wt) in enumerate(zip(lens.wavelengths, weights), start=1):
        lines.append(f"WAVM {k} {w * 1e6:.8f} {wt:g}")
    lines.append(f"PWAV {_default_wavelength_index(lens) + 1}")
    fields = lens.fields
    ftype = lens.field_type or (
        "angle" if lens.object_distance is None else "object_height"
    )
    if fields is None:
        top = lens.field_angle if lens.object_distance is None else lens.object_height
        fields = (
            [FieldPoint(y=0.0), FieldPoint(y=0.7 * top), FieldPoint(y=top)]
            if top
            else [FieldPoint()]
        )
    code = {"angle": 0, "object_height": 1, "paraxial_image_height": 2}[ftype]
    conv = math.degrees if ftype == "angle" else (lambda v: v * mm)
    lines.append(f"FTYP {code} 0 {len(fields)} {len(lens.wavelengths)} 0 0 0")
    lines.append("XFLN " + " ".join(f"{conv(f.x):.8f}" for f in fields))
    lines.append("YFLN " + " ".join(f"{conv(f.y):.8f}" for f in fields))
    lines.append("FWGN " + " ".join(f"{f.weight:g}" for f in fields))
    zx = [_vignetting_to_zemax(f.vux, f.vlx) for f in fields]
    zy = [_vignetting_to_zemax(f.vuy, f.vly) for f in fields]
    lines.append("VDXN " + " ".join(f"{d:g}" for d, _ in zx))
    lines.append("VDYN " + " ".join(f"{d:g}" for d, _ in zy))
    lines.append("VCXN " + " ".join(f"{c:g}" for _, c in zx))
    lines.append("VCYN " + " ".join(f"{c:g}" for _, c in zy))
    obj_t = (
        "INFINITY"
        if lens.object_distance is None
        else f"{lens.object_distance * mm:.8f}"
    )
    lines += ["SURF 0", "  TYPE STANDARD", "  CURV 0.0", f"  DISZ {obj_t}"]
    for i, (s, src) in enumerate(zip(resolved.surfaces, lens.surfaces), start=1):
        lines.append(f"SURF {i}")
        if s.label:
            lines.append(f"  COMM {s.label}")
        if s.is_stop:
            lines.append("  STOP")
        if s.surface_type == "coordinate_break":
            lines.append("  TYPE COORDBRK")
            params = [
                s.decenter_x * mm,
                s.decenter_y * mm,
                math.degrees(s.tilt_x),
                math.degrees(s.tilt_y),
                math.degrees(s.tilt_z),
                1.0 if s.break_order != "decenter_then_tilt" else 0.0,
            ]
            for k, v in enumerate(params, start=1):
                lines.append(f"  PARM {k} {v:.10g}")
            if s.decenter_z:
                warnings.append(
                    f"Surface {i - 1}: a z decenter is written as thickness only"
                )
            lines.append(f"  DISZ {(s.thickness + s.decenter_z) * mm:.8f}")
            continue
        if s.surface_type == "component":
            raise ValueError(f"Surface {i - 1}: a component surface cannot be written")
        if s.surface_type == "paraxial":
            lines += [
                "  TYPE PARAXIAL",
                f"  PARM 1 {(s.focal_length or 0.0) * mm:.10g}",
            ]
        elif s.surface_type == "toroid":
            # Zemax's toroid: the y-z curve (CURV, CONI) swept about an axis
            # parallel to y at the radius of rotation (PARM 1, 0 = flat in x)
            _unwritten(i - 1, s, "Zemax", ("toroid",), warnings)
            lines.append("  TYPE TOROIDAL")
            curv = 1.0 / (s.radius * mm) if s.radius else 0.0
            lines.append(f"  CURV {curv:.15g}")
            if s.conic:
                lines.append(f"  CONI {s.conic:.10g}")
            lines.append(f"  PARM 1 {s.radius_x * mm:.15g}")
            _write_zemax_glass(s.material, lines, warnings)
        else:
            _unwritten(i - 1, s, "Zemax", ("toroid",), warnings)
            odd = s.surface_type == "odd_asphere" and any(s.odd_coefficients)
            aspheric = s.surface_type in ("even_asphere", "odd_asphere") and any(
                s.aspheric_coefficients
            )
            if odd:
                lines.append("  TYPE ODDASPH")
            else:
                lines.append("  TYPE EVENASPH" if aspheric else "  TYPE STANDARD")
            curv = 1.0 / (s.radius * mm) if s.radius else 0.0
            lines.append(f"  CURV {curv:.15g}")
            if s.conic:
                lines.append(f"  CONI {s.conic:.10g}")
            if odd:
                # Zemax's odd asphere: PARM k is the r^k coefficient, k = 1 .. 8
                terms = {
                    order: a
                    for order, a in zip(range(4, 22, 2), s.aspheric_coefficients)
                }
                terms.update(zip(range(3, 21, 2), s.odd_coefficients))
                if any(a for order, a in terms.items() if order > 8):
                    warnings.append(
                        f"Surface {i - 1}: odd asphere terms beyond r^8 dropped"
                    )
                for order in range(3, 9):
                    if terms.get(order):
                        lines.append(
                            f"  PARM {order} {terms[order] * (1e-3) ** (order - 1):.10E}"
                        )
            elif aspheric:
                for k, a in enumerate(s.aspheric_coefficients[:9], start=2):
                    lines.append(f"  PARM {k} {a * (1e-3) ** (2 * k - 1):.10E}")
            _write_zemax_glass(s.material, lines, warnings)
        if src.semi_diameter is not None and not src.semi_diameter_auto:
            lines.append(f"  DIAM {src.semi_diameter * mm:.8f}")
        lines.append(f"  DISZ {s.thickness * mm:.8f}")
        for var in src.variables:
            warnings.append(f"Surface {i - 1}: variable {var} written as a fixed value")
    lines += [
        f"SURF {len(resolved.surfaces) + 1}",
        "  TYPE STANDARD",
        "  CURV 0.0",
        "  DISZ 0",
    ]
    warnings += _solve_warnings(lens, set())
    return "\n".join(lines) + "\n", warnings


def read_lens_file(text: str, filename: str) -> LensFileResult:
    """Read a .seq or .zmx file by its extension."""
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "seq":
        return read_codev(text)
    if ext == "zmx":
        return read_zemax(text)
    raise ValueError(
        f"Unsupported lens file '.{ext}': use .seq (Code V) or .zmx (Zemax)"
    )
