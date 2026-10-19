"""
Fast tolerancing of a lens prescription (in the manner of Code V's TOR).

Tolerances are named as in Code V:

- DLF radius error in fringes of power at ``test_wavelength`` over
  ``test_diameter`` (default: the surface's clear aperture): the conic sag
  at D/2 changes by exactly N lambda / 2 (paraxially dc = 4 N lambda / D^2);
- DLR radius error (m); DLT thickness after the surface (m);
- DLN, DLV index and Abbe-number errors of the glass after the surface
  (the catalog dispersion is kept, see ``materials.perturbed_glass_name``);
- DSX, DSY surface decenter (m); TRX, TRY surface tilt (rad);
- DLX, DLY element decenter (m); BTX, BTY element tilt (rad) about the
  element's first vertex, for the surfaces ``surface`` .. ``last_surface``.

Decenters and tilts are applied with a coordinate break before the surfaces
and an exact inverse after them, so everything after is on the original
axis. Before tolerancing, solves and pickups are frozen at their values:
each surface is made independently, and only compensators move. The
compensators are the back focus (the thickness to the image) and any other
thicknesses.

Performance is the RMS wavefront error in waves, piston and tilt removed,
over the field table and wavelengths (their weights) on a Gaussian pupil
quadrature; only the stop limits the beam. The composite is
sqrt(sum_f w_f RMS_f^2) with the field weights normalised.

The fast analysis traces each tolerance at +limit and -limit and the
compensators by central differences, which gives a model of the wavefront
residual vector r: r(d, z) = r0 + sum_k (a_k d_k + b_k d_k^2) + G z,
quadratic in each tolerance (cross terms between tolerances neglected) and
linear in the compensators. Compensators are set by least squares within
their limits. The sensitivity table uses the traced wavefronts at the
limits; the statistics come from Monte Carlo on the model, which needs no
further tracing. :func:`monte_carlo` is the reference: it perturbs, traces
and re-optimizes the compensators exactly for every trial.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

import numpy as np
from pydantic import BaseModel, Field, model_validator

from . import raytrace as rt
from .fields import pupil_samples, resolve_fields, wavelength_weights
from .lens_data import LensData, LensSurface, _merit_system, resolve
from .materials import parse_perturbed_glass, perturbed_glass_name

ToleranceKind = Literal[
    "DLF",
    "DLR",
    "DLT",
    "DLN",
    "DLV",
    "DSX",
    "DSY",
    "TRX",
    "TRY",
    "DLX",
    "DLY",
    "BTX",
    "BTY",
]
#: Tolerances that move a group of surfaces (an element).
ELEMENT_KINDS = ("DLX", "DLY", "BTX", "BTY")
#: Tolerances applied with coordinate breaks: kind -> (break field, sign).
_MISALIGN = {
    "DSX": "decenter_x",
    "DSY": "decenter_y",
    "TRX": "tilt_x",
    "TRY": "tilt_y",
    "DLX": "decenter_x",
    "DLY": "decenter_y",
    "BTX": "tilt_x",
    "BTY": "tilt_y",
}
#: Percentiles reported (Code V's cumulative probability levels: 50 %, and
#: the mean + 1, 2 and 3 sigma levels of a normal distribution).
PERCENTILES = (50.0, 84.13, 97.72, 99.87)


class Tolerance(BaseModel):
    """One tolerance: the parameter may be in error by up to +-``limit``."""

    kind: ToleranceKind
    surface: int = Field(..., ge=0)
    last_surface: Optional[int] = Field(
        default=None, description="Element tolerances: last surface of the element"
    )
    limit: float = Field(..., gt=0)
    distribution: Literal["uniform", "gaussian", "end_point"] = Field(
        default="uniform",
        description="uniform in +-limit; gaussian with sigma = limit/2, truncated "
        "at the limit; end_point at +-limit",
    )
    test_wavelength: float = Field(default=546.07e-9, description="DLF only")
    test_diameter: Optional[float] = Field(
        default=None, description="DLF only (default: the clear aperture)"
    )

    @model_validator(mode="after")
    def _check(self):
        if self.kind in ELEMENT_KINDS:
            if self.last_surface is None:
                self.last_surface = self.surface + 1
            if self.last_surface < self.surface:
                raise ValueError("last_surface precedes surface")
        elif self.last_surface is not None:
            raise ValueError(f"{self.kind} applies to one surface (no last_surface)")
        return self

    @property
    def label(self) -> str:
        if self.kind in ELEMENT_KINDS:
            return f"{self.kind} S{self.surface}..S{self.last_surface}"
        return f"{self.kind} S{self.surface}"


class Compensator(BaseModel):
    """An adjustment made after assembly: a thickness (back focus = the
    thickness to the image), moved by at most +-``limit`` (None = free)."""

    kind: Literal["back_focus", "thickness"] = "back_focus"
    surface: Optional[int] = None
    limit: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check(self):
        if (self.kind == "thickness") != (self.surface is not None):
            raise ValueError(
                "A thickness compensator needs a surface (back_focus none)"
            )
        return self


# =============================================================================
# Perturbing a lens
# =============================================================================


def freeze(lens: LensData) -> LensData:
    """The lens with solves and pickups replaced by their values (and no
    variables or constraints)."""
    out = resolve(lens, fill_apertures=False)
    for s in out.surfaces:
        s.solves = {}
        s.pickups = {}
        s.variables = []
    out.constraints = []
    return LensData.model_validate(out.model_dump())


def _compensator_surface(lens: LensData, c: Compensator) -> int:
    if c.kind == "back_focus" or c.surface is None:
        return len(lens.surfaces) - 1
    return c.surface


def _check(lens: LensData, t: Tolerance) -> None:
    n = len(lens.surfaces)
    last = t.last_surface if t.last_surface is not None else t.surface
    if last >= n:
        raise ValueError(f"{t.label}: the lens has {n} surfaces")
    s = lens.surfaces[t.surface]
    if t.kind in ("DLF", "DLR") and s.surface_type not in ("standard", "even_asphere"):
        raise ValueError(f"{t.label}: not a refracting or reflecting surface")
    if t.kind in ("DLN", "DLV") and (s.material is None or s.material == "MIRROR"):
        raise ValueError(f"{t.label}: no glass after surface {t.surface}")
    if t.kind in ELEMENT_KINDS and any(
        lens.surfaces[k].material == "MIRROR" for k in range(t.surface, last + 1)
    ):
        raise ValueError(f"{t.label}: element tolerances do not span mirrors")


def _conic_sag(radius: float, conic: float, h: float) -> float:
    if not radius:
        return 0.0
    c = 1.0 / radius
    arg = 1.0 - (1.0 + conic) * c * c * h * h
    if arg < 0:
        raise ValueError("The test diameter exceeds the conic's extent")
    return c * h * h / (1.0 + math.sqrt(arg))


def _radius_for_sag(z: float, conic: float, h: float) -> float:
    """Radius of the conic with sag z at height h (0 = flat): from
    h^2 - 2 R z + (1 + k) z^2 = 0."""
    return (h * h + (1.0 + conic) * z * z) / (2.0 * z) if z else 0.0


def _direction(thickness: float) -> float:
    """+1, or -1 for a thickness measured backwards (after a mirror): a
    positive error lengthens the gap either way."""
    return -1.0 if thickness < 0 else 1.0


def _break(**kw) -> LensSurface:
    return LensSurface(label="tol", surface_type="coordinate_break", **kw)


def apply(
    lens: LensData,
    tolerances: list[tuple[Tolerance, float]],
    compensators: Sequence[tuple[Compensator, float]] = (),
    apertures: Optional[list[Optional[float]]] = None,
) -> LensData:
    """
    The (frozen) lens with each tolerance set to its value and each
    compensator moved. ``apertures`` are the clear semi-diameters used by
    DLF when no test diameter is given.
    """
    rows = [s.model_copy(deep=True) for s in lens.surfaces]
    groups: dict[tuple[int, int], dict] = {}
    for t, v in tolerances:
        _check(lens, t)
        s = rows[t.surface]
        if t.kind == "DLF":
            semi = (
                t.test_diameter / 2
                if t.test_diameter
                else (apertures[t.surface] if apertures else s.semi_diameter)
            )
            if not semi:
                raise ValueError(f"{t.label}: needs a test diameter")
            s.radius = _radius_for_sag(
                _conic_sag(s.radius, s.conic, semi) + v * t.test_wavelength / 2,
                s.conic,
                semi,
            )
        elif t.kind == "DLR":
            if not s.radius:
                raise ValueError(f"{t.label}: a flat surface has no radius error")
            s.radius += v
        elif t.kind == "DLT":
            s.thickness += v * _direction(s.thickness)
        elif t.kind in ("DLN", "DLV"):
            base, dn, dvd = parse_perturbed_glass(s.material or "") or (
                s.material,
                0,
                0,
            )
            if t.kind == "DLN":
                dn += v
            else:
                dvd += v
            s.material = perturbed_glass_name(str(base), dn, dvd)
        else:
            last = t.last_surface if t.last_surface is not None else t.surface
            g = groups.setdefault((t.surface, last), {})
            key = _MISALIGN[t.kind]
            g[key] = g.get(key, 0.0) + v
    for c, v in compensators:
        s = rows[_compensator_surface(lens, c)]
        s.thickness += v * _direction(s.thickness)
    # coordinate breaks, innermost span first so nested breaks wrap correctly
    start = {i: rows[i] for i in range(len(rows))}
    end = dict(start)
    for (i, j), g in sorted(groups.items(), key=lambda kv: kv[0][1] - kv[0][0]):
        dx, dy = g.get("decenter_x", 0.0), g.get("decenter_y", 0.0)
        tx, ty = g.get("tilt_x", 0.0), g.get("tilt_y", 0.0)
        p_in = next(k for k, r in enumerate(rows) if r is start[i])
        cb_in = _break(decenter_x=dx, decenter_y=dy, tilt_x=tx, tilt_y=ty)
        rows.insert(p_in, cb_in)
        start[i] = cb_in
        p_end = next(k for k, r in enumerate(rows) if r is end[j])
        L = sum(r.thickness for r in rows[p_in:p_end])
        # exact inverse: the engine composes R_new = R Rz Ry Rx, so undo
        # Ry Rx with Rx(-tx) then Ry(-ty), and put the origin back on the
        # original axis at the last vertex
        R1 = rt._rotation(tx, ty, 0.0)
        p_end_frame = np.array([dx, dy, 0.0]) + R1 @ np.array([0.0, 0.0, L])
        dec = R1.T @ (np.array([0.0, 0.0, L]) - p_end_frame)
        gap = rows[p_end].thickness
        rows[p_end].thickness = 0.0
        out1 = _break(
            decenter_x=float(dec[0]),
            decenter_y=float(dec[1]),
            decenter_z=float(dec[2]),
            tilt_x=-tx,
        )
        out2 = _break(tilt_y=-ty, thickness=gap)
        rows[p_end + 1 : p_end + 1] = [out1, out2]
        end[j] = out2
    return lens.model_copy(update={"surfaces": rows})


# =============================================================================
# Wavefront performance
# =============================================================================


@dataclass
class _Probe:
    """Fields, wavelengths and pupil samples fixed for a tolerancing run."""

    tracing_object: object
    fields: list  # (hx, hy, weight, px, py, w)
    wavelengths: list  # (wavelength, weight)
    field_slices: list = field(default_factory=list)


def _probe(lens: LensData, rings: int) -> _Probe:
    system = _merit_system(lens)
    tracing, fields = resolve_fields(system)
    total = sum(f.weight for f in fields) or 1.0
    fl = []
    for f in fields:
        px, py, w = pupil_samples(rings, f.vignetting)
        fl.append((f.hx, f.hy, f.weight / total, px[1:], py[1:], w[1:]))
    wl = list(zip(system.wavelengths, wavelength_weights(system)))
    return _Probe(tracing.object, fl, wl)


def residuals(lens: LensData, probe: _Probe) -> np.ndarray:
    """Weighted wavefront residual vector (waves): sum of squares is the
    composite mean-square wavefront error. Raises ValueError when rays fail."""
    system = _merit_system(lens).model_copy(update={"object": probe.tracing_object})
    blocks = []
    for wl, ww in probe.wavelengths:
        seq = rt.build_sequence(system, wl)
        fo = rt.first_order(system, seq=seq)
        for hx, hy, wf, px, py, w in probe.fields:
            W, ok, _ = rt.opd(system, hx, hy, px, py, wl, seq=seq, fo=fo)
            if not np.all(ok):
                raise ValueError("Rays fail in the perturbed system")
            # remove piston and tilt (weighted least squares)
            A = np.stack([np.ones_like(px), px, py], axis=1)
            sw = np.sqrt(w)
            coef = np.linalg.lstsq(A * sw[:, None], W * sw, rcond=None)[0]
            blocks.append(np.sqrt(wf * ww) * sw * (W - A @ coef) / wl)
    return np.concatenate(blocks)


def _field_index(probe: _Probe) -> np.ndarray:
    """Field number of each residual component."""
    idx = []
    for _ in probe.wavelengths:
        for k, (_, _, _, px, _, _) in enumerate(probe.fields):
            idx.append(np.full(px.size, k))
    return np.concatenate(idx)


def _rms_per_field(R: np.ndarray, fidx: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """(..., n_fields) RMS of each field from residual rows R (..., m)."""
    out = []
    for k, wf in enumerate(weights):
        sel = fidx == k
        out.append(np.sqrt(np.sum(R[..., sel] ** 2, axis=-1) / wf))
    return np.stack(out, axis=-1)


# =============================================================================
# Fast analysis
# =============================================================================


def _draw(t: Tolerance, rng: np.random.Generator, n: int) -> np.ndarray:
    L = t.limit
    if t.distribution == "uniform":
        return rng.uniform(-L, L, n)
    if t.distribution == "end_point":
        return L * rng.choice([-1.0, 1.0], n)
    out = rng.normal(0.0, L / 2, n)
    bad = np.abs(out) > L
    while bad.any():
        out[bad] = rng.normal(0.0, L / 2, bad.sum())
        bad = np.abs(out) > L
    return out


def _compensate(R, G, limits):
    """Rows of R compensated by least squares over G's columns within
    limits; returns (compensated rows, compensator values)."""
    if G.shape[1] == 0:
        return R, np.zeros((R.shape[0], 0))
    pinv = np.linalg.pinv(G)
    Z = -(R @ pinv.T)
    lim = np.array([np.inf if v is None else v for v in limits])
    over = np.any(np.abs(Z) > lim, axis=1)
    if over.any():
        from scipy.optimize import lsq_linear

        for i in np.flatnonzero(over):
            Z[i] = lsq_linear(G, -R[i], bounds=(-lim, lim)).x
    return R + Z @ G.T, Z


@dataclass
class ToleranceAnalysis:
    nominal_rms: float  # waves, composite
    nominal_field_rms: list
    sensitivities: list  # dicts per tolerance
    rss_increase: float  # sqrt(sum of the larger |change| at the limits squared)
    predicted: dict  # mean, std, percentiles, cumulative curve (composite)
    predicted_fields: list  # percentiles per field
    compensators: list  # adjustment statistics
    trials: int
    # model, for inverse sensitivity
    _r0: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))
    _A: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))
    _B: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))
    _G: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))
    _limits: list = field(repr=False, default_factory=list)
    _tolerances: list = field(repr=False, default_factory=list)

    def to_dict(self) -> dict:
        """The report without the fitted model arrays (units: waves)."""
        return {
            "units": "waves",
            "nominal_rms": self.nominal_rms,
            "nominal_field_rms": self.nominal_field_rms,
            "sensitivities": self.sensitivities,
            "rss_increase": self.rss_increase,
            "predicted": self.predicted,
            "predicted_fields": self.predicted_fields,
            "compensators": self.compensators,
            "trials": self.trials,
        }


def analyze(
    lens: LensData,
    tolerances: list[Tolerance],
    compensators: Optional[list[Compensator]] = None,
    trials: int = 20000,
    rings: int = 6,
    seed: Optional[int] = 0,
    compensator_step: float = 1e-5,
) -> ToleranceAnalysis:
    """Sensitivity table and predicted performance distribution."""
    compensators = list(compensators if compensators is not None else [Compensator()])
    nominal = freeze(lens)
    apertures = [s.semi_diameter for s in resolve(lens).surfaces]
    probe = _probe(nominal, rings)
    fidx = _field_index(probe)
    fw = np.array([f[2] for f in probe.fields])
    r0 = residuals(nominal, probe)
    m = r0.size
    G = np.zeros((m, len(compensators)))
    for k, c in enumerate(compensators):
        rp = residuals(apply(nominal, [], [(c, compensator_step)]), probe)
        rm = residuals(apply(nominal, [], [(c, -compensator_step)]), probe)
        G[:, k] = (rp - rm) / (2 * compensator_step)
    limits = [c.limit for c in compensators]
    A = np.zeros((len(tolerances), m))
    B = np.zeros((len(tolerances), m))
    traced = []
    for k, t in enumerate(tolerances):
        rp = residuals(apply(nominal, [(t, t.limit)], apertures=apertures), probe)
        rm = residuals(apply(nominal, [(t, -t.limit)], apertures=apertures), probe)
        A[k] = (rp - rm) / (2 * t.limit)
        B[k] = (rp + rm - 2 * r0) / (2 * t.limit**2)
        traced.append((rp, rm))
    (r0c,), _ = _compensate(r0[None, :], G, limits)
    base = float(np.linalg.norm(r0c))
    rows = []
    for t, (rp, rm) in zip(tolerances, traced):
        comp, Z = _compensate(np.stack([rp, rm]), G, limits)
        plus, minus = (float(np.linalg.norm(v)) for v in comp)
        rows.append(
            {
                "tolerance": t.label,
                "kind": t.kind,
                "surface": t.surface,
                "last_surface": t.last_surface,
                "limit": t.limit,
                "rms_plus": plus,
                "rms_minus": minus,
                "change_plus": plus - base,
                "change_minus": minus - base,
                "compensation_plus": Z[0].tolist(),
                "compensation_minus": Z[1].tolist(),
            }
        )
    rss = math.sqrt(
        sum(max(abs(r["change_plus"]), abs(r["change_minus"])) ** 2 for r in rows)
    )
    # Monte Carlo on the model
    rng = np.random.default_rng(seed)
    D = (
        np.stack([_draw(t, rng, trials) for t in tolerances], axis=1)
        if tolerances
        else np.zeros((trials, 0))
    )
    R = r0 + D @ A + (D * D) @ B
    Rc, Z = _compensate(R, G, limits)
    rms = np.linalg.norm(Rc, axis=1)
    per_field = _rms_per_field(Rc, fidx, fw)
    probs = np.linspace(0.0, 1.0, 51)
    predicted = {
        "mean": float(rms.mean()),
        "std": float(rms.std()),
        "percentiles": {str(p): float(np.percentile(rms, p)) for p in PERCENTILES},
        "cumulative": {
            "probability": probs.tolist(),
            "rms": np.quantile(rms, probs).tolist(),
        },
    }
    return ToleranceAnalysis(
        nominal_rms=base,
        nominal_field_rms=_rms_per_field(r0c[None, :], fidx, fw)[0].tolist(),
        sensitivities=rows,
        rss_increase=rss,
        predicted=predicted,
        predicted_fields=[
            {str(p): float(np.percentile(per_field[:, k], p)) for p in PERCENTILES}
            for k in range(fw.size)
        ],
        compensators=[
            {
                "compensator": (
                    c.kind if c.surface is None else f"thickness S{c.surface}"
                ),
                "mean": float(Z[:, k].mean()),
                "std": float(Z[:, k].std()),
                "max_abs": float(np.max(np.abs(Z[:, k]))),
            }
            for k, c in enumerate(compensators)
        ],
        trials=trials,
        _r0=r0,
        _A=A,
        _B=B,
        _G=G,
        _limits=limits,
        _tolerances=list(tolerances),
    )


def inverse_limits(analysis: ToleranceAnalysis, total_increase: float) -> list[dict]:
    """
    Inverse sensitivity: the limit for each tolerance at which it alone
    raises the composite RMS by total_increase / sqrt(K) (an equal share of
    an RSS budget over K tolerances), from the fitted model. Limits far
    beyond those analysed are extrapolations of the model.
    """
    from scipy.optimize import brentq

    K = len(analysis._tolerances)
    share = total_increase / math.sqrt(max(K, 1))
    (r0c,), _ = _compensate(analysis._r0[None, :], analysis._G, analysis._limits)
    base = float(np.linalg.norm(r0c))

    def change(k, d):
        r = analysis._r0 + analysis._A[k] * d + analysis._B[k] * d * d
        (rc,), _ = _compensate(r[None, :], analysis._G, analysis._limits)
        return float(np.linalg.norm(rc)) - base

    out = []
    for k, t in enumerate(analysis._tolerances):

        def worst(d):
            return max(change(k, d), change(k, -d)) - share

        hi = t.limit
        while worst(hi) < 0 and hi < 1e3 * t.limit:
            hi *= 2
        lim = brentq(worst, 1e-12 * t.limit, hi) if worst(hi) >= 0 else math.inf
        out.append(
            {
                "tolerance": t.label,
                "limit": lim,
                "analysed_limit": t.limit,
                "extrapolated": bool(lim > t.limit * 1.5),
            }
        )
    return out


# =============================================================================
# Reference Monte Carlo
# =============================================================================


def monte_carlo(
    lens: LensData,
    tolerances: list[Tolerance],
    compensators: Optional[list[Compensator]] = None,
    trials: int = 100,
    rings: int = 6,
    seed: Optional[int] = 0,
) -> dict:
    """Exact Monte Carlo: each trial is perturbed, traced, and its
    compensators re-optimized on the traced RMS."""
    from scipy.optimize import minimize, minimize_scalar

    compensators = list(compensators if compensators is not None else [Compensator()])
    nominal = freeze(lens)
    apertures = [s.semi_diameter for s in resolve(lens).surfaces]
    probe = _probe(nominal, rings)
    rng = np.random.default_rng(seed)
    D = np.stack([_draw(t, rng, trials) for t in tolerances], axis=1)
    values, failed, adjust = [], 0, []
    for d in D:
        pert = list(zip(tolerances, d))

        def rms(z):
            try:
                r = residuals(
                    apply(
                        nominal, pert, list(zip(compensators, z)), apertures=apertures
                    ),
                    probe,
                )
            except ValueError:
                return math.inf
            return float(np.linalg.norm(r))

        bounds = [(-(c.limit or 1e-2), c.limit or 1e-2) for c in compensators]
        if len(compensators) == 1:
            res = minimize_scalar(
                lambda z: rms([z]),
                bounds=bounds[0],
                method="bounded",
                options={"xatol": 1e-9},
            )
            z, v = [res.x], res.fun
        elif compensators:
            res = minimize(
                rms, np.zeros(len(compensators)), bounds=bounds, method="L-BFGS-B"
            )
            z, v = list(res.x), res.fun
        else:
            z, v = [], rms([])
        if not math.isfinite(v):
            failed += 1
            continue
        values.append(v)
        adjust.append(z)
    arr = np.array(values)
    return {
        "trials": len(values),
        "failed_trials": failed,
        "rms": values,
        "mean": float(arr.mean()) if arr.size else math.nan,
        "std": float(arr.std()) if arr.size else math.nan,
        "percentiles": (
            {str(p): float(np.percentile(arr, p)) for p in PERCENTILES}
            if arr.size
            else {}
        ),
        "compensation": adjust,
    }


# =============================================================================
# Starting tolerance set
# =============================================================================


def elements(lens: LensData) -> list[tuple[int, int]]:
    """(first, last surface) of each glass element: from a surface entering
    glass from air to the surface leaving it (cemented groups are one)."""
    out, start = [], None
    medium = None
    for i, s in enumerate(lens.surfaces):
        if s.surface_type == "coordinate_break" or s.material == "MIRROR":
            continue
        if medium is None and s.material is not None and start is None:
            start = i
        if start is not None and s.material is None:
            out.append((start, i))
            start = None
        medium = s.material
    return out


def default_tolerances(
    lens: LensData,
    fringes: float = 3.0,
    thickness: float = 0.05e-3,
    index: float = 0.0005,
    abbe_fraction: float = 0.005,
    element_decenter: float = 0.025e-3,
    element_tilt: float = math.radians(1 / 60),
    surface_tilt: float = math.radians(1 / 60),
) -> list[Tolerance]:
    """
    A starting tolerance set for every element. The default values are
    editable starting points of the kind used for commercial-precision
    optics, not a standard: set them from the fabricator's capabilities.
    """
    from .materials import abbe_number

    out: list[Tolerance] = []
    for first, last in elements(lens):
        for i in range(first, last + 1):
            s = lens.surfaces[i]
            if s.radius:
                out.append(Tolerance(kind="DLF", surface=i, limit=fringes))
            if i < last:
                out.append(Tolerance(kind="DLT", surface=i, limit=thickness))
                out.append(Tolerance(kind="DLN", surface=i, limit=index))
                vd = abbe_number(s.material) if s.material else None
                if vd:
                    out.append(
                        Tolerance(kind="DLV", surface=i, limit=abbe_fraction * vd)
                    )
            if i > first:
                out.append(Tolerance(kind="TRX", surface=i, limit=surface_tilt))
                out.append(Tolerance(kind="TRY", surface=i, limit=surface_tilt))
        misalign: tuple[tuple[ToleranceKind, float], ...] = (
            ("DLX", element_decenter),
            ("DLY", element_decenter),
            ("BTX", element_tilt),
            ("BTY", element_tilt),
        )
        for kind, lim in misalign:
            out.append(
                Tolerance(kind=kind, surface=first, last_surface=last, limit=lim)
            )
    return out
