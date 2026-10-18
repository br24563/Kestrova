"""
Tolerance analysis.

Monte Carlo, sensitivity (tornado) and compensated analyses of how
manufacturing and alignment errors change a performance metric.

Parameters are named "<component id>.<field>" (for example "L1.position",
"L1.radius1", "L1.thickness"), "image_plane.position" or
"object.position". Each trial adds a random error to the parameter's
*nominal* value. Element decenters and tilts are applied as
"<id>.decenter_x", "<id>.decenter_y" (meters), "<id>.tilt_x", "<id>.tilt_y"
(radians): the element is moved by a pair of coordinate breaks placed
around it, and the real 3D ray trace sees the misalignment.

The default metric is the real-ray RMS spot radius at the image plane.
All values are in SI base units (meters, radians).
"""

import math
import random
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np
from scipy.optimize import minimize_scalar

from .models import OpticalSystem, ImagePlane, Object, ThickLens, ThinLens
from .advanced_surfaces import CoordinateBreak
from .analysis import analyze_system

_DEFAULT_TRIALS = 100
_DEFAULT_TOLERANCE = 1.0e-4  # 0.1 mm (1 sigma) on element positions


@dataclass
class ToleranceSpec:
    """Specification for a single tolerance parameter."""
    name: str                     # e.g. "L1.radius1"
    nominal: float
    distribution: str = "gaussian"   # "gaussian", "uniform", "truncated_gaussian"
    sigma: float = 0.0
    lower: float = 0.0               # bounds of the error for "uniform"
    upper: float = 0.0
    correlation_group: Optional[str] = None


@dataclass
class Compensator:
    """
    An adjustment made after assembly to recover performance.

    ``parameter`` is a parameter name as above (e.g. "image_plane.position");
    the compensator may move it by an offset in [min_value, max_value] from
    its value in the perturbed system.
    """
    name: str
    parameter: str
    min_value: float
    max_value: float
    current_value: float = 0.0


@dataclass
class ManufacturingErrors:
    """
    Typical fabrication and assembly errors (1 sigma) used by
    :func:`manufacturing_tolerances`.

    radius_error_fringes: power error in fringes at test_wavelength over the
        clear aperture; converted to a radius error |dR| = 4 N lambda R^2 / D^2.
    """
    radius_error_fringes: float = 1.0
    test_wavelength: float = 546.1e-9
    thickness_error_mm: float = 0.05
    decenter_um: float = 5.0
    tilt_arcmin: float = 1.0
    spacing_error_mm: float = 0.05


def manufacturing_tolerances(system: OpticalSystem,
                             errors: Optional[ManufacturingErrors] = None) -> dict:
    """Build a tolerance dict (parameter -> 1-sigma error) for every lens."""
    e = errors or ManufacturingErrors()
    tol: dict[str, float] = {}
    for c in system.components:
        if isinstance(c, (ThickLens, ThinLens)):
            tol[f"{c.id}.position"] = e.spacing_error_mm * 1e-3
            tol[f"{c.id}.decenter_y"] = e.decenter_um * 1e-6
            tol[f"{c.id}.tilt_x"] = math.radians(e.tilt_arcmin / 60.0)
        if isinstance(c, ThickLens):
            tol[f"{c.id}.thickness"] = e.thickness_error_mm * 1e-3
            D = c.aperture_diameter
            for field in ("radius1", "radius2"):
                R = getattr(c, field)
                if R and math.isfinite(R) and abs(R) < 1e9:
                    tol[f"{c.id}.{field}"] = 4.0 * e.radius_error_fringes * e.test_wavelength * R * R / (D * D)
    return tol


def _draw_from_distribution(spec: ToleranceSpec, rng: random.Random) -> float:
    """Random error from the specified distribution."""
    if spec.distribution == "uniform":
        return rng.uniform(spec.lower, spec.upper)
    if spec.distribution == "truncated_gaussian":
        # Gaussian truncated at +-3 sigma (rejection sampling).
        if spec.sigma <= 0:
            return 0.0
        while True:
            v = rng.gauss(0.0, spec.sigma)
            if abs(v) <= 3.0 * spec.sigma:
                return v
    if spec.distribution != "gaussian":
        raise ValueError(f"Unknown distribution '{spec.distribution}'")
    return rng.gauss(0.0, spec.sigma)


_MISALIGN = ("decenter_x", "decenter_y", "tilt_x", "tilt_y")


def get_parameter(system: OpticalSystem, name: str) -> float:
    """Current value of a named parameter (misalignments are 0 nominally)."""
    target, field = name.split(".", 1)
    if target == "image_plane":
        return float(getattr(system.image_plane, field))
    if target == "object":
        return float(getattr(system.object, field))
    comp = next((c for c in system.components if c.id == target), None)
    if comp is None:
        raise ValueError(f"No component '{target}'")
    if field in _MISALIGN:
        return 0.0
    if not hasattr(comp, field):
        raise ValueError(f"Component '{target}' has no field '{field}'")
    return float(getattr(comp, field))


