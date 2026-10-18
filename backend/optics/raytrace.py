"""
Sequential ray-tracing core.

Every geometric and wavefront analysis in the engine is built on this
module. It converts an :class:`OpticalSystem` (components placed along the
axis) into an ordered list of surfaces and provides:

- **Paraxial (y-nu) ray tracing** and the first-order properties derived
  from it: effective focal length, back/front focal distance, principal
  planes, aperture stop, entrance/exit pupils, paraxial image, F-numbers,
  numerical apertures and the Lagrange invariant.
- **Exact 3D real-ray tracing** (vector Snell's law and the law of
  reflection) through spheres, conics, even/odd aspheres, Forbes
  Q-polynomial aspheres, Zernike sag surfaces, toroids, diffractive
  (phase) surfaces, ideal thin lenses and mirrors, with optical path length
  accumulated as sum(n * distance), aperture vignetting and total internal
  reflection detected per ray.
- **Ray aiming**: rays are aimed so that normalized pupil coordinates
  (px, py) land on the real aperture stop at (px, py) times its radius.
- **Seidel sums** (S_I..S_V, C_L, C_T) surface by surface (Welford,
  *Aberrations of Optical Systems*, ch. 8), including the aspheric
  contributions.

Modelling conventions
---------------------
- Units are meters; wavelengths in meters; indices relative to air.
- Light enters travelling in +z. Without mirrors, components are taken in
  order of position. With mirrors, the list order is the sequence and the
  direction of travel reverses at every mirror.
- A ``ThinLens`` is an *ideal paraxial lens*: it maps ray direction tangents
  as t' = t - (x, y)/f, which images every pair of conjugate planes without
  aberration. Its focal length holds at the system's reference wavelength
  (``analysis_settings.wavelength``) and scales with wavelength as
  (n_ref - 1)/(n(lambda) - 1) of its glass. Its optical-path term
  makes every ray from the lens's paraxial object point to the conjugate
  image point equal in length to the ray through the vertex, so the lens
  itself adds no wavefront aberration at any conjugate.
- ``SphericalSurface`` and the aspheric components are single refracting
  surfaces; the medium after them is their ``material`` and persists until
  the next surface changes it. ``ThickLens`` is two refracting surfaces
  with the lens glass between them.
- A ``CoordinateBreak`` decenters and tilts the coordinate frame of every
  surface after it, pivoting about its own axial position.
- The object is treated as at infinity when it is more than
  ``INFINITE_OBJECT_DISTANCE`` from the first surface; the field angle is
  then atan(height / distance).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np
from scipy.special import eval_jacobi

from .materials import refractive_index, F_LINE, C_LINE, D_LINE
from .models import (
    OpticalSystem,
    ThinLens,
    ThickLens,
    SphericalSurface,
    ApertureStop,
    Mirror,
)
from .advanced_surfaces import (
    AsphericSurface,
    OddAsphericSurface,
    QAsphericSurface,
    ZernikeSurface,
    DiffractiveOpticalElement,
    ToricSurface,
    CoordinateBreak,
)

INFINITE_OBJECT_DISTANCE = 1.0e4  # meters
_FLAT_RADIUS = 1.0e9  # |R| at or above this is flat


def curvature_from_radius(radius: Optional[float]) -> float:
    if (
        radius is None
        or radius == 0
        or not math.isfinite(radius)
        or abs(radius) >= _FLAT_RADIUS
    ):
        return 0.0
    return 1.0 / radius


# =============================================================================
# Surface shapes (all in the surface's local frame, vertex at origin)
# =============================================================================


class Shape:
    """Base shape: a plane."""

    rotationally_symmetric = True

    def sag(self, x, y):
        return np.zeros(np.broadcast(x, y).shape)

    def grad(self, x, y):
        z = np.zeros(np.broadcast(x, y).shape)
        return z, z

    # Paraxial description: vertex curvature and the r^4 sag coefficient in
    # excess of the vertex sphere's own r^4 term (c^3/8).
    def vertex_curvature(self) -> float:
        return 0.0

    def quartic_excess(self) -> float:
        return 0.0

    def conic_base(self):
        """(c, k) of a conicoid the intersection can start from."""
        return self.vertex_curvature(), 0.0


class Conicoid(Shape):
    """Conic plus even (r^4, r^6, ...) and odd (r, r^3, ...) polynomial terms."""

    def __init__(self, c=0.0, k=0.0, even=(), odd=()):
        self.c, self.k = float(c), float(k)
        self.even = tuple(float(a) for a in even)
        self.odd = tuple(float(b) for b in odd)

    def _radial(self, r):
        c, k = self.c, self.k
        r2 = r * r
        arg = 1.0 - (1.0 + k) * c * c * r2
        root = np.sqrt(np.where(arg >= 0, arg, np.nan))
        s = c * r2 / (1.0 + root)
        ds = c * r / root
        for i, a in enumerate(self.even):
            p = 2 * i + 4
            s = s + a * r**p
            ds = ds + p * a * r ** (p - 1)
        for i, b in enumerate(self.odd):
            p = 2 * i + 1
            s = s + b * r**p
            ds = ds + p * b * r ** (p - 1)
        return s, ds

    def sag(self, x, y):
        return self._radial(np.hypot(x, y))[0]

    def grad(self, x, y):
        r = np.hypot(x, y)
        _, ds = self._radial(r)
        with np.errstate(invalid="ignore", divide="ignore"):
            fx = np.where(r > 0, ds * x / np.where(r > 0, r, 1.0), 0.0)
            fy = np.where(r > 0, ds * y / np.where(r > 0, r, 1.0), 0.0)
        return fx, fy

    def vertex_curvature(self):
        if self.odd and self.odd[0] != 0.0:
            raise ValueError("An r^1 odd-asphere term has no paraxial curvature")
        return self.c

    def quartic_excess(self):
        a4 = self.even[0] if self.even else 0.0
        return a4 + self.k * self.c**3 / 8.0

    def conic_base(self):
        return self.c, self.k


class RadialNumeric(Shape):
    """A rotationally symmetric sag given by a function of r."""

    def __init__(self, func, c_base=0.0, k_base=0.0, scale=1e-3):
        self.func = func
        self._c, self._k = c_base, k_base
        self.scale = scale

    def sag(self, x, y):
        return self.func(np.hypot(x, y))

    def grad(self, x, y):
        r = np.hypot(x, y)
        h = 1e-7 * self.scale
        # sag is even in r, so s(r - h) = s(|r - h|) gives a central difference
        ds = (self.func(r + h) - self.func(np.abs(r - h))) / (2 * h)
        with np.errstate(invalid="ignore", divide="ignore"):
            fx = np.where(r > 0, ds * x / np.where(r > 0, r, 1.0), 0.0)
            fy = np.where(r > 0, ds * y / np.where(r > 0, r, 1.0), 0.0)
        return fx, fy

    def _taylor(self):
        # Fit s(r) = a2 r^2 + a4 r^4 + a6 r^6 at small r.
        r = self.scale * np.array([0.02, 0.04, 0.06, 0.08])
        s = np.asarray(self.func(r), dtype=float)
        A = np.stack([r**2, r**4, r**6, r**8], axis=1)
        coef = np.linalg.solve(A, s)
        return coef[0], coef[1]

    def vertex_curvature(self):
        return 2.0 * self._taylor()[0]

    def quartic_excess(self):
        a2, a4 = self._taylor()
        c = 2.0 * a2
        return a4 - c**3 / 8.0

    def conic_base(self):
        return self._c, self._k


def _qbfs_basis(m_max: int) -> list:
    """
    Forbes Qbfs polynomials Q_0..Q_m_max as power-series coefficients in
    x = u^2. Built by Gram-Schmidt from their definition (G. W. Forbes, Opt.
    Express 15, 5218 (2007)): the departures u^2(1-u^2)Q_m(u^2) have
    orthonormal slopes under the weight 1/sqrt(1-u^2), normalised so Q_0 = 1.
    """
    t = np.linspace(0, np.pi / 2, 4001)[1:-1]
    # u = sin t gives du/sqrt(1-u^2) = dt (Gauss-Chebyshev style quadrature)
    u = np.sin(t)
    w = np.full_like(t, t[1] - t[0])

    def slope(coeffs):
        x = u * u
        q = np.polynomial.polynomial.polyval(x, coeffs)
        dq = (
            np.polynomial.polynomial.polyval(
                x, np.polynomial.polynomial.polyder(coeffs)
            )
            if len(coeffs) > 1
            else 0.0
        )
        return (2 * u - 4 * u**3) * q + (u**2 - u**4) * dq * 2 * u

    def ip(a, b):
        return float(np.sum(slope(a) * slope(b) * w))

    norm0 = ip([1.0], [1.0])
    basis: list = []
    for m in range(m_max + 1):
        v = np.zeros(m + 1)
        v[m] = 1.0
        for q in basis:
            proj = ip(v, q) / norm0
            vv = np.zeros(max(len(v), len(q)))
            vv[: len(v)] += v
            vv[: len(q)] -= proj * q
            v = vv
        v = v / math.sqrt(ip(v, v) / norm0)
        if v[0] < 0:
            v = -v
        basis.append(v)
    return basis


@lru_cache(maxsize=4)
def qbfs_basis(m_max: int) -> tuple:
    return tuple(tuple(b) for b in _qbfs_basis(m_max))


def q_aspheric_sag_function(c, k, coeffs, norm_radius, q_type):
    """Radial sag function of a Forbes Qbfs or Qcon asphere."""
    coeffs = [float(a) for a in coeffs]
    rn = float(norm_radius)
    qt = (q_type or "Qbfs").lower()
    if qt not in ("qbfs", "qcon"):
        raise ValueError(f"Unknown Q-polynomial type '{q_type}' (use 'Qbfs' or 'Qcon')")
    basis = (
        [np.array(b) for b in qbfs_basis(max(len(coeffs) - 1, 0))]
        if qt == "qbfs"
        else None
    )

    def f(r):
        r = np.asarray(r, dtype=float)
        r2 = r * r
        arg = 1.0 - (1.0 + k) * c * c * r2
        root = np.sqrt(np.where(arg >= 0, arg, np.nan))
        s = c * r2 / (1.0 + root)
        if not coeffs:
            return s
        u2 = r2 / (rn * rn)
        if qt == "qbfs":
            # Qbfs is defined on a sphere (k = 0): departure normal to it.
            arg0 = 1.0 - c * c * r2
            dep = sum(
                a * np.polynomial.polynomial.polyval(u2, b)
                for a, b in zip(coeffs, basis)
            )
            return s + u2 * (1.0 - u2) / np.sqrt(arg0) * dep
        dep = sum(
            a * eval_jacobi(m, 0, 4, 2.0 * u2 - 1.0) for m, a in enumerate(coeffs)
        )
        return s + u2 * u2 * dep

    return f


class ZernikeShape(Shape):
    """Sag = sum c_j Z_j(rho, theta) (Noll-normalised), rho = r / norm_radius."""

    rotationally_symmetric = False

    def __init__(self, coeffs, norm_radius):
        from .zernike import zernike_standard

        self.coeffs = [float(c) for c in coeffs]
        self.rn = float(norm_radius)
        self._z = zernike_standard

    def sag(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        rho = np.hypot(x, y) / self.rn
        th = np.arctan2(y, x)
        s = np.zeros(np.broadcast(x, y).shape)
        for j, c in enumerate(self.coeffs, start=1):
            if c:
                s = s + c * self._z(j, rho, th)
        return s

    def grad(self, x, y):
        h = 1e-7 * self.rn
        fx = (self.sag(x + h, y) - self.sag(x - h, y)) / (2 * h)
        fy = (self.sag(x, y + h) - self.sag(x, y - h)) / (2 * h)
        return fx, fy

    def vertex_curvature(self):
        # meridional (y-z) curvature at the vertex, from the r^2 term of the
        # sag along y
        r = self.rn * np.array([0.01, 0.02, 0.03])
        z = self.sag(np.zeros(3), r) - self.sag(0.0, 0.0)
        A = np.stack([r, r**2, r**3], axis=1)
        return 2.0 * np.linalg.solve(A, z)[1]


class YToroid(Shape):
    """
    Y-toroid (Code V 'YTO'): a conic in the y-z plane with vertex curvature
    cy, swept about an axis parallel to y at distance 1/cx from the vertex.
    cx = 0 gives a cylinder.
    """

    rotationally_symmetric = False

    def __init__(self, cy, cx, k=0.0):
        self.cy, self.cx, self.k = float(cy), float(cx), float(k)

    def _zy(self, y):
        arg = 1.0 - (1.0 + self.k) * self.cy**2 * y * y
        return self.cy * y * y / (1.0 + np.sqrt(np.where(arg >= 0, arg, np.nan)))

    def sag(self, x, y):
        zy = self._zy(np.asarray(y, dtype=float))
        if self.cx == 0.0:
            return zy + 0.0 * np.asarray(x)
        R = 1.0 / self.cx
        arg = (R - zy) ** 2 - np.asarray(x) ** 2
        return R - np.sign(R) * np.sqrt(np.where(arg >= 0, arg, np.nan))

    def grad(self, x, y):
        h = 1e-7
        fx = (self.sag(x + h, y) - self.sag(x - h, y)) / (2 * h)
        fy = (self.sag(x, y + h) - self.sag(x, y - h)) / (2 * h)
        return fx, fy

    def vertex_curvature(self):
        return self.cy  # meridional curvature

    def conic_base(self):
        return 0.0, 0.0


# =============================================================================
# Surfaces and sequences
# =============================================================================


@dataclass
class Surface:
    """One surface of the sequence."""

    kind: str  # refract | reflect | ideal | stop | dummy
    z: float  # vertex position along the local axis
    shape: Shape = field(default_factory=Shape)
    n_before: float = 1.0  # unsigned indices at the trace wavelength
    n_after: float = 1.0
    dn_before: float = 0.0  # n_F - n_C of the media (for colour sums)
    dn_after: float = 0.0
    semi_aperture: Optional[float] = None
    focal_length: Optional[float] = None  # ideal lens
    ideal_dispersion: float = 0.0  # 1/V of an ideal lens's glass
    phase: Optional[tuple] = None  # DOE: (coeffs, order)
    component_id: str = ""
    label: str = ""
    material_after: Optional[str] = None
    direction: int = 1  # +1 or -1: travel along local z after
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rotation: np.ndarray = field(default_factory=lambda: np.eye(3))

    @property
    def curvature(self) -> float:
        return self.shape.vertex_curvature()


@dataclass
class Sequence:
    surfaces: list
    wavelength: float
    object_z: float
    object_height: float
    object_infinite: bool
    image_z: float
    image_origin: np.ndarray
    image_rotation: np.ndarray
    image_direction: int
    n_object: float
    n_image: float
    stop_index: int


def _medium_index(material: Optional[str], wavelength: float) -> float:
    if not material or material.lower() == "air":
        return 1.0
    return refractive_index(material, wavelength)


def _medium_dn(material: Optional[str]) -> float:
    if not material or material.lower() == "air":
        return 0.0
    try:
        return refractive_index(material, F_LINE) - refractive_index(material, C_LINE)
    except ValueError:
        return 0.0


def _rotation(tx, ty, tz):
    """Rotation matrix for tilts about x, then y, then z (radians)."""
    cx, sx = math.cos(tx), math.sin(tx)
    cy, sy = math.cos(ty), math.sin(ty)
    cz, sz = math.cos(tz), math.sin(tz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def ordered_components(system: OpticalSystem) -> list:
    comps = list(system.components)
    if any(isinstance(c, Mirror) for c in comps):
        return comps
    return sorted(comps, key=lambda c: c.position)


def ideal_lens_focal_length(
    lens: ThinLens, wavelength: float, reference_wavelength: float
) -> float:
    """
    Focal length of a ThinLens at a wavelength. The specified focal length
    holds at the reference wavelength and scales with the glass dispersion
    as (n_ref - 1) / (n(lambda) - 1).
    """
    f = lens.focal_length
    if not math.isfinite(f) or wavelength == reference_wavelength:
        return f
    nr = refractive_index(lens.material, reference_wavelength)
    nl = refractive_index(lens.material, wavelength)
    return f * (nr - 1.0) / (nl - 1.0)


def _shape_for(comp) -> Shape:
    if isinstance(comp, (SphericalSurface,)):
        return Conicoid(curvature_from_radius(comp.radius))
    if isinstance(comp, OddAsphericSurface):
        return Conicoid(
            curvature_from_radius(comp.radius),
            comp.conic,
            comp.aspheric_coeffs,
            comp.odd_coeffs,
        )
    if isinstance(comp, AsphericSurface):
        return Conicoid(
            curvature_from_radius(comp.radius), comp.conic, comp.aspheric_coeffs
        )
    if isinstance(comp, QAsphericSurface):
        c = curvature_from_radius(comp.radius)
        k = comp.conic if (comp.q_type or "").lower() == "qcon" else 0.0
        func = q_aspheric_sag_function(
            c, k, comp.coefficients, comp.norm_radius, comp.q_type
        )
        return RadialNumeric(func, c, k, scale=comp.norm_radius)
    if isinstance(comp, ZernikeSurface):
        return ZernikeShape(comp.zernike_coeffs, comp.norm_radius)
    if isinstance(comp, ToricSurface):
        return YToroid(
            curvature_from_radius(comp.radius_tangential),
            curvature_from_radius(comp.radius_sagittal),
            comp.conic,
        )
    if isinstance(comp, Mirror):
        return Conicoid(curvature_from_radius(comp.radius), comp.conic)
    return Shape()


def build_sequence(
    system: OpticalSystem,
    wavelength: Optional[float] = None,
    index_offsets: Optional[dict] = None,
) -> Sequence:
    """
    Convert a system into its surface sequence at one wavelength.

    ``index_offsets`` maps a material name to an index change added to it
    (used for temperature and melt-tolerance analyses).
    """
    if wavelength is None:
        wavelength = system.analysis_settings.wavelength
    offsets = index_offsets or {}

    def med_index(material):
        n = _medium_index(material, wavelength)
        if material and material in offsets:
            n += offsets[material]
        return n

    surfaces: list[Surface] = []
    medium: Optional[str] = None
    direction = 1
    O = np.zeros(3)  # global position of the frame's pivot
    R = np.eye(3)  # frame rotation
    pivot = 0.0  # axial coordinate of the pivot

    def frame(z):
        # global position of the point at axial coordinate z on the current axis
        return O + R @ np.array([0.0, 0.0, z - pivot])

    def add(kind, z, shape=None, new_medium=None, keep_medium=True, **kw):
        nonlocal medium
        n_b = med_index(medium)
        dn_b = _medium_dn(medium)
        after = medium if keep_medium else new_medium
        s = Surface(
            kind=kind,
            z=z,
            shape=shape or Shape(),
            n_before=n_b,
            n_after=med_index(after),
            dn_before=dn_b,
            dn_after=_medium_dn(after),
            material_after=after,
            direction=direction,
            origin=frame(z),
            rotation=R.copy(),
            **kw,
        )
        surfaces.append(s)
        medium = after
        return s

    for comp in ordered_components(system):
        cid = comp.id
        if isinstance(comp, CoordinateBreak):
            # New frame: decenter and tilt about this axial position.
            p_old = frame(comp.position)
            dec = np.array([comp.decenter_x, comp.decenter_y, comp.decenter_z])
            R_new = R @ _rotation(comp.tilt_x, comp.tilt_y, comp.tilt_z)
            if comp.order == "decenter_then_tilt":
                O = p_old + R @ dec
            else:
                O = p_old + R_new @ dec
            R = R_new
            pivot = comp.position
            continue
        if isinstance(comp, ThinLens):
            f = ideal_lens_focal_length(
                comp, wavelength, system.analysis_settings.wavelength
            )
            try:
                nd = refractive_index(comp.material, D_LINE)
                V = (nd - 1.0) / (
                    refractive_index(comp.material, F_LINE)
                    - refractive_index(comp.material, C_LINE)
                )
                inv_v = 1.0 / V
            except ValueError:
                inv_v = 0.0
            add(
                "ideal",
                comp.position,
                focal_length=f,
                ideal_dispersion=inv_v,
                semi_aperture=comp.aperture_diameter / 2.0,
                component_id=cid,
                label=f"{cid}",
            )
        elif isinstance(comp, ThickLens):
            outer = medium
            semi = comp.aperture_diameter / 2.0
            z1 = comp.position
            z2 = comp.position + direction * comp.thickness
            add(
                "refract",
                z1,
                Conicoid(curvature_from_radius(comp.radius1)),
                new_medium=comp.material,
                keep_medium=False,
                semi_aperture=semi,
                component_id=cid,
                label=f"{cid}.front",
            )
            add(
                "refract",
                z2,
                Conicoid(curvature_from_radius(comp.radius2)),
                new_medium=outer,
                keep_medium=False,
                semi_aperture=semi,
                component_id=cid,
                label=f"{cid}.back",
            )
        elif isinstance(comp, SphericalSurface):
            surf_semi = comp.aperture_diameter / 2.0 if comp.aperture_diameter else None
            add(
                "refract",
                comp.position,
                _shape_for(comp),
                new_medium=comp.material,
                keep_medium=False,
                semi_aperture=surf_semi,
                component_id=cid,
                label=cid,
            )
        elif isinstance(comp, DiffractiveOpticalElement):
            add(
                "refract",
                comp.position,
                Shape(),
                new_medium=comp.material,
                keep_medium=False,
                semi_aperture=comp.aperture_diameter / 2.0,
                phase=(tuple(comp.phase_coeffs), comp.diffraction_order),
                component_id=cid,
                label=cid,
            )
        elif isinstance(
            comp,
            (
                AsphericSurface,
                OddAsphericSurface,
                QAsphericSurface,
                ZernikeSurface,
                ToricSurface,
            ),
        ):
            add(
                "refract",
                comp.position,
                _shape_for(comp),
                new_medium=comp.material,
                keep_medium=False,
                semi_aperture=comp.aperture_diameter / 2.0,
                component_id=cid,
                label=cid,
            )
        elif isinstance(comp, ApertureStop):
            add(
                "stop",
                comp.position,
                semi_aperture=comp.diameter / 2.0,
                component_id=cid,
                label=cid,
            )
        elif isinstance(comp, Mirror):
            semi = (comp.aperture_diameter or comp.width) / 2.0
            s = add(
                "reflect",
                comp.position,
                _shape_for(comp),
                semi_aperture=semi,
                component_id=cid,
                label=f"{cid}.mirror",
            )
            direction = -direction
            s.direction = direction
        else:
            raise ValueError(f"Unsupported component type: {type(comp).__name__}")

    # Check that the sequence moves consistently along the axis.
    prev_z = system.object.position
    d = 1
    for s in surfaces:
        if (s.z - prev_z) * d < -1e-12:
            raise ValueError(
                f"Surface {s.label} at z={s.z:.6g} m lies behind the light "
                f"travelling {'+' if d > 0 else '-'}z from z={prev_z:.6g} m; "
                "list components in the order light meets them."
            )
        prev_z = s.z
        d = s.direction

    if not surfaces:
        raise ValueError("System has no optical surfaces")

    first_z = surfaces[0].z
    obj_dist = first_z - system.object.position
    infinite = obj_dist > INFINITE_OBJECT_DISTANCE
    stop_index = _find_stop(surfaces, system, wavelength)
    return Sequence(
        surfaces=surfaces,
        wavelength=wavelength,
        object_z=system.object.position,
        object_height=system.object.height,
        object_infinite=infinite,
        image_z=system.image_plane.position,
        image_origin=frame(system.image_plane.position),
        image_rotation=R.copy(),
        image_direction=direction,
        n_object=1.0,
        n_image=med_index(medium),
        stop_index=stop_index,
    )


# =============================================================================
# Paraxial trace
# =============================================================================


def _surface_power(s: Surface, nb: float, na: float) -> float:
    """Power phi with signed indices nb, na (n'u' = nu - y phi)."""
    if s.kind == "ideal":
        f = s.focal_length
        assert f is not None  # every ideal surface carries one
        return 0.0 if not math.isfinite(f) else 1.0 / f * abs(nb)
    if s.phase is not None:
        coeffs, order = s.phase
        c1 = coeffs[0] if coeffs else 0.0
        # psi = (m lambda / 2pi) Phi ; psi ~ -phi r^2 / 2  =>  phi = -2 c1 m lambda/2pi
        return -2.0 * c1 * order * s_wavelength_holder[0] / (2 * math.pi)
    if s.kind in ("stop", "dummy"):
        return 0.0
    return s.curvature * (na - nb)


# wavelength of the sequence being traced (needed by DOE power)
s_wavelength_holder = [D_LINE]


def signed_indices(seq: Sequence) -> list:
    """(n_before, n_after) with the sign of the travel direction."""
    out = []
    d = 1
    for s in seq.surfaces:
        nb = d * s.n_before
        d_after = s.direction
        na = d_after * s.n_after
        out.append((nb, na))
        d = d_after
    return out


@dataclass
class ParaxialRay:
    y: np.ndarray  # height at each surface
    nu_before: np.ndarray
    nu_after: np.ndarray
    u_before: np.ndarray
    u_after: np.ndarray
    y_object_space: float  # height at the first surface
    u_object_space: float


def paraxial_trace(seq: Sequence, y1: float, u0: float) -> ParaxialRay:
    """
    Trace a paraxial ray that arrives at the first surface at height y1 with
    slope u0 (object space, travelling +z).
    """
    s_wavelength_holder[0] = seq.wavelength
    idx = signed_indices(seq)
    n = len(seq.surfaces)
    ys = np.zeros(n)
    nub = np.zeros(n)
    nua = np.zeros(n)
    ub = np.zeros(n)
    ua = np.zeros(n)
    y = y1
    nu = idx[0][0] * u0
    for i, s in enumerate(seq.surfaces):
        nb, na = idx[i]
        if i > 0:
            t = s.z - seq.surfaces[i - 1].z
            y = y + t * nu / idx[i - 1][1]
        ys[i] = y
        nub[i] = nu
        ub[i] = nu / nb
        phi = _surface_power(s, nb, na)
        nu = nu - y * phi
        nua[i] = nu
        ua[i] = nu / na
    return ParaxialRay(ys, nub, nua, ub, ua, y1, u0)


def _ray_at_first_surface_from_object(seq: Sequence, h: float, u: float):
    """(y1, u0) for a ray from object height h with slope u (finite object)."""
    d = seq.surfaces[0].z - seq.object_z
    return h + u * d, u


def _find_stop(surfaces: list, system: OpticalSystem, wavelength: float) -> int:
    for i, s in enumerate(surfaces):
        if s.kind == "stop":
            return i
    # No explicit stop: the surface that limits an axial ray's height.
    seq = Sequence(
        surfaces,
        wavelength,
        system.object.position,
        system.object.height,
        (surfaces[0].z - system.object.position) > INFINITE_OBJECT_DISTANCE,
        system.image_plane.position,
        np.zeros(3),
        np.eye(3),
        1,
        1.0,
        1.0,
        0,
    )
    if seq.object_infinite:
        pr = paraxial_trace(seq, 1.0, 0.0)
    else:
        y1, u0 = _ray_at_first_surface_from_object(seq, 0.0, 1.0)
        pr = paraxial_trace(seq, y1, u0)
    best, best_ratio = 0, math.inf
    for i, s in enumerate(surfaces):
        if s.semi_aperture is None or abs(pr.y[i]) < 1e-300:
            continue
        ratio = s.semi_aperture / abs(pr.y[i])
        if ratio < best_ratio - 1e-12:
            best, best_ratio = i, ratio
    return best


@dataclass
class FirstOrder:
    """First-order (paraxial) properties of a system at one wavelength."""

    wavelength: float
    efl: float  # effective focal length (inf if afocal)
    power: float
    bfl: float  # last surface to rear focal point
    ffl: float  # first surface to front focal point (signed, front)
    rear_principal_z: float
    front_principal_z: float
    rear_focal_z: float
    front_focal_z: float
    stop_index: int
    stop_semi_diameter: float
    entrance_pupil_z: float
    entrance_pupil_semi_diameter: float
    exit_pupil_z: float
    exit_pupil_semi_diameter: float
    image_z: float  # paraxial image position
    image_height: float  # paraxial image height of the field edge
    magnification: float  # transverse magnification (0 at infinity)
    object_infinite: bool
    field_angle: float  # radians (object at infinity)
    f_number: float  # EFL / entrance pupil diameter
    working_f_number: float  # 1 / (2 n' |u'|) of the marginal ray
    na_image: float  # n' |u'| of the marginal ray (paraxial)
    na_object: float
    lagrange_invariant: float
    n_image: float
    marginal: ParaxialRay
    chief: ParaxialRay


def _solve_linear(f0, f1, target):
    """Given values f(0)=f0 and f(1)=f1 of a linear function, return x with f(x)=target."""
    if abs(f1 - f0) < 1e-300:
        raise ValueError("Degenerate paraxial ray construction")
    return (target - f0) / (f1 - f0)


_ROUNDOFF = 1e-10


def _angle_is_zero(u: float, trace, span: float, z_scale: float = 0.0) -> bool:
    """True when a paraxial angle is zero to round-off, judged against the
    largest angle and height/span in the same trace (an afocal output
    otherwise shows up as an image ~1e14 m away). Surface positions far
    from the origin carry absolute round-off ~eps * |z|, which perturbs the
    spacings by that relative amount."""
    scale = max(
        max((abs(v) for v in trace.u_after), default=0.0),
        max((abs(v) for v in trace.y), default=0.0) / span,
    )
    tol = max(_ROUNDOFF, 64.0 * np.finfo(float).eps * z_scale / span)
    return abs(u) <= tol * scale


def first_order(
    system: OpticalSystem,
    wavelength: Optional[float] = None,
    seq: Optional[Sequence] = None,
) -> FirstOrder:
    """Compute all first-order properties from paraxial ray traces."""
    if seq is None:
        seq = build_sequence(system, wavelength)
    surfaces = seq.surfaces
    st = seq.stop_index
    stop = surfaces[st]
    if stop.semi_aperture is None:
        raise ValueError("The aperture stop has no defined diameter")
    idx = signed_indices(seq)
    n_img = idx[-1][1]
    last = surfaces[-1]

    span = max(abs(last.z - surfaces[0].z), 1e-3)
    z_scale = max(abs(sf.z) for sf in surfaces)

    # Power: parallel ray of unit height.
    pr = paraxial_trace(seq, 1.0, 0.0)
    nu_out = pr.nu_after[-1]
    afocal = _angle_is_zero(pr.u_after[-1], pr, span, z_scale)
    power = 0.0 if afocal else -nu_out / 1.0
    efl = math.inf if power == 0.0 else 1.0 / power
    u_out = pr.u_after[-1]
    if not afocal:
        rear_focal_z = last.z - pr.y[-1] / u_out
        bfl = (rear_focal_z - last.z) * seq.image_direction  # along the travel
    else:
        rear_focal_z = bfl = math.inf
    rear_principal_z = rear_focal_z - (n_img * efl if math.isfinite(efl) else 0.0)

    # Front focal point: ray leaving parallel in image space, traced via
    # linearity: find the object-space ray with u_out = 0 through height 1 at
    # the first surface.
    a = paraxial_trace(seq, 1.0, 0.0)
    b = paraxial_trace(seq, 1.0, 1.0)
    if abs(b.u_after[-1] - a.u_after[-1]) > 1e-300 and math.isfinite(efl):
        s_par = _solve_linear(a.u_after[-1], b.u_after[-1], 0.0)
        u0 = s_par
        front_focal_z = surfaces[0].z - 1.0 / u0 if abs(u0) > 1e-300 else -math.inf
        ffl = surfaces[0].z - front_focal_z
        front_principal_z = front_focal_z + efl
    else:
        front_focal_z = front_principal_z = -math.inf
        ffl = math.inf

    # Marginal ray: axial object point to stop edge.
    if seq.object_infinite:
        m0 = paraxial_trace(seq, 0.0, 0.0)
        m1 = paraxial_trace(seq, 1.0, 0.0)
        k = _solve_linear(m0.y[st], m1.y[st], stop.semi_aperture)
        marginal = paraxial_trace(seq, k, 0.0)
    else:
        y1a, u0a = _ray_at_first_surface_from_object(seq, 0.0, 0.0)
        y1b, u0b = _ray_at_first_surface_from_object(seq, 0.0, 1.0)
        m0 = paraxial_trace(seq, y1a, u0a)
        m1 = paraxial_trace(seq, y1b, u0b)
        k = _solve_linear(m0.y[st], m1.y[st], stop.semi_aperture)
        y1, u0 = _ray_at_first_surface_from_object(seq, 0.0, k)
        marginal = paraxial_trace(seq, y1, u0)

    # Chief ray: field edge through stop centre.
    first_z = surfaces[0].z
    if seq.object_infinite:
        dist = first_z - seq.object_z
        u_field = seq.object_height / dist
        c0 = paraxial_trace(seq, 0.0, u_field)
        c1 = paraxial_trace(seq, 1.0, u_field)
        k = _solve_linear(c0.y[st], c1.y[st], 0.0)
        chief = paraxial_trace(seq, k, u_field)
        field_angle = math.atan(u_field)
    else:
        h = seq.object_height
        y1a, u0a = _ray_at_first_surface_from_object(seq, h, 0.0)
        y1b, u0b = _ray_at_first_surface_from_object(seq, h, 1.0)
        c0 = paraxial_trace(seq, y1a, u0a)
        c1 = paraxial_trace(seq, y1b, u0b)
        k = _solve_linear(c0.y[st], c1.y[st], 0.0)
        y1, u0 = _ray_at_first_surface_from_object(seq, h, k)
        chief = paraxial_trace(seq, y1, u0)
        field_angle = 0.0

    # Pupils (paraxial images of the stop), located with a chief ray of
    # nominal field: pupil positions do not depend on the field size.
    if seq.object_infinite:
        q0 = paraxial_trace(seq, 0.0, 1e-3)
        q1 = paraxial_trace(seq, 1.0, 1e-3)
        kq = _solve_linear(q0.y[st], q1.y[st], 0.0)
        pupil_chief = paraxial_trace(seq, kq, 1e-3)
    else:
        hq = 1e-3
        y1a, u0a = _ray_at_first_surface_from_object(seq, hq, 0.0)
        y1b, u0b = _ray_at_first_surface_from_object(seq, hq, 1.0)
        q0 = paraxial_trace(seq, y1a, u0a)
        q1 = paraxial_trace(seq, y1b, u0b)
        kq = _solve_linear(q0.y[st], q1.y[st], 0.0)
        y1, u0 = _ray_at_first_surface_from_object(seq, hq, kq)
        pupil_chief = paraxial_trace(seq, y1, u0)
    if abs(pupil_chief.u_object_space) > 1e-300:
        ep_z = first_z - pupil_chief.y_object_space / pupil_chief.u_object_space
    else:
        ep_z = math.inf
    if seq.object_infinite:
        ep_semi = abs(marginal.y_object_space)
    elif math.isfinite(ep_z):
        ep_semi = abs(
            marginal.y_object_space + marginal.u_object_space * (ep_z - first_z)
        )
    else:
        ep_semi = math.inf
    uc_out = pupil_chief.u_after[-1]
    if not _angle_is_zero(uc_out, pupil_chief, span, z_scale):
        xp_z = last.z - pupil_chief.y[-1] / uc_out
        xp_semi = abs(marginal.y[-1] + marginal.u_after[-1] * (xp_z - last.z))
    else:
        xp_z, xp_semi = math.inf, math.inf

    # Paraxial image.
    um = marginal.u_after[-1]
    if not _angle_is_zero(um, marginal, span, z_scale):
        image_z = last.z - marginal.y[-1] / um
    else:
        image_z = math.inf
    if math.isfinite(image_z):
        image_height = chief.y[-1] + chief.u_after[-1] * (image_z - last.z)
    else:
        image_height = math.inf

    if seq.object_infinite:
        magnification = 0.0
        na_object = 0.0
    else:
        magnification = (
            image_height / seq.object_height
            if seq.object_height
            else (
                (marginal.nu_before[0]) / (marginal.nu_after[-1])
                if abs(marginal.nu_after[-1]) > 0
                else 0.0
            )
        )
        na_object = abs(marginal.nu_before[0])

    # Lagrange invariant H = n (u_bar y - u y_bar) at the first surface.
    H = idx[0][0] * (
        chief.u_before[0] * marginal.y[0] - marginal.u_before[0] * chief.y[0]
    )
    na_image = abs(marginal.nu_after[-1])
    epd = 2.0 * ep_semi
    f_number = abs(efl) / epd if math.isfinite(efl) and epd > 0 else math.inf
    working_f = 1.0 / (2.0 * na_image) if na_image > 0 else math.inf

    if not seq.object_infinite and not seq.object_height:
        image_height = 0.0
    return FirstOrder(
        wavelength=seq.wavelength,
        efl=efl,
        power=power,
        bfl=bfl,
        ffl=ffl,
        rear_principal_z=rear_principal_z,
        front_principal_z=front_principal_z,
        rear_focal_z=rear_focal_z,
        front_focal_z=front_focal_z,
        stop_index=st,
        stop_semi_diameter=stop.semi_aperture,
        entrance_pupil_z=ep_z,
        entrance_pupil_semi_diameter=ep_semi,
        exit_pupil_z=xp_z,
        exit_pupil_semi_diameter=xp_semi,
        image_z=image_z,
        image_height=image_height,
        magnification=magnification,
        object_infinite=seq.object_infinite,
        field_angle=field_angle,
        f_number=f_number,
        working_f_number=working_f,
        na_image=na_image,
        na_object=na_object,
        lagrange_invariant=H,
        n_image=abs(n_img),
        marginal=marginal,
        chief=chief,
    )


# =============================================================================
# Real ray tracing
# =============================================================================


@dataclass
class RayBundle:
    """Result of tracing N rays (arrays have a leading ray axis)."""

    points: np.ndarray  # (N, M+2, 3): start, each surface, image plane (global)
    directions: np.ndarray  # (N, 3) final unit direction (global)
    opl: np.ndarray  # (N,) optical path from the start to the image plane
    valid: np.ndarray  # (N,) bool
    image: np.ndarray  # (N, 3) image-plane intersection (global)
    n_image: float
    surface_opl: np.ndarray  # (N, M+1) cumulative OPL at each surface and image


def _to_local(s_origin, s_rot, p, d):
    pl = (p - s_origin) @ s_rot  # R^T (p - o) via row vectors
    dl = d @ s_rot
    return pl, dl


def _to_global(s_origin, s_rot, pl, dl):
    return pl @ s_rot.T + s_origin, dl @ s_rot.T


def _intersect(shape: Shape, p, d):
    """Intersect rays (local frame) with a shape; returns (t, point, ok)."""
    c, k = shape.conic_base()
    # Move to the vertex plane first.
    with np.errstate(divide="ignore", invalid="ignore"):
        t0 = -p[:, 2] / d[:, 2]
    q = p + t0[:, None] * d
    ok = np.isfinite(t0)
    x, y = q[:, 0], q[:, 1]
    dx, dy, dz = d[:, 0], d[:, 1], d[:, 2]
    if c != 0.0:
        A = c * (dx * dx + dy * dy) + c * (1.0 + k) * dz * dz
        B = 2.0 * (c * (x * dx + y * dy) - dz)
        C = c * (x * x + y * y)
        disc = B * B - 4.0 * A * C
        ok &= disc >= 0
        sq = np.sqrt(np.where(disc >= 0, disc, 0.0))
        denom = B + np.where(B >= 0, 1.0, -1.0) * sq  # stable small root
        with np.errstate(divide="ignore", invalid="ignore"):
            dt = np.where(np.abs(denom) > 0, -2.0 * C / denom, 0.0)
    else:
        dt = np.zeros_like(t0)
    t = t0 + dt
    # Newton refinement for the full sag.
    for _ in range(30):
        pt = p + t[:, None] * d
        s = shape.sag(pt[:, 0], pt[:, 1])
        f = pt[:, 2] - s
        gx, gy = shape.grad(pt[:, 0], pt[:, 1])
        df = d[:, 2] - gx * d[:, 0] - gy * d[:, 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            step = np.where(np.abs(df) > 1e-300, f / df, 0.0)
        step = np.where(np.isfinite(step), step, 0.0)
        t = t - step
        if np.nanmax(np.abs(step)) < 1e-15:
            break
    pt = p + t[:, None] * d
    s = shape.sag(pt[:, 0], pt[:, 1])
    ok &= np.isfinite(s) & (np.abs(pt[:, 2] - s) < 1e-9)
    return t, pt, ok


def _normals(shape: Shape, pt):
    gx, gy = shape.grad(pt[:, 0], pt[:, 1])
    nrm = np.stack([-gx, -gy, np.ones_like(gx)], axis=1)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    return nrm


def trace_bundle(
    seq: Sequence, p0: np.ndarray, d0: np.ndarray, clip: bool = True
) -> RayBundle:
    """
    Trace rays exactly through the sequence to the image plane.

    Args:
        seq: Surface sequence.
        p0: (N, 3) start points (global).
        d0: (N, 3) start directions (global, unit; must travel +z).
        clip: Mark rays outside any surface's semi-aperture as vignetted.
    """
    s_wavelength_holder[0] = seq.wavelength
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        return _trace_bundle(seq, p0, d0, clip)


def _ideal_object_distances(seq) -> dict:
    """For each ideal lens, the axial distance from its paraxial object point
    to the lens measured along the direction of travel (positive = real
    object before the lens, inf = collimated input)."""
    ideal = [i for i, s in enumerate(seq.surfaces) if s.kind == "ideal"]
    if not ideal:
        return {}
    if seq.object_infinite:
        pr = paraxial_trace(seq, 1.0, 0.0)
    else:
        y1, u0 = _ray_at_first_surface_from_object(seq, 0.0, 1e-3)
        pr = paraxial_trace(seq, y1, u0)
    idx = signed_indices(seq)
    span = max(abs(seq.surfaces[-1].z - seq.surfaces[0].z), 1e-3)
    out = {}
    for i in ideal:
        nu, y = pr.nu_before[i], pr.y[i]
        scale = max(np.max(np.abs(pr.u_before)), np.max(np.abs(pr.y)) / span)
        if abs(nu) <= 1e-12 * scale * abs(idx[i][0]):
            out[i] = math.inf
        else:
            out[i] = y * abs(idx[i][0]) / nu
    return out


def _signed_len(a, b, travel):
    """Length from a to b, negative when b lies behind a along the travel."""
    v = b - a
    return np.linalg.norm(v, axis=1) * np.where(v[:, 2] * travel >= 0, 1.0, -1.0)


def _ideal_lens_opl(hit, d_in, d_out, f, L, travel):
    """
    Optical path an ideal lens adds (per unit index), local frame with the
    lens at z = 0. P is the ray's object point (on the incoming line, axial
    distance L before the lens), P' its Gaussian image (axial distance L'
    after, 1/L' = 1/f - 1/L). The added path makes P -> X -> P' equal to
    P -> O -> P' (O the vertex); points at infinity use the plane-wave limit.
    """
    X = np.stack([hit[:, 0], hit[:, 1], np.zeros(len(hit))], axis=1)
    O = np.zeros_like(X)
    if math.isinf(L):
        inc = -np.sum(X * d_in, axis=1)
    else:
        P = X - d_in * (L / np.abs(d_in[:, 2]))[:, None]
        inc = _signed_len(P, O, travel) - _signed_len(P, X, travel)
    inv_lp = 1.0 / f - (0.0 if math.isinf(L) else 1.0 / L)
    if abs(inv_lp) * abs(f) < 1e-12:
        out = np.sum(X * d_out, axis=1)
    else:
        Lp = 1.0 / inv_lp
        Pp = X + d_out * (Lp / np.abs(d_out[:, 2]))[:, None]
        out = _signed_len(O, Pp, travel) - _signed_len(X, Pp, travel)
    return inc + out


def _trace_bundle(seq, p0, d0, clip):
    p = np.array(p0, dtype=float)
    d = np.array(d0, dtype=float)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    N = p.shape[0]
    M = len(seq.surfaces)
    pts = np.zeros((N, M + 2, 3))
    pts[:, 0] = p
    opl = np.zeros(N)
    sopl = np.zeros((N, M + 1))
    valid = np.ones(N, dtype=bool)
    n_cur = seq.surfaces[0].n_before
    lam = seq.wavelength
    ideal_L = _ideal_object_distances(seq)

    for i, s in enumerate(seq.surfaces):
        pl, dl = _to_local(s.origin, s.rotation, p, d)
        if s.kind in ("ideal", "stop", "dummy") or s.phase is not None:
            with np.errstate(divide="ignore", invalid="ignore"):
                t = -pl[:, 2] / dl[:, 2]
            hit = pl + t[:, None] * dl
            ok = np.isfinite(t)
        else:
            t, hit, ok = _intersect(s.shape, pl, dl)
        ok &= t > -1e-12
        valid &= ok
        hit = np.where(ok[:, None], hit, pl)
        t = np.where(ok, t, 0.0)
        opl = opl + n_cur * t
        r = np.hypot(hit[:, 0], hit[:, 1])
        if clip and s.semi_aperture is not None:
            valid &= r <= s.semi_aperture * (1 + 1e-9) + 1e-12

        travel = np.sign(dl[:, 2])
        if s.kind == "ideal":
            f = s.focal_length
            if math.isfinite(f):
                tx = dl[:, 0] / np.abs(dl[:, 2])
                ty = dl[:, 1] / np.abs(dl[:, 2])
                tx2 = tx - hit[:, 0] / f
                ty2 = ty - hit[:, 1] / f
                dn = np.stack([tx2, ty2, travel], axis=1)
                d_out = dn / np.linalg.norm(dn, axis=1, keepdims=True)
                tr = float(np.median(travel)) if N else 1.0
                opl = opl + n_cur * _ideal_lens_opl(
                    hit, dl, d_out, f, ideal_L.get(i, math.inf), tr
                )
                dl = d_out
        elif s.kind == "reflect":
            nrm = _normals(s.shape, hit)
            dot = np.sum(dl * nrm, axis=1)
            dl = dl - 2.0 * dot[:, None] * nrm
        elif s.kind == "refract":
            n1, n2 = s.n_before, s.n_after
            if s.phase is not None:
                coeffs, order = s.phase
                rr = r
                dphi = np.zeros(N)
                for j, cj in enumerate(coeffs):
                    pw = 2 * (j + 1)
                    dphi = dphi + pw * cj * rr ** (pw - 1)
                    opl = opl + order * lam / (2 * math.pi) * cj * rr**pw
                with np.errstate(invalid="ignore", divide="ignore"):
                    gx = np.where(
                        rr > 0, dphi * hit[:, 0] / np.where(rr > 0, rr, 1), 0.0
                    )
                    gy = np.where(
                        rr > 0, dphi * hit[:, 1] / np.where(rr > 0, rr, 1), 0.0
                    )
                kx = n1 * dl[:, 0] + order * lam / (2 * math.pi) * gx
                ky = n1 * dl[:, 1] + order * lam / (2 * math.pi) * gy
                tx, ty = kx / n2, ky / n2
                tz2 = 1.0 - tx * tx - ty * ty
                valid &= tz2 >= 0
                dl = np.stack([tx, ty, travel * np.sqrt(np.clip(tz2, 0, None))], axis=1)
            else:
                nrm = _normals(s.shape, hit)
                cos_i = np.sum(dl * nrm, axis=1)
                nrm = np.where(cos_i[:, None] < 0, -nrm, nrm)
                cos_i = np.abs(cos_i)
                mu = n1 / n2
                rad = 1.0 - mu * mu * (1.0 - cos_i * cos_i)
                valid &= rad >= 0
                cos_t = np.sqrt(np.clip(rad, 0, None))
                dl = mu * dl + (cos_t - mu * cos_i)[:, None] * nrm
            n_cur = n2
        p, d = _to_global(s.origin, s.rotation, hit, dl)
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        pts[:, i + 1] = p
        sopl[:, i] = opl
        if s.kind != "refract":
            n_cur = s.n_after

    # Image plane (perpendicular to the final local axis).
    o, Rm = seq.image_origin, seq.image_rotation
    pl, dl = _to_local(o, Rm, p, d)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = -pl[:, 2] / dl[:, 2]
    ok = np.isfinite(t)
    valid &= ok
    t = np.where(ok, t, 0.0)
    img_l = pl + t[:, None] * dl
    opl = opl + n_cur * t
    img, _ = _to_global(o, Rm, img_l, dl)
    pts[:, M + 1] = img
    sopl[:, M] = opl
    return RayBundle(pts, d, opl, valid, img, n_cur, sopl)


# =============================================================================
# Ray generation and aiming
# =============================================================================


def _start_rays(seq: Sequence, fo: FirstOrder, hx: float, hy: float, a, b):
    """
    Start points and directions for rays from field (hx, hy) (fractions of
    the object height) parameterised by (a, b): for a finite object, the
    direction tangents; at infinity, positions on the incident wavefront.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    N = a.size
    if seq.object_infinite:
        theta = fo.field_angle
        ux, uy = math.tan(theta) * hx, math.tan(theta) * hy
        dvec = np.array([ux, uy, 1.0])
        dvec /= np.linalg.norm(dvec)
        z_ref = seq.surfaces[0].z - _start_offset(seq)
        # points on the plane through (0,0,z_ref) perpendicular to dvec
        e1 = np.cross([0.0, 1.0, 0.0], dvec)
        if np.linalg.norm(e1) < 1e-12:
            e1 = np.array([1.0, 0.0, 0.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(dvec, e1)
        p = (
            np.array([0.0, 0.0, z_ref])[None, :]
            + a[:, None] * e1[None, :]
            + b[:, None] * e2[None, :]
        )
        d = np.tile(dvec, (N, 1))
    else:
        p = np.tile(
            [hx * seq.object_height, hy * seq.object_height, seq.object_z], (N, 1)
        )
        d = np.stack([a, b, np.ones(N)], axis=1)
        d /= np.linalg.norm(d, axis=1, keepdims=True)
    return p, d


def _start_offset(seq: Sequence) -> float:
    span = max((s.semi_aperture or 0.0) for s in seq.surfaces)
    return max(span, 1e-3) * 2.0


def _stop_coords(seq: Sequence, p0, d0):
    """Local (x, y) where rays cross the stop surface."""
    sub = Sequence(
        seq.surfaces[: seq.stop_index + 1],
        seq.wavelength,
        seq.object_z,
        seq.object_height,
        seq.object_infinite,
        seq.image_z,
        seq.surfaces[seq.stop_index].origin,
        seq.surfaces[seq.stop_index].rotation,
        1,
        seq.n_object,
        seq.n_image,
        seq.stop_index,
    )
    b = trace_bundle(sub, p0, d0, clip=False)
    s = seq.surfaces[seq.stop_index]
    pl = (b.points[:, seq.stop_index + 1] - s.origin) @ s.rotation
    return pl[:, 0], pl[:, 1], b.valid


def aim_rays(
    seq: Sequence,
    fo: FirstOrder,
    hx: float,
    hy: float,
    px: np.ndarray,
    py: np.ndarray,
    iterations: int = 12,
):
    """
    Starting rays for field (hx, hy) that cross the real stop at
    (px, py) * stop radius. Returns (p0, d0, converged).
    """
    px = np.atleast_1d(np.asarray(px, dtype=float))
    py = np.atleast_1d(np.asarray(py, dtype=float))
    rs = fo.stop_semi_diameter
    tx_target, ty_target = px * rs, py * rs

    # Paraxial initial guess: aim at the paraxial entrance pupil.
    ep_z, ep_r = fo.entrance_pupil_z, fo.entrance_pupil_semi_diameter
    if seq.object_infinite:
        theta = fo.field_angle
        dvec = np.array([math.tan(theta) * hx, math.tan(theta) * hy, 1.0])
        dvec /= np.linalg.norm(dvec)
        z_ref = seq.surfaces[0].z - _start_offset(seq)
        e1 = np.cross([0.0, 1.0, 0.0], dvec)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(dvec, e1)
        zt = ep_z if math.isfinite(ep_z) else seq.surfaces[seq.stop_index].z
        X = np.stack([px * ep_r, py * ep_r, np.full(px.shape, zt)], axis=1)
        rel = X - np.array([0.0, 0.0, z_ref])
        a = rel @ e1
        b = rel @ e2
    elif math.isfinite(ep_z) and abs(ep_z - seq.object_z) > 1e-12:
        dz = ep_z - seq.object_z
        a = (px * ep_r - hx * seq.object_height) / dz
        b = (py * ep_r - hy * seq.object_height) / dz
    else:
        um = fo.marginal.u_object_space
        a = px * um + hx * fo.chief.u_object_space
        b = py * um + hy * fo.chief.u_object_space

    a = np.array(a, dtype=float) * np.ones_like(px)
    b = np.array(b, dtype=float) * np.ones_like(px)
    scale = ep_r if seq.object_infinite else ep_r / max(abs(ep_z - seq.object_z), 1e-12)
    h = 1e-6 * max(scale, 1e-12)
    converged = np.zeros(px.size, dtype=bool)
    # Achievable accuracy is limited by round-off in the absolute coordinates
    # (objects "at infinity" sit ~1e6 m away).
    z_scale = max(abs(seq.object_z), max(abs(sf.z) for sf in seq.surfaces), 1.0)
    tol = max(1e-10 * max(rs, 1e-6), 64.0 * np.finfo(float).eps * z_scale)
    for _ in range(iterations):
        p0, d0 = _start_rays(seq, fo, hx, hy, a, b)
        x, y, ok = _stop_coords(seq, p0, d0)
        ex, ey = x - tx_target, y - ty_target
        err = np.hypot(ex, ey)
        converged = ok & (err < tol)
        if converged.all():
            break
        p1, d1 = _start_rays(seq, fo, hx, hy, a + h, b)
        x1, y1, _ = _stop_coords(seq, p1, d1)
        p2, d2 = _start_rays(seq, fo, hx, hy, a, b + h)
        x2, y2, _ = _stop_coords(seq, p2, d2)
        J11, J21 = (x1 - x) / h, (y1 - y) / h
        J12, J22 = (x2 - x) / h, (y2 - y) / h
        det = J11 * J22 - J12 * J21
        with np.errstate(divide="ignore", invalid="ignore"):
            da = np.where(np.abs(det) > 0, (J22 * ex - J12 * ey) / det, 0.0)
            db = np.where(np.abs(det) > 0, (-J21 * ex + J11 * ey) / det, 0.0)
        da = np.where(np.isfinite(da), da, 0.0)
        db = np.where(np.isfinite(db), db, 0.0)
        a = a - np.where(converged, 0.0, da)
        b = b - np.where(converged, 0.0, db)
    p0, d0 = _start_rays(seq, fo, hx, hy, a, b)
    return p0, d0, converged


def trace_field_rays(
    system: OpticalSystem,
    hx: float,
    hy: float,
    px,
    py,
    wavelength: Optional[float] = None,
    clip: bool = True,
    seq: Optional[Sequence] = None,
    fo: Optional[FirstOrder] = None,
):
    """Aim and trace rays for one field point. Returns (bundle, seq, fo)."""
    if seq is None:
        seq = build_sequence(system, wavelength)
    if fo is None:
        fo = first_order(system, seq=seq)
    p0, d0, conv = aim_rays(seq, fo, hx, hy, px, py)
    b = trace_bundle(seq, p0, d0, clip=clip)
    b.valid &= conv
    return b, seq, fo


def pupil_grid(n: int, shape: str = "square"):
    """Normalised pupil sample coordinates inside the unit circle."""
    if shape == "hexapolar":
        rings = max(1, n)
        xs, ys = [0.0], [0.0]
        for i in range(1, rings + 1):
            rho = i / rings
            m = 6 * i
            th = np.arange(m) * 2 * np.pi / m
            xs.extend(rho * np.cos(th))
            ys.extend(rho * np.sin(th))
        return np.array(xs), np.array(ys)
    g = np.linspace(-1.0, 1.0, n)
    X, Y = np.meshgrid(g, g)
    inside = X**2 + Y**2 <= 1.0 + 1e-12
    return X[inside], Y[inside]


# =============================================================================
# Wavefront (OPD) relative to the exit-pupil reference sphere
# =============================================================================


def opd(
    system: OpticalSystem,
    hx: float,
    hy: float,
    px,
    py,
    wavelength: Optional[float] = None,
    seq=None,
    fo=None,
):
    """
    Optical path difference W = OPL(chief) - OPL(ray), both measured to the
    reference sphere centred on the chief ray's image-plane point and passing
    through the paraxial exit pupil on the chief ray. When the image is at
    infinity (afocal image space) the reference is a plane wave normal to
    the chief ray.

    Returns (W array in meters, valid mask, bundle).
    """
    if seq is None:
        seq = build_sequence(system, wavelength)
    if fo is None:
        fo = first_order(system, seq=seq)
    px = np.atleast_1d(np.asarray(px, dtype=float))
    py = np.atleast_1d(np.asarray(py, dtype=float))
    allx = np.concatenate([[0.0], px])
    ally = np.concatenate([[0.0], py])
    b, _, _ = trace_field_rays(system, hx, hy, allx, ally, seq=seq, fo=fo)
    if not b.valid[0]:
        raise ValueError("The chief ray cannot be traced for this field")
    Q = b.image[0]
    dch = b.directions[0]
    o, Rm = seq.image_origin, seq.image_rotation
    # exit pupil point on the chief ray
    R = math.inf
    s_xp = -1.0
    if math.isfinite(fo.exit_pupil_z) and math.isfinite(fo.image_z):
        ql, dl = _to_local(o, Rm, Q[None, :], dch[None, :])
        # local z of the exit-pupil plane (the image plane is local z = 0)
        s_xp = ((fo.exit_pupil_z - seq.image_z) - ql[0, 2]) / dl[0, 2]
        R = abs(s_xp)
    n_img = b.n_image
    P = b.image
    D = b.directions
    if math.isfinite(R) and R > 0:
        w = P - Q
        bq = np.sum(w * D, axis=1)
        cq = np.sum(w * w, axis=1) - R * R
        disc = bq * bq - cq
        root = np.sqrt(np.where(disc >= 0, disc, np.nan))
        # the sphere point on the exit-pupil side of the image
        s = -bq - root if s_xp < 0 else -bq + root
        opl_sphere = b.opl + n_img * s
    else:
        # plane reference perpendicular to the chief ray through Q
        s = -np.sum((P - Q) * dch, axis=1) / np.sum(D * dch, axis=1)
        opl_sphere = b.opl + n_img * s
    # Sign: W = OPL(chief) - OPL(ray), so that the primary spherical term
    # equals S_I / 8 (Welford's convention).
    W = opl_sphere[0] - opl_sphere
    valid = b.valid & np.isfinite(W)
    return W[1:], valid[1:], b


# =============================================================================
# Seidel sums
# =============================================================================


@dataclass
class SeidelSums:
    per_surface: list  # dicts with S1..S5, CL, CT, label
    S1: float
    S2: float
    S3: float
    S4: float
    S5: float
    CL: float
    CT: float
    nu_image: float  # n'u' of the marginal ray in image space
    lagrange_invariant: float
    unsupported: list  # labels of surfaces with no Seidel description


def seidel_sums(
    system: OpticalSystem, wavelength: Optional[float] = None
) -> SeidelSums:
    """
    Third-order (Seidel) aberration sums from paraxial marginal and chief
    rays (Welford, Aberrations of Optical Systems, 1986, sections 8.2-8.5).

    Sign convention: S_I > 0 is under-corrected spherical aberration for a
    system forming a real image. The wavefront coefficients are
    W040 = S_I/8, W131 = S_II/2, W222 = S_III/2, W220 = (S_III+S_IV)/4,
    W311 = S_V/2.
    """
    seq = build_sequence(system, wavelength)
    fo = first_order(system, seq=seq)
    idx = signed_indices(seq)
    mr, cr = fo.marginal, fo.chief
    H = fo.lagrange_invariant
    rows = []
    tot = dict(S1=0.0, S2=0.0, S3=0.0, S4=0.0, S5=0.0, CL=0.0, CT=0.0)
    unsupported = []
    for i, s in enumerate(seq.surfaces):
        nb, na = idx[i]
        y, yb = mr.y[i], cr.y[i]
        u, ub = mr.u_before[i], cr.u_before[i]
        up = mr.u_after[i]
        row = dict(
            label=s.label, S1=0.0, S2=0.0, S3=0.0, S4=0.0, S5=0.0, CL=0.0, CT=0.0
        )
        if s.kind in ("stop", "dummy"):
            rows.append(row)
            continue
        if s.kind == "ideal":
            # A perfect lens adds no monochromatic aberration; its glass's
            # dispersion gives the thin-lens colour terms y^2 phi/V, y ybar phi/V.
            f = s.focal_length
            if math.isfinite(f):
                phi = 1.0 / f
                row["CL"] = y * y * phi * s.ideal_dispersion
                row["CT"] = y * yb * phi * s.ideal_dispersion
        elif not s.shape.rotationally_symmetric:
            unsupported.append(s.label)
        else:
            c = s.curvature
            A = nb * (u + y * c)
            Ab = nb * (ub + yb * c)
            d_u_n = up / na - u / nb
            d_1_n = 1.0 / na - 1.0 / nb
            S1 = -A * A * y * d_u_n
            S2 = -A * Ab * y * d_u_n
            S3 = -Ab * Ab * y * d_u_n
            S4 = -H * H * c * d_1_n
            # S_V = (Ab/A)(S_III + S_IV), written without the division using
            # u/n = A/n^2 - yc and Ab y - A yb = H:
            S5 = Ab * (
                -Ab * Ab * y * (1.0 / (na * na) - 1.0 / (nb * nb))
                + c * yb * (A * yb + 2.0 * H) * d_1_n
            )
            # Aspheric (conic / polynomial) contribution.
            q4 = s.shape.quartic_excess()
            if q4:
                dS1 = 8.0 * q4 * (na - nb) * y**4
                S1 += dS1
                if y != 0:
                    S2 += dS1 * (yb / y)
                    S3 += dS1 * (yb / y) ** 2
                    S5 += dS1 * (yb / y) ** 3
            # Colour (refraction only; mirrors are achromatic).
            CL = CT = 0.0
            if s.kind == "refract":
                dn_b = s.dn_before * (1 if nb > 0 else -1)
                dn_a = s.dn_after * (1 if na > 0 else -1)
                CL = A * y * (dn_a / na - dn_b / nb)
                CT = Ab * y * (dn_a / na - dn_b / nb)
            if s.phase is not None:
                unsupported.append(s.label)
            row.update(S1=S1, S2=S2, S3=S3, S4=S4, S5=S5, CL=CL, CT=CT)
        for key in tot:
            tot[key] += row[key]
        rows.append(row)
    return SeidelSums(
        rows,
        tot["S1"],
        tot["S2"],
        tot["S3"],
        tot["S4"],
        tot["S5"],
        tot["CL"],
        tot["CT"],
        mr.nu_after[-1],
        H,
        unsupported,
    )


# =============================================================================
# Real-ray focus and image measurements
# =============================================================================


def real_field_foci(
    system: OpticalSystem,
    hy: float,
    delta: float = 1e-3,
    wavelength: Optional[float] = None,
    seq=None,
    fo=None,
):
    """
    Tangential and sagittal foci of the field point (0, hy) from exact
    differential rays about the chief ray (pupil offsets +-delta).

    Returns (z_tangential, z_sagittal) as positions along the local axis,
    measured from the image plane (positive = further along the axis).
    """
    if seq is None:
        seq = build_sequence(system, wavelength)
    if fo is None:
        fo = first_order(system, seq=seq)
    px = np.array([0.0, 0.0, delta])
    py = np.array([delta, -delta, 0.0])
    b, _, _ = trace_field_rays(system, 0.0, hy, px, py, seq=seq, fo=fo, clip=False)
    if not b.valid.all():
        raise ValueError("Differential rays failed for this field")
    o, Rm = seq.image_origin, seq.image_rotation
    P, D = _to_local(o, Rm, b.image, b.directions)
    # tangential: intersection of the two meridional rays in the y-z plane
    m1 = D[0, 1] / D[0, 2]
    m2 = D[1, 1] / D[1, 2]
    zt = (P[1, 1] - P[0, 1]) / (m1 - m2) if m1 != m2 else math.inf
    # sagittal: where the skew ray crosses the meridional plane x = 0
    zs = -P[2, 0] / (D[2, 0] / D[2, 2]) if D[2, 0] != 0 else math.inf
    return zt, zs


def third_order_aberrations(sums: SeidelSums, fo: FirstOrder) -> dict:
    """
    Image-space third-order aberrations from the Seidel sums (Welford ch. 8),
    for the full aperture and full field. Transverse values are y-heights in
    the paraxial image plane; longitudinal values are along the axis from the
    paraxial image (positive = further along the direction of travel).
    """
    nu = sums.nu_image  # n' u'
    n_img = fo.n_image
    if abs(nu) < 1e-300 or not math.isfinite(fo.image_z):
        raise ValueError(
            "Afocal image space: third-order image aberrations undefined "
            "(image at infinity)"
        )
    nuu = nu * nu / n_img  # n' u'^2
    h_img = fo.image_height
    out = {
        "transverse_spherical": sums.S1 / (2.0 * nu),
        "longitudinal_spherical": -sums.S1 / (2.0 * nuu),
        "sagittal_coma": sums.S2 / (2.0 * nu),
        "tangential_coma": 3.0 * sums.S2 / (2.0 * nu),
        "sagittal_field_curvature": -(sums.S3 + sums.S4) / (2.0 * nuu),
        "tangential_field_curvature": -(3.0 * sums.S3 + sums.S4) / (2.0 * nuu),
        "petzval_field_curvature": -sums.S4 / (2.0 * nuu),
        "astigmatism": -(2.0 * sums.S3) / (2.0 * nuu),
        "distortion": sums.S5 / (2.0 * nu),
        "longitudinal_color": -sums.CL / nuu,
        "lateral_color": sums.CT / nu,
    }
    out["fractional_distortion"] = (out["distortion"] / h_img) if h_img else 0.0
    return out
