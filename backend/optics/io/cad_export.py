"""
STEP and IGES export of a prescription's optical elements.

Each glass element (a pair of surfaces with glass between them; a cemented
group gives one body per glass) and each mirror becomes a solid of
revolution in its place along the axis, in millimetres:

- spherical faces are exact spheres, flat faces planes;
- conics, aspheres and Q-type surfaces are surfaces of revolution of a
  cubic B-spline interpolating the sag (refined until it matches the sag
  to 10 nm);
- past its clear aperture an element continues as a flat land out to the
  outer diameter (clear diameter + ``edge_margin``) and a cylindrical edge,
  as in the ISO 10110 drawings;
- a mirror gets a flat back ``mirror_thickness`` behind its deepest point
  (default: one eighth of its diameter).

STEP (ISO 10303-21, AP214) holds one part with a closed B-rep solid per
element; IGES (5.3) holds the faces as surfaces of revolution (type 120).
Surfaces without rotational symmetry (toroids, XY polynomials, Zernike,
tilted or decentred surfaces) and ideal (paraxial) lenses cannot be
exported this way; they are left out and listed in the warnings.
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..lens_data import LensData, LensSurface, resolve, surface_shape

MM = 1e3  # m -> mm
#: Largest allowed difference between a B-spline profile and the sag (mm).
PROFILE_TOLERANCE = 1e-5
_SYMMETRIC = ("standard", "even_asphere", "odd_asphere", "q_asphere")


# ---------------------------------------------------------------------------
# Geometry: element outlines in the (z, r) half plane
# ---------------------------------------------------------------------------


@dataclass
class Face:
    """One face of a body: a segment of its outline revolved about the axis.

    kind: "surface" (an optical surface from the axis to its rim or back),
    "plane" (an annulus or disk at constant z) or "cylinder" (constant r).
    ``a`` and ``b`` are the (z, r) end points in mm, in outline order."""

    kind: str
    a: tuple[float, float]
    b: tuple[float, float]
    surface: Optional[LensSurface] = None
    vertex_z: float = 0.0  # mm, optical surfaces only

    def sag(self, r: float) -> float:
        """z (mm) of an optical face at radius r (mm)."""
        assert self.surface is not None
        return self.vertex_z + _sag(self.surface, r / MM) * MM


@dataclass
class Body:
    name: str
    faces: list[Face] = field(default_factory=list)


def _sag(surface: LensSurface, h: float) -> float:
    if not surface.radius and surface.surface_type == "standard":
        return 0.0
    return float(surface_shape(surface).sag(np.array(0.0), np.array(h)))


def _is_sphere(s: LensSurface) -> bool:
    return s.surface_type == "standard" and not s.conic and bool(s.radius)


def _is_plane(s: LensSurface) -> bool:
    return s.surface_type == "standard" and not s.radius


def _exportable(s: LensSurface) -> Optional[str]:
    """Why a surface cannot be exported (None when it can)."""
    if s.surface_type not in _SYMMETRIC:
        return f"a {s.surface_type} surface is not rotationally symmetric"
    if s.decenter_x or s.decenter_y or s.tilt_x or s.tilt_y:
        return "the surface is decentred or tilted"
    return None


def _outline(
    points: list[tuple[float, float]], kinds: list[str], surfaces: list
) -> list[Face]:
    """Faces from outline points (z, r): drop zero-length segments and make
    the outline clockwise in (z, r) (solid on the right, outward on the
    left of travel)."""
    pts = list(points)
    area = 0.0
    closed = pts + [pts[0]]
    for (z1, r1), (z2, r2) in zip(closed, closed[1:]):
        area += z1 * r2 - z2 * r1
    faces = []
    for k in range(len(pts) - 1):
        a, b = pts[k], pts[k + 1]
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9:
            continue
        surf, vz = surfaces[k] if surfaces[k] else (None, 0.0)
        faces.append(Face(kinds[k], a, b, surf, vz))
    if area > 0:  # counter-clockwise: reverse
        faces = [Face(f.kind, f.b, f.a, f.surface, f.vertex_z) for f in reversed(faces)]
    return faces


def lens_bodies(
    lens: LensData,
    edge_margin: float = 1e-3,
    mirror_thickness: Optional[float] = None,
) -> tuple[list[Body], list[str]]:
    """The solids of a lens (mm) and warnings for what was left out."""
    lens = resolve(lens)
    surfaces = lens.surfaces
    warnings: list[str] = []
    # vertex positions along the axis (signed thicknesses, as traced)
    zs, z = [], lens.first_surface_position
    for s in surfaces:
        zs.append(z * MM)
        z += s.thickness
    margin = edge_margin * MM / 2
    bodies: list[Body] = []
    n_glass = 0
    for i, s in enumerate(surfaces):
        if s.surface_type in ("coordinate_break",):
            continue
        if s.material == "MIRROR":
            reason = _exportable(s)
            if reason:
                warnings.append(f"Mirror S{i} left out: {reason}")
                continue
            h = (s.semi_diameter or 0.0) * MM
            if h <= 0:
                continue
            # light leaves toward -z after the mirror when the next
            # thickness is negative: the substrate is on the +z side then
            back = 1.0 if s.thickness < 0 else -1.0
            if s.thickness == 0 and i > 0:
                back = 1.0 if surfaces[i - 1].thickness > 0 else -1.0
            t = (mirror_thickness * MM) if mirror_thickness else 2 * h / 8
            face = Face("surface", (0, 0), (0, 0), s, zs[i])
            outer = h + margin
            rim = face.sag(h)
            deepest = max(rim, zs[i]) if back > 0 else min(rim, zs[i])
            zb = deepest + back * t
            pts = [(zs[i], 0.0), (rim, h), (rim, outer), (zb, outer), (zb, 0.0)]
            kinds = ["surface", "plane", "cylinder", "plane"]
            surf = [(s, zs[i]), None, None, None]
            bodies.append(Body(s.label or f"Mirror S{i}", _outline(pts, kinds, surf)))
            continue
        if s.material is None or s.surface_type in ("paraxial", "component"):
            if s.surface_type in ("paraxial", "component") and s.material is not None:
                warnings.append(
                    f"S{i} left out: a {s.surface_type} surface has no shape"
                )
            continue
        j = i + 1
        while j < len(surfaces) and surfaces[j].surface_type == "coordinate_break":
            j += 1
        if j >= len(surfaces):
            continue
        back_s = surfaces[j]
        n_glass += 1
        name = s.element or f"Element {n_glass}"
        reasons = [r for r in (_exportable(s), _exportable(back_s)) if r]
        if back_s.surface_type in ("paraxial", "component"):
            reasons.append(f"a {back_s.surface_type} surface has no shape")
        if reasons:
            warnings.append(f"{name} (S{i}-S{j}) left out: {reasons[0]}")
            continue
        hf = (s.semi_diameter or 0.0) * MM
        hb = (back_s.semi_diameter or 0.0) * MM
        if hf <= 0 or hb <= 0:
            warnings.append(f"{name} left out: no clear aperture")
            continue
        outer = max(hf, hb) + margin
        front = Face("surface", (0, 0), (0, 0), s, zs[i])
        rear = Face("surface", (0, 0), (0, 0), back_s, zs[j])
        zf, zb = front.sag(hf), rear.sag(hb)
        direction = 1.0 if zs[j] >= zs[i] else -1.0
        if (zb - zf) * direction <= 0:
            warnings.append(f"{name} left out: its edge thickness is not positive")
            continue
        pts = [(zs[i], 0.0), (zf, hf), (zf, outer), (zb, outer), (zb, hb), (zs[j], 0.0)]
        kinds = ["surface", "plane", "cylinder", "plane", "surface"]
        surf = [(s, zs[i]), None, None, None, (back_s, zs[j])]
        bodies.append(Body(name, _outline(pts, kinds, surf)))
    return bodies, warnings


# ---------------------------------------------------------------------------
# B-spline profiles (global cubic interpolation, Piegl & Tiller A9.1)
# ---------------------------------------------------------------------------


def _basis(i: int, p: int, u: float, U: np.ndarray) -> float:
    if p == 0:
        if U[i] <= u < U[i + 1]:
            return 1.0
        return 0.0
    left = 0.0
    if U[i + p] != U[i]:
        left = (u - U[i]) / (U[i + p] - U[i]) * _basis(i, p - 1, u, U)
    right = 0.0
    if U[i + p + 1] != U[i + 1]:
        right = (
            (U[i + p + 1] - u) / (U[i + p + 1] - U[i + 1]) * _basis(i + 1, p - 1, u, U)
        )
    return left + right


def _basis_row(n: int, p: int, u: float, U: np.ndarray) -> np.ndarray:
    """All n basis functions at u (at the last knot only the last is 1)."""
    if u >= U[-1]:
        row = np.zeros(n)
        row[-1] = 1.0
        return row
    return np.array([_basis(k, p, u, U) for k in range(n)])


def _evaluate(ctrl: np.ndarray, U: np.ndarray, u: float, p: int = 3) -> np.ndarray:
    return _basis_row(len(ctrl), p, u, U) @ ctrl


def interpolate(
    points: np.ndarray, p: int = 3
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cubic B-spline through the points: (control points, knots, params)."""
    n = len(points)
    d = np.linalg.norm(np.diff(points, axis=0), axis=1)
    t = np.concatenate([[0.0], np.cumsum(d)]) / d.sum()
    U = np.concatenate(
        [
            np.zeros(p + 1),
            [t[j : j + p].mean() for j in range(1, n - p)],
            np.ones(p + 1),
        ]
    )
    A = np.array([_basis_row(n, p, float(u), U) for u in t])
    return np.linalg.solve(A, points), U, t