def _misalign(system: OpticalSystem, comp_id: str, field: str, value: float) -> OpticalSystem:
    """Decenter or tilt one element about its front vertex, then restore the
    original axis exactly after its last surface."""
    from .raytrace import _rotation
    comps = list(system.components)
    i = next(k for k, c in enumerate(comps) if c.id == comp_id)
    c = comps[i]
    L = c.thickness if isinstance(c, ThickLens) else 0.0
    offset: dict[str, Any] = {field: value}
    before = CoordinateBreak(id=f"{comp_id}__cb_in_{field}", position=c.position, **offset)
    R1 = _rotation(before.tilt_x, before.tilt_y, 0.0)
    O1 = np.array([before.decenter_x, before.decenter_y, 0.0])
    p_end = O1 + R1 @ np.array([0.0, 0.0, L])          # relative to the vertex
    dec2 = R1.T @ (np.array([0.0, 0.0, L]) - p_end)
    after = CoordinateBreak(id=f"{comp_id}__cb_out_{field}", position=c.position + L,
                            decenter_x=float(dec2[0]), decenter_y=float(dec2[1]),
                            decenter_z=float(dec2[2]),
                            tilt_x=-before.tilt_x, tilt_y=-before.tilt_y)
    comps[i:i + 1] = [before, c, after]
    return system.model_copy(update={"components": comps})


def set_parameter(system: OpticalSystem, name: str, value: float) -> OpticalSystem:
    """Return a copy of the system with the named parameter set to ``value``."""
    target, field = name.split(".", 1)
    if target == "image_plane":
        return system.model_copy(update={"image_plane": system.image_plane.model_copy(update={field: value})})
    if target == "object":
        return system.model_copy(update={"object": system.object.model_copy(update={field: value})})
    if field in _MISALIGN:
        return _misalign(system, target, field, value) if value else system
    comps = []
    found = False
    for c in system.components:
        if c.id == target:
            if not hasattr(c, field):
                raise ValueError(f"Component '{target}' has no field '{field}'")
            c = c.model_validate({**c.model_dump(), field: value})
            found = True
        comps.append(c)
    if not found:
        raise ValueError(f"No component '{target}'")
    return system.model_copy(update={"components": comps})


def perturb(system: OpticalSystem, name: str, delta: float) -> OpticalSystem:
    """Add ``delta`` to a parameter's nominal value."""
    return set_parameter(system, name, get_parameter(system, name) + delta)


def _perturb_system(system: OpticalSystem, tolerances: dict, rng: random.Random) -> OpticalSystem:
    """Apply one Monte Carlo draw (Gaussian, sigma = tolerance) to every parameter."""
    result = system
    for name, tol in tolerances.items():
        spec = tol if isinstance(tol, ToleranceSpec) else ToleranceSpec(name, 0.0, sigma=float(tol))
        result = perturb(result, name, _draw_from_distribution(spec, rng))
    return result


def _default_metric(s: OpticalSystem) -> float:
    return analyze_system(s).rms_spot_radius


def _default_tolerances(system: OpticalSystem) -> dict:
    return {f"{c.id}.position": _DEFAULT_TOLERANCE for c in system.components
            if isinstance(c, (ThinLens, ThickLens))}


def _stats(samples: list) -> dict:
    arr = np.array(samples)
    return {"mean": float(arr.mean()), "std": float(arr.std()), "min": float(arr.min()),
            "max": float(arr.max()), "p95": float(np.percentile(arr, 95))}


def tolerance_analysis(system: OpticalSystem,
                       metric: Optional[Callable[[OpticalSystem], float]] = None,
                       tolerances: Optional[dict] = None,
                       trials: int = _DEFAULT_TRIALS,
                       seed: Optional[int] = 42) -> dict:
    """
    Monte Carlo tolerance analysis.

    Returns mean/std/min/max/p95 of the metric, the per-trial values
    ("trend"), the nominal value, the number of failed trials (metric could
    not be evaluated, e.g. rays missed an aperture) and the worst system.
    """
    metric = metric or _default_metric
    tolerances = tolerances if tolerances is not None else _default_tolerances(system)
    rng = random.Random(seed)
    samples, failed = [], 0
    worst, worst_val = None, -math.inf
    for _ in range(max(1, trials)):
        perturbed = _perturb_system(system, tolerances, rng)
        try:
            v = float(metric(perturbed))
        except ValueError:
            failed += 1
            continue
        if not math.isfinite(v):
            failed += 1
            continue
        samples.append(v)
        if v > worst_val:
            worst, worst_val = perturbed, v
    base = {"nominal": float(metric(system)), "trials": len(samples), "failed_trials": failed,
            "trend": samples, "worst": worst}
    if not samples:
        base.update({k: float("nan") for k in ("mean", "std", "min", "max", "p95")})
        return base
    base.update(_stats(samples))
    return base


