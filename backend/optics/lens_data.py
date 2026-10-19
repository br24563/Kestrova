"""
Surface-by-surface lens prescription (the Code V / Zemax lens data model).

A :class:`LensData` is an ordered list of :class:`LensSurface` rows. Each row
holds the surface's shape, the material after it and the *thickness to the
next surface*, so changing one thickness moves everything after it, as in
Code V. On top of the plain values a row can carry

- **variables**: parameters the optimizer may change;
- **solves**: parameters computed from paraxial rays every time the lens is
  resolved (Code V's height and angle solves);
- **pickups**: parameters copied from another surface as
  ``scale * source + offset``.

:func:`resolve` applies pickups and solves and fills unset clear apertures;
:func:`to_system` turns the resolved lens into the component-based
:class:`~optics.models.OpticalSystem` every analysis in the engine uses, and
:func:`from_system` goes the other way. Conversion both ways keeps the
optics identical (same surfaces, media, apertures and stop).

Conventions
-----------
- Lengths in meters, angles in radians; radius 0 means flat.
- ``material`` is the medium after the surface (None = air); ``"MIRROR"``
  reflects and keeps the medium. After a mirror light travels toward -z
  and thicknesses are negative, as in Zemax and Code V.
- Solve slopes are measured in the direction of travel (they keep their
  meaning after a mirror). An F-number solve sets the marginal-ray slope to
  -1/(2N) after the surface.
- Automatic semi-diameters (``semi_diameter=None``) are the largest real-ray
  height at the surface over the pupil edge at the axial, +field and -field
  points for every wavelength, so they never vignette those beams.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Literal, Optional

import numpy as np
from pydantic import BaseModel, Field, TypeAdapter, model_validator

from . import raytrace as rt
from .advanced_surfaces import AsphericSurface, CoordinateBreak
from .models import (
    AnalysisSettings,
    ApertureStop,
    FieldPoint,
    ImagePlane,
    Mirror,
    Object,
    OpticalComponent,
    OpticalSystem,
    SphericalSurface,
    ThickLens,
    ThinLens,
)

#: Object distance used for an object at infinity (beyond the engine's
#: INFINITE_OBJECT_DISTANCE, so it is traced as collimated).
FAR_OBJECT = 1.0e6
#: Aperture given to surfaces without a clear aperture while solving, large
#: enough never to limit the beam.
_PLACEHOLDER_SEMI = 100.0

SurfaceType = Literal[
    "standard", "even_asphere", "paraxial", "coordinate_break", "component"
]
SolveKind = Literal[
    "marginal_height", "chief_height", "marginal_angle", "chief_angle", "f_number"
]

THICKNESS_SOLVES = ("marginal_height", "chief_height")
RADIUS_SOLVES = ("marginal_angle", "chief_angle", "f_number")
_ASPHERE_ORDERS = tuple(range(4, 22, 2))  # A4 .. A20
_ASPHERE_PARAMS = tuple(f"asphere_{k}" for k in _ASPHERE_ORDERS)
_CB_PARAMS = ("decenter_x", "decenter_y", "decenter_z", "tilt_x", "tilt_y", "tilt_z")

#: Parameters each surface type has (all numeric).
PARAMETERS: dict[str, tuple[str, ...]] = {
    "standard": ("radius", "thickness", "conic", "semi_diameter"),
    "even_asphere": ("radius", "thickness", "conic", "semi_diameter") + _ASPHERE_PARAMS,
    "paraxial": ("focal_length", "thickness", "semi_diameter"),
    "coordinate_break": ("thickness",) + _CB_PARAMS,
    "component": ("thickness",),
}


class Solve(BaseModel):
    """A parameter computed from a paraxial ray.

    marginal_height / chief_height (on ``thickness``): the ray reaches
        height ``target`` (m) at the next surface; marginal_height with
        target 0 on the last surface is the paraxial image solve.
    marginal_angle / chief_angle (on ``radius``): the ray leaves the surface
        with slope ``target`` (in the direction of travel).
    f_number (on ``radius``): the marginal ray leaves with slope -1/(2N),
        N = ``target``, giving working F-number N in image space.
    """

    kind: SolveKind
    target: float = 0.0


class Pickup(BaseModel):
    """parameter = scale * (surface ``source``'s ``parameter``) + offset."""

    source: int = Field(..., ge=0, description="0-based index of the source surface")
    parameter: Optional[str] = Field(
        default=None, description="Source parameter (default: the same one)"
    )
    scale: float = 1.0
    offset: float = 0.0


class LensSurface(BaseModel):
    """One row of the lens data editor."""

    label: str = ""
    element: Optional[str] = Field(
        default=None,
        description="Lens element name; two adjacent rows with the same element form a singlet",
    )
    surface_type: SurfaceType = "standard"
    radius: float = 0.0
    conic: float = 0.0
    aspheric_coefficients: list[float] = Field(
        default_factory=list, description="A4, A6, ..."
    )
    thickness: float = 0.0
    material: Optional[str] = Field(
        default=None, description='Medium after (None = air, "MIRROR" reflects)'
    )
    semi_diameter: Optional[float] = Field(
        default=None, description="Clear semi-aperture (None = automatic)"
    )
    is_stop: bool = False
    focal_length: Optional[float] = Field(
        default=None, description="Paraxial (ideal) lens focal length"
    )
    ideal_lens_glass: str = Field(
        default="N-BK7", description="Glass giving a paraxial lens its dispersion"
    )
    decenter_x: float = 0.0
    decenter_y: float = 0.0
    decenter_z: float = 0.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    tilt_z: float = 0.0
    break_order: str = "decenter_then_tilt"
    component: Optional[dict[str, Any]] = Field(
        default=None,
        description="Engine component for surface types without a native row (surface_type 'component')",
    )
    variables: list[str] = Field(default_factory=list)
    solves: dict[str, Solve] = Field(default_factory=dict)
    pickups: dict[str, Pickup] = Field(default_factory=dict)
    semi_diameter_auto: bool = Field(
        default=False, description="Set by resolve when the semi-diameter was computed"
    )

    @model_validator(mode="after")
    def _check(self):
        allowed = PARAMETERS[self.surface_type]
        if self.surface_type == "paraxial" and self.focal_length is None:
            raise ValueError("A paraxial surface needs a focal_length")
        if self.surface_type == "component" and not self.component:
            raise ValueError("A 'component' surface needs its component data")
        if self.material is not None and self.material.lower() == "air":
            self.material = None
        for name in self.variables:
            if name not in allowed:
                raise ValueError(
                    f"'{name}' is not a parameter of a {self.surface_type} surface"
                )
        for name, solve in self.solves.items():
            if name == "thickness" and solve.kind not in THICKNESS_SOLVES:
                raise ValueError(f"A thickness solve must be one of {THICKNESS_SOLVES}")
            if name == "radius" and solve.kind not in RADIUS_SOLVES:
                raise ValueError(f"A radius solve must be one of {RADIUS_SOLVES}")
            if name not in ("thickness", "radius") or name not in allowed:
                raise ValueError(f"Solves apply to thickness or radius, not '{name}'")
            if solve.kind == "f_number" and solve.target <= 0:
                raise ValueError("An F-number solve needs a positive F-number")
        for name in self.pickups:
            if name not in allowed:
                raise ValueError(
                    f"'{name}' is not a parameter of a {self.surface_type} surface"
                )
        for name in set(self.variables) & (set(self.solves) | set(self.pickups)):
            raise ValueError(
                f"'{name}' cannot be both a variable and solved or picked up"
            )
        for name in set(self.solves) & set(self.pickups):
            raise ValueError(f"'{name}' cannot be both solved and picked up")
        return self


class LensData(BaseModel):
    """A sequential lens prescription."""

    name: str = ""
    surfaces: list[LensSurface]
    object_distance: Optional[float] = Field(
        default=None,
        description="Object to first surface (m); None = object at infinity",
    )
    object_height: float = Field(
        default=0.0, description="Object height (m) for a finite object"
    )
    field_angle: float = Field(
        default=0.0, description="Field half-angle (rad) for an object at infinity"
    )
    entrance_pupil_diameter: Optional[float] = Field(
        default=None,
        description="Aperture as an entrance pupil diameter (m); otherwise the stop's semi-diameter",
    )
    wavelengths: list[float] = Field(default_factory=lambda: [550e-9])
    wavelength_weights: Optional[list[float]] = Field(
        default=None, description="Weight of each wavelength (None = equal)"
    )
    fields: Optional[list[FieldPoint]] = Field(
        default=None, description="Field table (None = 0, 0.7, 1 of the full field)"
    )
    field_type: Optional[Literal["object_height", "angle", "paraxial_image_height"]] = (
        Field(
            default=None,
            description="object_height, angle or paraxial_image_height (None = by object distance)",
        )
    )
    first_surface_position: float = 0.0
    analysis_settings: AnalysisSettings = Field(default_factory=AnalysisSettings)

    @model_validator(mode="after")
    def _check(self):
        if not self.surfaces:
            raise ValueError("A lens needs at least one surface")
        stops = [i for i, s in enumerate(self.surfaces) if s.is_stop]
        if len(stops) != 1:
            raise ValueError("Exactly one surface must be the aperture stop")
        n = len(self.surfaces)
        for i, s in enumerate(self.surfaces):
            for name, p in s.pickups.items():
                if p.source >= n:
                    raise ValueError(
                        f"Surface {i}: pickup source {p.source} does not exist"
                    )
                src = self.surfaces[p.source]
                if (p.parameter or name) not in PARAMETERS[src.surface_type]:
                    raise ValueError(
                        f"Surface {i}: surface {p.source} has no '{p.parameter or name}'"
                    )
                if p.source == i and (p.parameter or name) == name:
                    raise ValueError(f"Surface {i}: '{name}' picks itself up")
        if (
            self.entrance_pupil_diameter is not None
            and self.entrance_pupil_diameter <= 0
        ):
            raise ValueError("The entrance pupil diameter must be positive")
        return self

    @property
    def stop_index(self) -> int:
        return next(i for i, s in enumerate(self.surfaces) if s.is_stop)


# =============================================================================
# Parameters
# =============================================================================


def get_parameter(surface: LensSurface, name: str) -> float:
    """Value of a numeric surface parameter (unset aspheric terms are 0)."""
    if name not in PARAMETERS[surface.surface_type]:
        raise ValueError(
            f"'{name}' is not a parameter of a {surface.surface_type} surface"
        )
    if name.startswith("asphere_"):
        k = _ASPHERE_ORDERS.index(int(name.split("_")[1]))
        coeffs = surface.aspheric_coefficients
        return coeffs[k] if k < len(coeffs) else 0.0
    value = getattr(surface, name)
    if value is None:
        raise ValueError(f"'{name}' is not set on surface '{surface.label}'")
    return float(value)


def _set(surface: LensSurface, name: str, value: float) -> None:
    if name.startswith("asphere_"):
        k = _ASPHERE_ORDERS.index(int(name.split("_")[1]))
        coeffs = list(surface.aspheric_coefficients)
        coeffs += [0.0] * (k + 1 - len(coeffs))
        coeffs[k] = float(value)
        surface.aspheric_coefficients = coeffs
    else:
        setattr(surface, name, float(value))
    if name == "semi_diameter":
        surface.semi_diameter_auto = False


def set_parameter(lens: LensData, index: int, name: str, value: float) -> LensData:
    """Copy of the lens with one surface parameter changed."""
    out = lens.model_copy(deep=True)
    surface = out.surfaces[index]
    if name not in PARAMETERS[surface.surface_type]:
        raise ValueError(
            f"'{name}' is not a parameter of a {surface.surface_type} surface"
        )
    _set(surface, name, value)
    return out


def variables(lens: LensData) -> list[tuple[int, str]]:
    """(surface index, parameter) of every variable, in surface order."""
    return [(i, name) for i, s in enumerate(lens.surfaces) for name in s.variables]


# =============================================================================
# Conversion to the engine's component model
# =============================================================================


def _unique(base: str, used: set) -> str:
    base = base or "S"
    name, k = base, 2
    while name in used:
        name, k = f"{base}_{k}", k + 1
    used.add(name)
    return name


def _object(lens: LensData) -> tuple[float, float]:
    """(object distance, object height) used for the engine model."""
    if lens.object_distance is None:
        return FAR_OBJECT, FAR_OBJECT * math.tan(lens.field_angle)
    return lens.object_distance, lens.object_height


def _build(
    lens: LensData, stop_semi: float, placeholder: bool
) -> tuple[OpticalSystem, dict[int, str]]:
    """
    The component model of a lens, and for each lens surface the label of
    the engine sequence surface it becomes (absent for surfaces that are not
    sequence surfaces: dummies and coordinate breaks).

    ``placeholder`` gives surfaces without a semi-diameter an aperture that
    never limits the beam (used while solving and while measuring apertures).
    """
    surfaces = lens.surfaces
    n = len(surfaces)
    zs = []
    z = lens.first_surface_position
    for s in surfaces:
        zs.append(z)
        z += s.thickness
    image_z = z
    stop = lens.stop_index

    def semi_of(i: int) -> Optional[float]:
        if i == stop:
            return stop_semi
        s = surfaces[i].semi_diameter
        if s is None and placeholder:
            return _PLACEHOLDER_SEMI
        return s

    def required_semi(i: int) -> float:
        s = semi_of(i)
        if s is None:
            raise ValueError(
                f"Surface {i} ('{surfaces[i].label}') has no semi-diameter; resolve the lens first"
            )
        return s

    comps: list = []
    labels: dict[int, str] = {}
    owner: dict[int, int] = {}  # lens surface -> index in comps of its component
    used: set = set()
    medium: Optional[str] = None
    direction = 1
    i = 0
    while i < n:
        s = surfaces[i]
        cid_base = s.label.split(".")[0] if s.label else f"S{i + 1}"
        if s.surface_type == "coordinate_break":
            comps.append(
                CoordinateBreak(
                    id=_unique(cid_base, used),
                    position=zs[i],
                    decenter_x=s.decenter_x,
                    decenter_y=s.decenter_y,
                    decenter_z=s.decenter_z,
                    tilt_x=s.tilt_x,
                    tilt_y=s.tilt_y,
                    tilt_z=s.tilt_z,
                    order=s.break_order,
                )
            )
            i += 1
            continue
        if s.surface_type == "component":
            data = dict(s.component or {})
            data["position"] = zs[i]
            data["id"] = _unique(str(data.get("id") or cid_base), used)
            comp = TypeAdapter(OpticalComponent).validate_python(data)
            if isinstance(comp, (ThickLens, Mirror, ThinLens, ApertureStop)):
                raise ValueError(
                    f"Surface {i}: use a native surface row for a {comp.type}"
                )
            owner[i] = len(comps)
            comps.append(comp)
            labels[i] = comp.id
            material = getattr(comp, "material", None)
            if material is not None:
                medium = None if str(material).lower() == "air" else material
            i += 1
            continue
        if s.surface_type == "paraxial":
            assert s.focal_length is not None
            cid = _unique(s.element or cid_base, used)
            owner[i] = len(comps)
            comps.append(
                ThinLens(
                    id=cid,
                    position=zs[i],
                    focal_length=s.focal_length,
                    aperture_diameter=2 * required_semi(i),
                    material=s.ideal_lens_glass,
                )
            )
            labels[i] = cid
            i += 1
            continue
        # standard / even_asphere
        aspheric = s.surface_type == "even_asphere" and any(s.aspheric_coefficients)
        if s.material == "MIRROR":
            if aspheric:
                raise ValueError(f"Surface {i}: aspheric mirrors are not supported yet")
            cid = _unique(cid_base, used)
            semi = required_semi(i)
            owner[i] = len(comps)
            comps.append(
                Mirror(
                    id=cid,
                    position=zs[i],
                    width=2 * semi,
                    radius=s.radius,
                    conic=s.conic,
                    aperture_diameter=2 * semi,
                )
            )
            labels[i] = f"{cid}.mirror"
            direction = -direction
            i += 1
            continue
        nxt = surfaces[i + 1] if i + 1 < n else None
        pair = (
            nxt is not None
            and s.element is not None
            and nxt.element == s.element
            and s.surface_type == "standard"
            and nxt.surface_type == "standard"
            and s.conic == 0
            and nxt.conic == 0
            and s.material is not None
            and s.material != "MIRROR"
            and nxt.material == medium
            and s.thickness * direction > 0
        )
        if pair:
            assert nxt is not None
            sa, sb = semi_of(i), semi_of(i + 1)
            user_a = (
                surfaces[i].semi_diameter is not None
                and not surfaces[i].semi_diameter_auto
            )
            user_b = nxt.semi_diameter is not None and not nxt.semi_diameter_auto
            if (
                sa is not None
                and sb is not None
                and user_a
                and user_b
                and i != stop
                and i + 1 != stop
                and abs(sa - sb) > 1e-15
            ):
                pair = False  # two different clear apertures: keep separate surfaces
        if pair:
            assert nxt is not None
            cid = _unique(s.element or cid_base, used)
            # one aperture for both surfaces: the stop's, if either is the stop
            semi = (
                stop_semi
                if stop in (i, i + 1)
                else max(required_semi(i), required_semi(i + 1))
            )
            owner[i] = owner[i + 1] = len(comps)
            comps.append(
                ThickLens(
                    id=cid,
                    position=zs[i],
                    radius1=s.radius,
                    radius2=nxt.radius,
                    thickness=abs(s.thickness),
                    aperture_diameter=2 * semi,
                    material=str(s.material),  # a pair always has glass
                )
            )
            labels[i], labels[i + 1] = f"{cid}.front", f"{cid}.back"
            i += 2
            continue
        dummy = s.radius == 0 and s.conic == 0 and not aspheric and s.material == medium
        if dummy:
            if i == stop:
                cid = _unique(cid_base, used)
                owner[i] = len(comps)
                comps.append(
                    ApertureStop(id=cid, position=zs[i], diameter=2 * stop_semi)
                )
                labels[i] = cid
            i += 1
            continue
        cid = _unique(cid_base, used)
        semi_s = semi_of(i)
        owner[i] = len(comps)
        if s.conic != 0 or aspheric:
            comps.append(
                AsphericSurface(
                    id=cid,
                    position=zs[i],
                    radius=s.radius,
                    conic=s.conic,
                    aspheric_coeffs=list(s.aspheric_coefficients),
                    aperture_diameter=2 * required_semi(i),
                    material=s.material or "air",
                )
            )
        else:
            comps.append(
                SphericalSurface(
                    id=cid,
                    position=zs[i],
                    radius=s.radius,
                    thickness=abs(s.thickness),
                    material=s.material or "air",
                    aperture_diameter=2 * semi_s if semi_s is not None else None,
                )
            )
        labels[i] = cid
        medium = s.material
        i += 1

    obj_dist, obj_height = _object(lens)
    z0 = lens.first_surface_position

    def assemble(components):
        return OpticalSystem(
            components=components,
            wavelengths=list(lens.wavelengths),
            object=Object(position=z0 - obj_dist, height=obj_height),
            fields=lens.fields,
            field_type=lens.field_type,
            wavelength_weights=lens.wavelength_weights,
            image_plane=ImagePlane(position=image_z),
            analysis_settings=lens.analysis_settings,
        )

    system = assemble(comps)
    if stop in labels and not isinstance(comps[owner[stop]], ApertureStop):
        # A stop on a powered surface: add an aperture at the surface only if
        # the engine would otherwise pick a different limiting aperture.
        seq = rt.build_sequence(system)
        if seq.surfaces[seq.stop_index].label != labels[stop]:
            k = owner[stop]
            back_of_pair = labels[stop].endswith(".back")
            ap = ApertureStop(
                id=_unique(f"{labels[stop].split('.')[0]}_stop", used),
                position=zs[stop],
                diameter=2 * stop_semi,
            )
            comps.insert(k + 1 if back_of_pair else k, ap)
            labels[stop] = ap.id
            system = assemble(comps)
    elif stop not in labels:
        raise ValueError("The stop surface does not form an aperture in the system")
    return system, labels


# =============================================================================
# Resolution: pickups, solves, automatic apertures
# =============================================================================


def _stop_semi(lens: LensData) -> float:
    stop = lens.surfaces[lens.stop_index]
    if lens.entrance_pupil_diameter is None:
        if stop.semi_diameter is None or stop.semi_diameter <= 0:
            raise ValueError(
                "Give the stop a semi-diameter or the lens an entrance pupil diameter"
            )
        return stop.semi_diameter
    # The entrance pupil scales linearly with the stop (paraxial optics).
    system, _ = _build(lens, 1.0, placeholder=True)
    fo = rt.first_order(system)
    ep = fo.entrance_pupil_semi_diameter
    if not (math.isfinite(ep) and ep > 0):
        raise ValueError(
            "The entrance pupil is not finite; specify the stop semi-diameter instead"
        )
    return 0.5 * lens.entrance_pupil_diameter / ep


def _seq_index(seq, labels: dict, i: int) -> Optional[int]:
    lab = labels.get(i)
    if lab is None:
        return None
    for k, s in enumerate(seq.surfaces):
        if s.label == lab:
            return k
    return None


def _solve(lens: LensData, i: int, param: str, solve: Solve) -> float:
    system, labels = _build(lens, _stop_semi(lens), placeholder=True)
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    ray = fo.chief if solve.kind.startswith("chief") else fo.marginal
    if param == "thickness":
        zs = np.cumsum(
            [lens.first_surface_position] + [s.thickness for s in lens.surfaces]
        )
        k = None
        for j in range(i, -1, -1):
            k = _seq_index(seq, labels, j)
            if k is not None:
                break
        if k is None:  # before the first sequence surface: object-space ray
            u = ray.u_before[0]
            y = ray.y[0] + (zs[i] - seq.surfaces[0].z) * u
        else:
            u = ray.u_after[k]
            y = ray.y[k] + (zs[i] - seq.surfaces[k].z) * u
        if abs(u) < 1e-15:
            raise ValueError(
                f"Surface {i}: the {solve.kind.split('_')[0]} ray is parallel to the axis, "
                "so no thickness reaches the target height"
            )
        return float((solve.target - y) / u)
    # radius: set the slope after the surface
    k = _seq_index(seq, labels, i)
    if k is None or seq.surfaces[k].kind not in ("refract", "reflect"):
        raise ValueError(
            f"Surface {i}: a radius solve needs a refracting or reflecting surface"
        )
    nb, na = rt.signed_indices(seq)[k]
    slope = -1.0 / (2.0 * solve.target) if solve.kind == "f_number" else solve.target
    y = ray.y[k]
    if abs(y) < 1e-15:
        raise ValueError(
            f"Surface {i}: the {solve.kind.split('_')[0]} ray height is zero there"
        )
    if na == nb:
        raise ValueError(f"Surface {i}: no index change, so the radius has no power")
    c = (ray.nu_before[k] - abs(na) * slope) / (y * (na - nb))
    return 0.0 if c == 0 else float(1.0 / c)


def _apply_pickups(lens: LensData) -> None:
    for s in lens.surfaces:
        for name, p in s.pickups.items():
            src = lens.surfaces[p.source]
            _set(s, name, p.scale * get_parameter(src, p.parameter or name) + p.offset)


def _snapshot(lens: LensData) -> list:
    out: list = []
    for s in lens.surfaces:
        for name in PARAMETERS[s.surface_type]:
            try:
                out.append(get_parameter(s, name))
            except ValueError:
                out.append(None)
    return out


def _fill_semi_diameters(lens: LensData, stop_semi: float) -> None:
    """Automatic semi-diameters from real rays (paraxial heights as fallback)."""
    stop = lens.stop_index
    lens.surfaces[stop].semi_diameter = stop_semi
    lens.surfaces[stop].semi_diameter_auto = lens.entrance_pupil_diameter is not None
    todo = [
        i
        for i, s in enumerate(lens.surfaces)
        if s.semi_diameter is None and s.surface_type != "coordinate_break"
    ]
    if not todo:
        return
    system, labels = _build(lens, stop_semi, placeholder=True)
    heights: dict[int, float] = {}
    incomplete = False  # some edge ray failed: real heights may be too small
    th = np.linspace(0.0, 2 * np.pi, 24, endpoint=False)
    ring_x = np.concatenate([[0.0], np.cos(th)])
    ring_y = np.concatenate([[0.0], np.sin(th)])
    from .fields import resolve_fields
    from .pupil import vignetted_pupil

    tracing, field_list = resolve_fields(system)
    points: list[tuple[float, float, Optional[tuple]]]
    if system.fields is None:  # also cover the -y full field
        points = [
            (0.0, ff, None)
            for ff in ([0.0, 1.0, -1.0] if system.object.height else [0.0])
        ]
    else:
        points = [(f.hx, f.hy, f.vignetting) for f in field_list]
    try:
        for wl in lens.wavelengths:
            seq = rt.build_sequence(tracing, wl)
            fo = rt.first_order(tracing, seq=seq)
            for hx, hy, vig in points:
                cx, cy, ax, ay = vignetted_pupil(vig)
                px, py = cx + ax * ring_x, cy + ay * ring_y
                b, _, _ = rt.trace_field_rays(
                    tracing, hx, hy, px, py, wavelength=wl, seq=seq, fo=fo, clip=False
                )
                incomplete |= not bool(b.valid.all())
                for i in todo:
                    k = _seq_index(seq, labels, i)
                    if k is None:
                        continue
                    pts = b.points[b.valid, k + 1]
                    if len(pts) == 0:
                        continue
                    local, _ = rt._to_local(
                        seq.surfaces[k].origin,
                        seq.surfaces[k].rotation,
                        pts,
                        np.zeros_like(pts),
                    )
                    h = float(np.max(np.hypot(local[:, 0], local[:, 1])))
                    heights[i] = max(heights.get(i, 0.0), h)
    except ValueError:
        heights, incomplete = {}, True
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    for i in todo:
        k = _seq_index(seq, labels, i)
        if k is None:
            continue  # dummy surface: no aperture needed
        h = heights.get(i, 0.0)
        if incomplete:
            # paraxial estimate (marginal + chief height) as a floor
            h = max(h, abs(fo.marginal.y[k]) + abs(fo.chief.y[k]))
        lens.surfaces[i].semi_diameter = h * (1 + 1e-9) + 1e-12
        lens.surfaces[i].semi_diameter_auto = True


def resolve(
    lens: LensData, max_passes: int = 50, fill_apertures: bool = True
) -> LensData:
    """
    A copy of the lens with pickups and solves applied (repeated, in surface
    order, until nothing changes, since a solve can depend on surfaces after
    it through the stop) and, with ``fill_apertures``, every automatic
    semi-diameter filled in.
    """
    out = lens.model_copy(deep=True)
    for s in out.surfaces:
        if s.semi_diameter_auto:
            s.semi_diameter = None  # recompute automatic apertures
    for _ in range(max_passes):
        before = _snapshot(out)
        _apply_pickups(out)
        for i, s in enumerate(out.surfaces):
            for name, solve in s.solves.items():
                _set(s, name, _solve(out, i, name, solve))
        after = _snapshot(out)
        if all(
            (a is None and b is None)
            or (
                a is not None
                and b is not None
                and abs(a - b) <= 1e-12 * max(1.0, abs(a))
            )
            for a, b in zip(before, after)
        ):
            break
    else:
        raise ValueError("Pickups and solves did not converge")
    if fill_apertures:
        _fill_semi_diameters(out, _stop_semi(out))
    return out


def _merit_system(lens: LensData) -> OpticalSystem:
    """The system traced by the optimizer: solves and pickups applied, and
    only the stop limiting the beam (clear apertures do not vignette while
    optimizing, as in Code V)."""
    resolved = resolve(lens, fill_apertures=False)
    stop_semi = _stop_semi(resolved)
    for i, s in enumerate(resolved.surfaces):
        if i != resolved.stop_index:
            s.semi_diameter = None
    system, _ = _build(resolved, stop_semi, placeholder=True)
    return system


def to_system(lens: LensData) -> OpticalSystem:
    """The engine model of a lens (resolved first)."""
    resolved = resolve(lens)
    system, _ = _build(
        resolved,
        resolved.surfaces[resolved.stop_index].semi_diameter or 0.0,
        placeholder=False,
    )
    return system


# =============================================================================
# Conversion from the component model
# =============================================================================


def _component_label(c) -> list[str]:
    if isinstance(c, ThickLens):
        return [f"{c.id}.front", f"{c.id}.back"]
    if isinstance(c, Mirror):
        return [f"{c.id}.mirror"]
    if isinstance(c, CoordinateBreak):
        return []
    return [c.id]


def from_system(system: OpticalSystem) -> LensData:
    """The surface-by-surface prescription of an existing system."""
    comps = rt.ordered_components(system)
    if not comps:
        raise ValueError("System has no components")
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    stop_label = seq.surfaces[fo.stop_index].label
    rows: list[LensSurface] = []
    zs: list[float] = []
    medium: Optional[str] = None
    direction = 1
    for c in comps:
        if isinstance(c, ThinLens):
            rows.append(
                LensSurface(
                    label=c.id,
                    element=c.id,
                    surface_type="paraxial",
                    focal_length=c.focal_length,
                    ideal_lens_glass=c.material,
                    material=medium,
                    semi_diameter=c.aperture_diameter / 2,
                )
            )
            zs.append(c.position)
        elif isinstance(c, ThickLens):
            semi = c.aperture_diameter / 2
            rows.append(
                LensSurface(
                    label=f"{c.id}.front",
                    element=c.id,
                    radius=c.radius1,
                    material=c.material,
                    semi_diameter=semi,
                )
            )
            rows.append(
                LensSurface(
                    label=f"{c.id}.back",
                    element=c.id,
                    radius=c.radius2,
                    material=medium,
                    semi_diameter=semi,
                )
            )
            zs += [c.position, c.position + direction * c.thickness]
        elif isinstance(c, AsphericSurface):
            medium = (
                None if (not c.material or c.material.lower() == "air") else c.material
            )
            rows.append(
                LensSurface(
                    label=c.id,
                    surface_type="even_asphere",
                    radius=c.radius,
                    conic=c.conic,
                    aspheric_coefficients=list(c.aspheric_coeffs),
                    material=medium,
                    semi_diameter=c.aperture_diameter / 2,
                )
            )
            zs.append(c.position)
        elif isinstance(c, SphericalSurface):
            medium = None if c.material.lower() == "air" else c.material
            rows.append(
                LensSurface(
                    label=c.id,
                    radius=c.radius,
                    material=medium,
                    semi_diameter=(
                        c.aperture_diameter / 2 if c.aperture_diameter else None
                    ),
                )
            )
            zs.append(c.position)
        elif isinstance(c, ApertureStop):
            rows.append(
                LensSurface(label=c.id, material=medium, semi_diameter=c.diameter / 2)
            )
            zs.append(c.position)
        elif isinstance(c, Mirror):
            rows.append(
                LensSurface(
                    label=c.id,
                    radius=c.radius,
                    conic=c.conic,
                    material="MIRROR",
                    semi_diameter=(c.aperture_diameter or c.width) / 2,
                )
            )
            zs.append(c.position)
            direction = -direction
        elif isinstance(c, CoordinateBreak):
            rows.append(
                LensSurface(
                    label=c.id,
                    surface_type="coordinate_break",
                    decenter_x=c.decenter_x,
                    decenter_y=c.decenter_y,
                    decenter_z=c.decenter_z,
                    tilt_x=c.tilt_x,
                    tilt_y=c.tilt_y,
                    tilt_z=c.tilt_z,
                    break_order=c.order,
                )
            )
            zs.append(c.position)
        else:
            data = c.model_dump(exclude={"position"})
            rows.append(
                LensSurface(label=c.id, surface_type="component", component=data)
            )
            zs.append(c.position)
            material = getattr(c, "material", None)
            if material is not None:
                medium = None if str(material).lower() == "air" else material
    for k in range(len(rows) - 1):
        rows[k].thickness = zs[k + 1] - zs[k]
    rows[-1].thickness = system.image_plane.position - zs[-1]
    # mark the stop the engine uses
    k = 0
    stop_row = None
    for c in comps:
        for lab in _component_label(c):
            if lab == stop_label:
                stop_row = k
            k += 1
        if isinstance(c, CoordinateBreak):
            k += 1
    if stop_row is None:
        raise ValueError(f"Stop surface '{stop_label}' not found")
    rows[stop_row].is_stop = True
    # a stop on a lens surface is limited by that element's own aperture
    obj_dist = zs[0] - system.object.position
    infinite = seq.object_infinite
    return LensData(
        surfaces=rows,
        object_distance=obj_dist,
        object_height=system.object.height,
        field_angle=math.atan2(system.object.height, obj_dist) if infinite else 0.0,
        wavelengths=list(system.wavelengths),
        wavelength_weights=system.wavelength_weights,
        fields=system.fields,
        field_type=system.field_type,
        first_surface_position=zs[0],
        analysis_settings=system.analysis_settings,
    )


# =============================================================================
# Optimization over flagged variables
# =============================================================================


def optimize(
    lens: LensData,
    merit: Optional[Callable[[OpticalSystem], np.ndarray]] = None,
    bounds: Optional[dict[str, tuple[float, float]]] = None,
    max_evaluations: int = 300,
) -> dict:
    """
    Damped least squares over the lens's variables (scipy's trust-region
    reflective least squares), with solves and pickups re-applied at every
    step, as in Code V. Only the stop limits the beam during optimization;
    the clear apertures you set are kept in the result.

    Args:
        merit: residual vector of a system (default: transverse ray errors
            over fields 0, 0.7, 1 and all wavelengths, whose sum of squares
            is the mean-square spot radius in m^2).
        bounds: optional ``{"<surface>.<parameter>": (low, high)}``.
    """
    from scipy.optimize import least_squares

    from .advanced_optimization import ray_aberration_residuals

    var = variables(lens)
    if not var:
        raise ValueError("No surface parameter is flagged as a variable")
    if merit is None:

        def merit(system: OpticalSystem) -> np.ndarray:
            return ray_aberration_residuals(
                system, wavelengths=list(system.wavelengths), vignetting=False
            )

    bounds = bounds or {}
    keys = [f"{i}.{name}" for i, name in var]
    for key in bounds:
        if key not in keys:
            raise ValueError(f"Bound '{key}' is not a variable (variables: {keys})")
    lo = np.array([bounds.get(k, (-np.inf, np.inf))[0] for k in keys], dtype=float)
    hi = np.array([bounds.get(k, (-np.inf, np.inf))[1] for k in keys], dtype=float)
    x0 = np.array([get_parameter(lens.surfaces[i], name) for i, name in var])
    if np.any(x0 < lo) or np.any(x0 > hi):
        raise ValueError("The starting values must lie within the bounds")

    def apply(x) -> LensData:
        out = lens.model_copy(deep=True)
        for (i, name), v in zip(var, x):
            _set(out.surfaces[i], name, v)
        return out

    r0 = np.asarray(merit(_merit_system(lens)), dtype=float)
    # Work with residuals normalised by the starting RMS so the solver's
    # stopping tolerances mean the same at any scale (residuals in meters
    # are ~1e-5 and their gradients would fall below gtol at once).
    norm0 = float(np.sqrt(np.sum(r0**2))) or 1.0
    penalty = 10.0 * max(float(np.max(np.abs(r0))) / norm0 if r0.size else 1.0, 1.0)
    evaluations = [0]

    def residual(x):
        evaluations[0] += 1
        try:
            r = np.asarray(merit(_merit_system(apply(x))), dtype=float)
            if r.shape != r0.shape or not np.all(np.isfinite(r)):
                raise ValueError("invalid merit")
            return r / norm0
        except (ValueError, ZeroDivisionError, FloatingPointError):
            return np.full(r0.shape, penalty)

    scale = np.where(x0 != 0, np.abs(x0), 1e-3)
    res = least_squares(
        residual,
        x0,
        bounds=(lo, hi),
        method="trf",
        x_scale=scale,
        max_nfev=max_evaluations,
        diff_step=1e-6,
    )
    best = resolve(apply(res.x))
    return {
        "lens": best,
        "system": to_system(best),
        "variables": {k: float(v) for k, v in zip(keys, res.x)},
        "merit_before": float(np.sum(r0**2)),
        "merit_after": float(np.sum(res.fun**2)) * norm0**2,
        "evaluations": evaluations[0],
        "success": bool(res.success),
        "message": str(res.message),
    }