def profile_spline(face: Face) -> tuple[np.ndarray, np.ndarray]:
    """Control points (z, r) and knots of an optical face's profile from
    the axis to its rim, matching the sag to PROFILE_TOLERANCE."""
    r_max = max(face.a[1], face.b[1])
    n = 9
    while True:
        r = r_max * np.sin(np.linspace(0.0, math.pi / 2, n))  # denser at the rim
        pts = np.array([[face.sag(x), x] for x in r])
        ctrl, U, t = interpolate(pts)
        mid = (t[1:] + t[:-1]) / 2
        err = 0.0
        for u in mid:
            zq, rq = _evaluate(ctrl, U, float(u))
            err = max(err, abs(zq - face.sag(min(max(rq, 0.0), r_max))))
        if err <= PROFILE_TOLERANCE or n >= 129:
            return ctrl, U
        n = 2 * n - 1


# ---------------------------------------------------------------------------
# STEP (ISO 10303-21, AP214)
# ---------------------------------------------------------------------------


def _f(x: float) -> str:
    text = f"{x:.10G}"
    if "E" in text:
        mant, exp = text.split("E")
        return (mant if "." in mant else mant + ".") + "E" + exp
    return text if "." in text else text + "."


class _Step:
    def __init__(self):
        self.lines: list[str] = []

    def add(self, text: str) -> str:
        self.lines.append(text)
        return f"#{len(self.lines)}"

    def point(self, x, y, z) -> str:
        return self.add(f"CARTESIAN_POINT('',({_f(x)},{_f(y)},{_f(z)}))")

    def direction(self, x, y, z) -> str:
        return self.add(f"DIRECTION('',({_f(x)},{_f(y)},{_f(z)}))")

    def placement(self, z: float, axis=(0.0, 0.0, 1.0)) -> str:
        loc = self.point(0, 0, z)
        ax = self.direction(*axis)
        ref = self.direction(1, 0, 0)
        return self.add(f"AXIS2_PLACEMENT_3D('',{loc},{ax},{ref})")