def sensitivity_analysis(system: OpticalSystem, tolerances: dict,
                         metric: Optional[Callable[[OpticalSystem], float]] = None,
                         delta_fraction: float = 1.0) -> dict:
    """
    Tornado analysis: change each parameter by +-(delta_fraction x tolerance)
    from nominal and record the metric.
    """
    metric = metric or _default_metric
    base = float(metric(system))
    rows = []
    for name, tol in tolerances.items():
        d = float(tol.sigma if isinstance(tol, ToleranceSpec) else tol) * delta_fraction
        vals = []
        for sgn in (1.0, -1.0):
            try:
                vals.append(float(metric(perturb(system, name, sgn * d))))
            except ValueError:
                vals.append(float("nan"))
        sens = np.nanmean([abs(v - base) for v in vals]) if np.isfinite(vals).any() else float("nan")
        rows.append({"parameter": name, "base_value": base, "delta": d,
                     "value_plus": vals[0], "value_minus": vals[1], "sensitivity": float(sens),
                     "relative_sensitivity": float(sens / base) if base > 0 else 0.0})
    rows.sort(key=lambda r: (-r["sensitivity"] if math.isfinite(r["sensitivity"]) else math.inf))
    return {"sensitivities": rows, "ranking": [r["parameter"] for r in rows], "base_value": base}


def tolerance_with_compensators(system: OpticalSystem, tolerances: dict,
                                compensators: list,
                                metric: Optional[Callable[[OpticalSystem], float]] = None,
                                trials: int = _DEFAULT_TRIALS,
                                seed: Optional[int] = 42) -> dict:
    """
    Monte Carlo with compensation: after each perturbation, each compensator
    is adjusted (bounded 1-D minimisation, in turn) to minimise the metric,
    and the compensated metric is recorded.
    """
    metric = metric or _default_metric
    rng = random.Random(seed)
    samples, failed = [], 0
    comp_values: dict[str, list] = {c.name: [] for c in compensators}
    for _ in range(max(1, trials)):
        s = _perturb_system(system, tolerances, rng)
        try:
            for comp in compensators:
                x0 = get_parameter(s, comp.parameter)

                def f(off, s=s, comp=comp, x0=x0):
                    try:
                        return float(metric(set_parameter(s, comp.parameter, x0 + off)))
                    except ValueError:
                        return math.inf

                res = minimize_scalar(f, bounds=(comp.min_value, comp.max_value),
                                      method="bounded", options={"xatol": 1e-9})
                best = res.x if f(res.x) <= f(0.0) else 0.0
                s = set_parameter(s, comp.parameter, x0 + best)
                comp_values[comp.name].append(float(best))
            v = float(metric(s))
        except ValueError:
            failed += 1
            continue
        samples.append(v)
    out = {"trials": len(samples), "failed_trials": failed, "trend": samples,
           "compensator_stats": {
               k: {"mean_adjustment": float(np.mean(v)), "std_adjustment": float(np.std(v)),
                   "max_adjustment": float(np.max(v)), "min_adjustment": float(np.min(v))}
               for k, v in comp_values.items() if v}}
    if samples:
        out.update(_stats(samples))
    else:
        out.update({k: float("nan") for k in ("mean", "std", "min", "max", "p95")})
    return out


def compute_yield(samples: list, upper_limit: float,
                  lower_limit: Optional[float] = None) -> dict:
    """
    Fraction of samples within the specification and the process
    capability index Cpk (one-sided when no lower limit is given).
    """
    if not samples:
        return {"yield": 0.0, "cpk": 0.0, "n_pass": 0, "n_total": 0}
    arr = np.array(samples, dtype=float)
    ok = arr <= upper_limit
    if lower_limit is not None:
        ok &= arr >= lower_limit
    mean, std = float(arr.mean()), float(arr.std())
    if std > 0:
        cpu = (upper_limit - mean) / (3 * std)
        cpk = min(cpu, (mean - lower_limit) / (3 * std)) if lower_limit is not None else cpu
    else:
        inside = mean <= upper_limit and (lower_limit is None or mean >= lower_limit)
        cpk = float("inf") if inside else 0.0
    return {"yield": float(ok.mean()), "cpk": float(cpk), "n_pass": int(ok.sum()),
            "n_total": len(arr), "mean": mean, "std": std}