def _outward(face: Face, z: float, r: float) -> tuple[float, float]:
    """Outward normal (z, r) of the solid on a face (left of travel)."""
    tz, tr = face.b[0] - face.a[0], face.b[1] - face.a[1]
    if face.kind == "surface":  # tangent of the profile at r
        eps = 1e-6 * max(abs(face.a[1] - face.b[1]), 1e-9)
        r0, r1 = max(r - eps, 0.0), r + eps
        dz = face.sag(r1) - face.sag(r0)
        dr = r1 - r0
        sign = 1.0 if tr >= 0 else -1.0  # travel outward (+r) or inward
        tz, tr = sign * dz, sign * dr
    return (-tr, tz)


def _step_body(st: _Step, body: Body) -> str:
    circles: dict[tuple[float, float], tuple[str, str]] = {}

    def circle_edge(z: float, r: float) -> tuple[str, str]:
        """(edge, vertex) of the circle through (z, r) about the axis."""
        key = (round(z, 9), round(r, 9))
        if key not in circles:
            c = st.add(f"CIRCLE('',{st.placement(z)},{_f(r)})")
            v = st.add(f"VERTEX_POINT('',{st.point(r, 0, z)})")
            circles[key] = (st.add(f"EDGE_CURVE('',{v},{v},{c},.T.)"), v)
        return circles[key]

    faces = []
    for face in body.faces:
        bounds = []
        rims = []  # (oriented edge, vertex) of the circles bounding the face
        # start circle: orientation .T., end circle: .F. (clockwise outline)
        for (z, r), sense in ((face.a, ".T."), (face.b, ".F.")):
            if r > 1e-12:
                edge, vertex = circle_edge(z, r)
                oe = st.add(f"ORIENTED_EDGE('',*,*,{edge},{sense})")
                rims.append((oe, vertex))
                loop = st.add(f"EDGE_LOOP('',({oe}))")
                bounds.append(st.add(f"FACE_BOUND('',{loop},.T.)"))
        zm = (face.a[0] + face.b[0]) / 2
        rm = (face.a[1] + face.b[1]) / 2
        if face.kind == "plane":
            out = _outward(face, zm, rm)
            surf = st.add(
                f"PLANE('',{st.placement(face.a[0], (0.0, 0.0, math.copysign(1.0, out[0])))})"
            )
            same = True
        elif face.kind == "cylinder":
            surf = st.add(
                f"CYLINDRICAL_SURFACE('',{st.placement(0.0)},{_f(face.a[1])})"
            )
            same = True
        else:
            s = face.surface
            assert s is not None
            r_mid = 0.5 * max(face.a[1], face.b[1])
            z_mid = face.sag(r_mid)
            out = _outward(face, z_mid, r_mid)
            if _is_plane(s):
                surf = st.add(
                    f"PLANE('',{st.placement(face.vertex_z, (0.0, 0.0, math.copysign(1.0, out[0])))})"
                )
                same = True
            elif _is_sphere(s):
                R = s.radius * MM
                surf = st.add(
                    f"SPHERICAL_SURFACE('',{st.placement(face.vertex_z + R)},{_f(abs(R))})"
                )
                cz = face.vertex_z + R
                natural = ((z_mid - cz), r_mid)  # (z, r) from the centre
                same = natural[0] * out[0] + natural[1] * out[1] > 0
            else:
                ctrl, U = profile_spline(face)
                cps = ",".join(st.point(r, 0.0, zq) for zq, r in ctrl)
                knots, mults = _knot_vector(U)
                curve = st.add(
                    f"B_SPLINE_CURVE_WITH_KNOTS('',3,({cps}),.UNSPECIFIED.,.F.,.F.,"
                    f"({','.join(str(m) for m in mults)}),({','.join(_f(k) for k in knots)}),"
                    ".UNSPECIFIED.)"
                )
                axis = st.add(
                    f"AXIS1_PLACEMENT('',{st.point(0, 0, face.vertex_z)},{st.direction(0, 0, 1)})"
                )
                surf = st.add(f"SURFACE_OF_REVOLUTION('',{curve},{axis})")
                # A revolved cap is bounded by its rim and its seam (the
                # profile from the rim to the pole, used in both senses).
                ((rim_oe, rim_v),) = rims
                apex = st.add(f"VERTEX_POINT('',{st.point(0, 0, face.vertex_z)})")
                seam = st.add(f"EDGE_CURVE('',{rim_v},{apex},{curve},.F.)")
                down = st.add(f"ORIENTED_EDGE('',*,*,{seam},.T.)")
                up = st.add(f"ORIENTED_EDGE('',*,*,{seam},.F.)")
                loop = st.add(f"EDGE_LOOP('',({rim_oe},{down},{up}))")
                bounds = [st.add(f"FACE_BOUND('',{loop},.T.)")]
                # natural normal of a revolved profile from the axis outward:
                # dS/du x dS/dv = (-dz, dr) in (r, z), i.e. (z: dr, r: -dz)
                eps = 1e-6 * max(face.a[1], face.b[1])
                dz = face.sag(r_mid + eps) - face.sag(r_mid - eps)
                natural = (2 * eps, -dz)
                same = natural[0] * out[0] + natural[1] * out[1] > 0
        faces.append(
            st.add(
                f"ADVANCED_FACE('',({','.join(bounds)}),{surf},{'.T.' if same else '.F.'})"
            )
        )
    shell = st.add(f"CLOSED_SHELL('',({','.join(faces)}))")
    return st.add(f"MANIFOLD_SOLID_BREP('{_quote(body.name)}',{shell})")


def _knot_vector(U: np.ndarray) -> tuple[list[float], list[int]]:
    knots: list[float] = []
    mults: list[int] = []
    for u in U:
        if knots and abs(u - knots[-1]) < 1e-14:
            mults[-1] += 1
        else:
            knots.append(float(u))
            mults.append(1)
    return knots, mults


def _quote(text: str) -> str:
    return text.replace("'", "''").encode("ascii", "replace").decode()


def write_step(
    lens: LensData,
    edge_margin: float = 1e-3,
    mirror_thickness: Optional[float] = None,
) -> tuple[str, list[str]]:
    """STEP AP214 text of the lens's elements and the warnings."""
    bodies, warnings = lens_bodies(lens, edge_margin, mirror_thickness)
    if not bodies:
        raise ValueError(
            "No element can be exported: " + ("; ".join(warnings) or "no glass")
        )
    st = _Step()
    app = st.add("APPLICATION_CONTEXT('automotive design')")
    st.add(
        f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,{app})"
    )
    pctx = st.add(f"PRODUCT_CONTEXT('',{app},'mechanical')")
    name = _quote(lens.name or "lens")
    prod = st.add(f"PRODUCT('{name}','{name}','Kestrova optical elements',({pctx}))")
    form = st.add(f"PRODUCT_DEFINITION_FORMATION('','',{prod})")
    dctx = st.add(f"PRODUCT_DEFINITION_CONTEXT('part definition',{app},'design')")
    pdef = st.add(f"PRODUCT_DEFINITION('design','',{form},{dctx})")
    pshape = st.add(f"PRODUCT_DEFINITION_SHAPE('','',{pdef})")
    mm = st.add("(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))")
    rad = st.add("(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.))")
    sr = st.add("(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT())")
    unc = st.add(
        f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-06),{mm},'distance_accuracy_value',"
        "'confusion accuracy')"
    )
    ctx = st.add(
        f"(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({unc}))"
        f"GLOBAL_UNIT_ASSIGNED_CONTEXT(({mm},{rad},{sr}))REPRESENTATION_CONTEXT('',''))"
    )
    origin = st.placement(0.0)
    solids = [_step_body(st, b) for b in bodies]
    rep = st.add(
        f"ADVANCED_BREP_SHAPE_REPRESENTATION('',({origin},{','.join(solids)}),{ctx})"
    )
    st.add(f"SHAPE_DEFINITION_REPRESENTATION({pshape},{rep})")
    now = _dt.datetime.now().replace(microsecond=0).isoformat()
    head = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('Kestrova optical elements'),'2;1');",
        f"FILE_NAME('{name}.step','{now}',('Kestrova'),(''),'Kestrova','Kestrova','');",
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));",
        "ENDSEC;",
        "DATA;",
    ]
    data = [f"#{k}={line};" for k, line in enumerate(st.lines, start=1)]
    return "\n".join(head + data + ["ENDSEC;", "END-ISO-10303-21;", ""]), warnings


# ---------------------------------------------------------------------------
# IGES 5.3
# ---------------------------------------------------------------------------


class _Iges:
    def __init__(self):
        self.entities: list[tuple[int, list, int, int]] = (
            []
        )  # type, params, status, form

    def add(
        self, etype: int, params: list, subordinate: bool = False, form: int = 0
    ) -> int:
        self.entities.append((etype, params, 1 if subordinate else 0, form))
        return 2 * len(self.entities) - 1  # DE pointer

    @staticmethod
    def _num(x) -> str:
        if isinstance(x, int):
            return str(x)
        text = f"{float(x):.12G}"
        if "E" in text:
            mant, exp = text.split("E")
            return (mant if "." in mant else mant + ".") + "D" + exp
        return text if "." in text else text + "."

    def text(self, name: str) -> str:
        # Hollerith strings may not hold the delimiters (kept simple here)
        name = "".join(c if c.isalnum() or c in " -_." else "_" for c in name)[:60]

        def hstr(s: str) -> str:
            return f"{len(s)}H{s}"

        now = _dt.datetime.now().strftime("%Y%m%d.%H%M%S")
        g = [
            "1H,",
            "1H;",
            hstr(name),
            hstr(f"{name}.igs"),
            hstr("Kestrova"),
            hstr("Kestrova"),
            "32",
            "38",
            "6",
            "308",
            "15",
            hstr(name),
            "1.",
            "2",
            "2HMM",
            "1",
            "0.01",
            hstr(now),
            "1.E-06",
            "1000.",
            hstr("Kestrova"),
            hstr(""),
            "11",
            "0",
            hstr(now),
        ]
        start = ["Kestrova optical elements (surfaces of revolution, mm)"]
        glines = _wrap(",".join(g) + ";", 72)
        d_lines: list[str] = []
        p_lines: list[str] = []
        for k, (etype, params, status, form) in enumerate(self.entities):
            de = 2 * k + 1
            body = ",".join([str(etype)] + [self._num(p) for p in params]) + ";"
            chunks = _wrap(body, 64)
            pstart = len(p_lines) + 1
            for c in chunks:
                p_lines.append(f"{c:<64}{de:>8}")
            status_s = f"00{status:02d}0000"
            d_lines.append(
                f"{etype:>8}{pstart:>8}{0:>8}{0:>8}{0:>8}{0:>8}{0:>8}{0:>8}{status_s:>8}"
            )
            d_lines.append(
                f"{etype:>8}{0:>8}{0:>8}{len(chunks):>8}{form:>8}{'':>8}{'':>8}{'':>8}{0:>8}"
            )
        out = []
        out += [f"{line:<72}S{k:>7}" for k, line in enumerate(start, 1)]
        out += [f"{line:<72}G{k:>7}" for k, line in enumerate(glines, 1)]
        out += [f"{line:<72}D{k:>7}" for k, line in enumerate(d_lines, 1)]
        out += [f"{line:<72}P{k:>7}" for k, line in enumerate(p_lines, 1)]
        out.append(
            f"S{len(start):>7}G{len(glines):>7}D{len(d_lines):>7}P{len(p_lines):>7}".ljust(
                72
            )
            + f"T{1:>7}"
        )
        return "\n".join(out) + "\n"


def _wrap(text: str, width: int) -> list[str]:
    """Split parameter text at commas so each line fits the width."""
    lines, cur = [], ""
    for tok in text.split(","):
        piece = tok if not cur else "," + tok
        # a broken line keeps its trailing comma, which must fit too
        if cur and len(cur) + len(piece) > width - 1:
            lines.append(cur + ",")
            cur = tok
        else:
            cur += piece
    if cur:
        lines.append(cur)
    return lines


def _iges_profile(ig: _Iges, face: Face) -> int:
    """Generatrix of a face in the x-z plane (x = r): line, exact circular
    arc (rational quadratic B-spline) or cubic B-spline."""
    (za, ra), (zb, rb) = face.a, face.b
    if face.kind != "surface" or _is_plane(face.surface):  # type: ignore[arg-type]
        return ig.add(110, [ra, 0.0, za, rb, 0.0, zb], subordinate=True)
    s = face.surface
    assert s is not None
    if _is_sphere(s):
        R = s.radius * MM
        c = np.array([face.vertex_z + R, 0.0])  # (z, r) centre
        p0, p2 = np.array([za, ra]), np.array([zb, rb])
        v0, v2 = p0 - c, p2 - c
        half = math.acos(max(-1.0, min(1.0, float(v0 @ v2) / (abs(R) ** 2)))) / 2
        bis = (v0 + v2) / np.linalg.norm(v0 + v2)
        p1 = c + bis * abs(R) / math.cos(half)
        weights = [1.0, math.cos(half), 1.0]
        # K=2, degree 2, rational; knots 0 0 0 1 1 1
        arc: list[int | float] = [2, 2, 0, 0, 0, 0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
        arc += weights
        for z, r in (p0, p1, p2):
            arc += [float(r), 0.0, float(z)]
        arc += [0.0, 1.0, 0.0, 1.0, 0.0]
        return ig.add(126, arc, subordinate=True)
    ctrl, U = profile_spline(
        Face(face.kind, (face.vertex_z, 0.0), (0.0, max(ra, rb)), s, face.vertex_z)
    )
    if ra > rb:  # traversed inward: reverse the curve
        ctrl = ctrl[::-1]
        U = 1.0 - U[::-1]
    n = len(ctrl) - 1
    params: list[int | float] = [n, 3, 0, 0, 1, 0]
    params += [float(u) for u in U] + [1.0] * (n + 1)
    for z, r in ctrl:
        params += [float(r), 0.0, float(z)]
    params += [0.0, 1.0, 0.0, 1.0, 0.0]
    return ig.add(126, params, subordinate=True)


def write_iges(
    lens: LensData,
    edge_margin: float = 1e-3,
    mirror_thickness: Optional[float] = None,
) -> tuple[str, list[str]]:
    """IGES 5.3 text of the lens's element faces (surfaces of revolution)."""
    bodies, warnings = lens_bodies(lens, edge_margin, mirror_thickness)
    if not bodies:
        raise ValueError(
            "No element can be exported: " + ("; ".join(warnings) or "no glass")
        )
    ig = _Iges()
    for body in bodies:
        z0 = min(min(f.a[0], f.b[0]) for f in body.faces)
        z1 = max(max(f.a[0], f.b[0]) for f in body.faces)
        for face in body.faces:
            axis = ig.add(
                110, [0.0, 0.0, z0 - 1.0, 0.0, 0.0, z1 + 1.0], subordinate=True
            )
            gen = _iges_profile(ig, face)
            ig.add(120, [axis, gen, 0.0, 2 * math.pi])
    return ig.text(lens.name or "lens"), warnings
