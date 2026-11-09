"""
Constrained damped least squares for a lens prescription (Code V style).

The merit is the sum of squared residuals (default: transverse ray errors
over the field table and weighted wavelengths, Gaussian pupil quadrature).
Each iteration linearises the residuals and the constraints about the
current variables (finite differences) and takes the damped Gauss-Newton
step that satisfies the linearised constraints exactly, by solving

    [ J^T J + lambda D   A^T ] [dx]   [ -J^T r ]
    [ A                  0   ] [mu] = [ -g     ]

for the active constraints A dx = -g (Lagrange multipliers mu), as in
Code V's damped least squares with exact constraints. Inequalities
(limits, variable bounds, the glass map for model glasses) join the active
set when violated or when the step would violate them, and leave it when
their multiplier says they no longer bind. The damping lambda grows
until a step lowers the merit plus a large multiple of the constraint
violation, and shrinks after each accepted step.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from . import raytrace as rt
from .lens_data import (
    GLASS_PARAMS,
    SHAPED_TYPES,
    LensData,
    _merit_system,
    _set,
    configured,
    get_parameter,
    surface_shape,
    resolve,
    to_system,
    variables,
)
from .merit import image_residuals, property_value
from .models import OpticalSystem

# =============================================================================
# Constraint values
# =============================================================================


def _surface_sag(surface, h: float) -> float:
    """Sag at height h along y of a surface with a shape (m)."""
    if surface.surface_type not in SHAPED_TYPES:
        raise ValueError(
            f"Edge thickness needs surfaces with a shape, not {surface.surface_type}"
        )
    sag = float(surface_shape(surface).sag(np.array(0.0), np.array(h)))
    if not math.isfinite(sag):
        raise ValueError("The semi-diameter exceeds the conic's extent")
    return sag


def edge_thickness(lens: LensData, i: int) -> float:
    """Thickness after surface i at the smaller of the two semi-diameters,
    measured along the direction of travel (the lens must be resolved)."""
    s1, s2 = lens.surfaces[i], lens.surfaces[i + 1]
    if s1.semi_diameter is None or s2.semi_diameter is None:
        raise ValueError(
            "Edge thickness needs both semi-diameters (resolve the lens first)"
        )
    h = min(s1.semi_diameter, s2.semi_diameter)
    sign = 1.0 if s1.thickness >= 0 else -1.0
    return sign * (s1.thickness - _surface_sag(s1, h) + _surface_sag(s2, h))


def constraint_value(c, lens: LensData, system: OpticalSystem, fo) -> float:
    """Current value of a constraint's or operand's property."""
    if c.kind == "efl":
        return fo.efl
    if c.kind == "bfl":
        return fo.bfl
    if c.kind == "working_f_number":
        return fo.working_f_number
    if c.kind == "magnification":
        return fo.magnification
    if c.kind == "total_track":
        return abs(sum(s.thickness for s in lens.surfaces))
    if c.kind == "center_thickness":
        assert c.surface is not None
        return abs(lens.surfaces[c.surface].thickness)
    if c.kind == "edge_thickness":
        assert c.surface is not None
        return edge_thickness(lens, c.surface)
    return property_value(c.kind, system, c.field)


def _needs_apertures(lens: LensData) -> bool:
    return any(c.kind == "edge_thickness" for c in lens.constraints) or any(
        o.kind == "edge_thickness" for o in lens.merit.operands
    )


def merit_report(lens: LensData) -> dict:
    """
    The merit of a lens term by term, per configuration: the image term
    (RMS spot in m, or RMS wavefront in waves) and every operand's value,
    target, weight and contribution (its squared residual), and the total
    (sum of squared residuals, weighted by configuration).
    """
    spec = lens.merit
    n = lens.num_configurations
    weights = lens.configuration_weights or [1.0] * n
    resolved_all = resolve(lens, fill_apertures=_needs_apertures(lens))
    out, total = [], 0.0
    for k in range(n):
        Lk = configured(lens, k) if n > 1 else lens
        resolved = configured(resolved_all, k) if n > 1 else resolved_all
        system = _merit_system(Lk)
        fo = rt.first_order(system)
        image = image_residuals(system, spec)
        image_ms = float(np.sum(image**2))
        ops = []
        for index, o in enumerate(lens.merit.operands):
            if o.configuration is not None and o.configuration != k:
                continue
            v = constraint_value(o, resolved, system, fo)
            c = (o.weight * (v - o.target)) ** 2
            ops.append(
                {**o.model_dump(), "value": v, "contribution": c, "index": index}
            )
        conf_total = image_ms + sum(o["contribution"] for o in ops)
        total += weights[k] * conf_total
        rms = math.sqrt(image_ms) / spec.image_weight if spec.image_weight else None
        out.append(
            {
                "configuration": k,
                "image_kind": spec.kind,
                "image_rms": rms,
                "image_contribution": image_ms,
                "operands": ops,
                "merit": conf_total,
            }
        )
    return {"configurations": out, "merit": total}


def evaluate_constraints(lens: LensData) -> list[dict]:
    """Every constraint with its current value and whether it is met (to
    1e-9 relative). With several configurations, a constraint for every
    configuration is reported once per configuration."""
    need_ap = _needs_apertures(lens)
    resolved_all = resolve(lens, fill_apertures=need_ap)
    n = lens.num_configurations
    out = []
    for k in range(n):
        Lk = configured(lens, k) if n > 1 else lens
        resolved = configured(resolved_all, k) if n > 1 else resolved_all
        system = to_system(resolved) if need_ap else _merit_system(Lk)
        fo = rt.first_order(system)
        for index, c in enumerate(lens.constraints):
            if c.configuration is not None and c.configuration != k:
                continue
            v = constraint_value(c, resolved, system, fo)
            tol = 1e-9 * max(abs(c.target or c.minimum or c.maximum or 0.0), 1e-9)
            met = (
                abs(v - c.target) <= max(tol, 1e-12)
                if c.target is not None
                else (c.minimum is None or v >= c.minimum - tol)
                and (c.maximum is None or v <= c.maximum + tol)
            )
            row = {**c.model_dump(), "value": v, "satisfied": bool(met), "index": index}
            if n > 1:
                row["configuration"] = k
            out.append(row)
    return out


# =============================================================================
# Glass map (model glasses stay inside the catalog's (nd, Vd) hull)
# =============================================================================


@functools.lru_cache(maxsize=1)
def glass_map_hull() -> tuple[np.ndarray, np.ndarray]:
    """(normals, offsets): the convex hull of the vendor glasses' (nd, Vd)
    points as half-planes normals @ (nd, Vd) <= offsets."""
    from scipy.spatial import ConvexHull

    from .materials import MATERIALS

    pts = np.array(
        [
            (m.nd, m.vd)
            for m in MATERIALS.values()
            if m.manufacturer in ("Schott", "Ohara", "Hoya", "CDGM") and m.nd and m.vd
        ]
    )
    hull = ConvexHull(pts)
    eq = hull.equations  # a nd + b vd + c <= 0 inside
    return eq[:, :2].copy(), -eq[:, 2].copy()


# =============================================================================
# Optimizer
# =============================================================================


@dataclass
class _Row:
    kind: str  # "eq" or "ineq" (value >= 0)
    label: str


#: Residual norm below which the merit is treated as zero.
_MERIT_FLOOR = 1e-9
#: Fractions of a rejected step tried before the damping is raised.
_STEP_FRACTIONS = (1.0, 0.5, 0.25)

_PARAM_SCALE = {
    "radius": 1e-3,
    "thickness": 1e-3,
    "conic": 1e-2,
    "semi_diameter": 1e-3,
    "focal_length": 1e-3,
    "glass_nd": 1e-2,
    "glass_vd": 1.0,
}


def _variable_key(handle) -> str:
    i, name, r, k = handle
    return f"{i}.{name}" if r is None else f"{i}.{name}@{k + 1}"


def _start_value(lens: LensData, handle) -> float:
    i, name, r, k = handle
    if r is None:
        return get_parameter(lens.surfaces[i], name)
    value = lens.zoom[r].values[k]
    assert value is not None  # surface zoom rows have every value
    return float(value)


def optimize(
    lens: LensData,
    merit: Optional[Callable[[OpticalSystem], np.ndarray]] = None,
    bounds: Optional[dict[str, tuple[float, float]]] = None,
    max_evaluations: int = 300,
    max_iterations: int = 100,
) -> dict:
    """
    Constrained damped least squares over the lens's variables with solves,
    pickups and the lens's constraints held. ``bounds`` are optional
    ``{"<surface>.<parameter>": (low, high)}`` limits on variables. Only the
    stop limits the beam while optimizing (as in Code V).

    With several configurations the merit is the weighted sum over all of
    them; zoom rows flagged variable add one variable per configuration
    (key ``"<surface>.<parameter>@<configuration number>"``; a bound on
    ``"<surface>.<parameter>"`` applies to every configuration), and each
    constraint holds in its configuration or in all of them.

    Returns the optimized lens and system, the variables, the merit before
    and after (sum of squared residuals; for the default merit the
    mean-square spot in m^2), the constraint report, evaluations,
    iterations, success and a message.
    """
    n_conf = lens.num_configurations
    weights = lens.configuration_weights or [1.0] * n_conf
    # (surface, parameter, zoom row or None, configuration or None)
    handles: list[tuple[int, str, Optional[int], Optional[int]]] = [
        (i, name, None, None) for i, name in variables(lens)
    ]
    for r_idx, row in enumerate(lens.zoom):
        if row.variable and row.surface is not None:
            handles += [(row.surface, row.parameter, r_idx, k) for k in range(n_conf)]
    if not handles:
        raise ValueError("No surface parameter is flagged as a variable")
    var = [(i, name) for i, name, _, _ in handles]
    spec_merit = merit is None  # the lens's own merit and operands

    bounds = dict(bounds or {})
    keys = [_variable_key(h) for h in handles]
    shared = {f"{i}.{name}" for i, name, r, _ in handles if r is not None}
    for key in bounds:
        if key not in keys and key not in shared:
            raise ValueError(f"Bound '{key}' is not a variable (variables: {keys})")
    for key, (i, name, r, _) in zip(keys, handles):
        if r is not None and key not in bounds and f"{i}.{name}" in bounds:
            bounds[key] = bounds[f"{i}.{name}"]
    # Radii are varied as curvatures (c = 1/R, 0 = flat), as Code V does:
    # power, and so focal-length constraints, are nearly linear in them.
    is_curv = np.array([name == "radius" for _, name in var])
    raw0 = np.array([_start_value(lens, h) for h in handles])
    x0 = np.where(is_curv, _to_curvature(raw0), raw0)
    scale = np.array(
        [
            max(abs(v), 1.0) if c else max(abs(v), _PARAM_SCALE.get(name, 1e-3))
            for v, c, (_, name) in zip(x0, is_curv, var)
        ]
    )
    lo = np.full(len(var), -np.inf)
    hi = np.full(len(var), np.inf)
    for k, key in enumerate(keys):
        if key not in bounds:
            continue
        a, b = bounds[key]
        if is_curv[k]:
            if a * b <= 0:
                raise ValueError(
                    f"Bound '{key}': radius bounds must not span a flat surface "
                    "(radii are varied as curvatures)"
                )
            lo[k], hi[k] = sorted((1.0 / a, 1.0 / b))
        else:
            lo[k], hi[k] = a, b
    if np.any(x0 < lo) or np.any(x0 > hi):
        raise ValueError("The starting values must lie within the bounds")
    need_ap = _needs_apertures(lens)
    hull_n, hull_b = glass_map_hull()
    glass_pairs = []  # (index of nd var or None, index of vd var or None, surface)
    for i in sorted(
        {i for i, name, r, _ in handles if name in GLASS_PARAMS and r is None}
    ):
        nd_k = keys.index(f"{i}.glass_nd") if f"{i}.glass_nd" in keys else None
        vd_k = keys.index(f"{i}.glass_vd") if f"{i}.glass_vd" in keys else None
        glass_pairs.append((nd_k, vd_k, i))

    def apply(x) -> LensData:
        out = lens.model_copy(deep=True)
        for (i, name, r, k), v, c in zip(handles, x, is_curv):
            val = float(_to_radius(v) if c else v)
            if r is None:
                _set(out.surfaces[i], name, val)
            else:
                out.zoom[r].values[k] = val  # type: ignore[index]
                if k == 0:  # the surface table shows configuration 1
                    _set(out.surfaces[i], name, val)
        return out

    evaluations = [0]

    def evaluate(x):
        """(residuals, constraint rows g (normalised), rows) or None if the
        system cannot be traced."""
        evaluations[0] += 1
        try:
            L = apply(x)
            confs = [configured(L, k) for k in range(n_conf)] if n_conf > 1 else [L]
            systems = [_merit_system(Lk) for Lk in confs]
            resolved_all = (
                resolve(L, fill_apertures=need_ap)
                if lens.constraints or (spec_merit and lens.merit.operands)
                else None
            )
            parts = []
            for k, (sk, wk) in enumerate(zip(systems, weights)):
                if not spec_merit:
                    assert merit is not None
                    rk = np.asarray(merit(sk), dtype=float)
                else:
                    rk = image_residuals(sk, lens.merit)
                    ops = [
                        o
                        for o in lens.merit.operands
                        if o.configuration is None or o.configuration == k
                    ]
                    if ops:
                        assert resolved_all is not None
                        resolved = (
                            configured(resolved_all, k) if n_conf > 1 else resolved_all
                        )
                        fo_k = rt.first_order(sk)
                        rk = np.concatenate(
                            [
                                rk,
                                [
                                    o.weight
                                    * (
                                        constraint_value(o, resolved, sk, fo_k)
                                        - o.target
                                    )
                                    for o in ops
                                ],
                            ]
                        )
                parts.append(math.sqrt(wk) * rk)
            r = np.concatenate(parts)
            if not np.all(np.isfinite(r)):
                return None
            g, rows = [], []
            if lens.constraints:
                assert resolved_all is not None
                for k, (Lk, sk) in enumerate(zip(confs, systems)):
                    todo = [
                        c
                        for c in lens.constraints
                        if c.configuration is None or c.configuration == k
                    ]
                    if not todo:
                        continue
                    resolved = (
                        configured(resolved_all, k) if n_conf > 1 else resolved_all
                    )
                    fo = rt.first_order(sk)
                    tag = f" [configuration {k + 1}]" if n_conf > 1 else ""
                    for c in todo:
                        v = constraint_value(c, resolved, sk, fo)
                        if not math.isfinite(v):
                            return None
                        ref = (
                            c.target
                            if c.target is not None
                            else (c.minimum if c.minimum is not None else c.maximum)
                        )
                        s = max(abs(ref or 0.0), 1e-6)
                        if c.target is not None:
                            g.append((v - c.target) / s)
                            rows.append(_Row("eq", f"{c.kind}={c.target}{tag}"))
                        if c.minimum is not None:
                            g.append((v - c.minimum) / s)
                            rows.append(_Row("ineq", f"{c.kind}>={c.minimum}{tag}"))
                        if c.maximum is not None:
                            g.append((c.maximum - v) / s)
                            rows.append(_Row("ineq", f"{c.kind}<={c.maximum}{tag}"))
            # linear rows: variable bounds and the glass map
            for k in range(len(x)):
                if np.isfinite(lo[k]):
                    g.append((x[k] - lo[k]) / scale[k])
                    rows.append(_Row("ineq", f"{keys[k]}>={lo[k]}"))
                if np.isfinite(hi[k]):
                    g.append((hi[k] - x[k]) / scale[k])
                    rows.append(_Row("ineq", f"{keys[k]}<={hi[k]}"))
            for nd_k, vd_k, i in glass_pairs:
                nd = (
                    x[nd_k]
                    if nd_k is not None
                    else get_parameter(lens.surfaces[i], "glass_nd")
                )
                vd = (
                    x[vd_k]
                    if vd_k is not None
                    else get_parameter(lens.surfaces[i], "glass_vd")
                )
                for n_vec, b in zip(hull_n, hull_b):
                    # b - n.(nd, vd) >= 0, normalised by |n| in (0.01 nd, 1 vd) units
                    norm = math.hypot(n_vec[0] * 0.01, n_vec[1])
                    g.append((b - n_vec[0] * nd - n_vec[1] * vd) / norm)
                    rows.append(_Row("ineq", f"glass map (surface {i})"))
            return r, np.array(g, dtype=float), rows
        except (ValueError, ZeroDivisionError, FloatingPointError):
            return None

    first = evaluate(x0)
    if first is None:
        raise ValueError("The starting lens cannot be traced")
    r0, g0, rows = first
    # Residuals are normalised by their starting size; below 1e-9 (1 nm RMS
    # for the default spot merit, e.g. ideal lenses) the merit counts as zero,
    # so round-off is not amplified and the constraints drive the steps.
    norm0 = max(float(np.sqrt(np.sum(r0**2))), _MERIT_FLOOR)
    eq = np.array([row.kind == "eq" for row in rows], dtype=bool)
    rho = 1e8  # steep: with the second-order correction steps stay feasible

    def violation(g):
        v = np.where(eq, g, np.minimum(g, 0.0)) if g.size else g
        return float(np.sum(v * v))

    def phi(r, g):
        return float(np.sum((r / norm0) ** 2)) + rho * violation(g)

    x, r, g = x0.copy(), r0, g0
    lam = 1e-3
    message = "maximum iterations reached"
    iterations = 0
    history = [
        {"merit": float(np.sum(r**2)), "violation": violation(g), "damping": lam}
    ]
    tol_active = 1e-9
    for iterations in range(1, max_iterations + 1):
        if evaluations[0] >= max_evaluations:
            message = "maximum evaluations reached"
            break
        # finite-difference Jacobians in scaled variables z = x / scale
        n = len(x)
        J = np.zeros((r.size, n))
        A = np.zeros((g.size, n))
        for k in range(n):
            h = 1e-6
            xk = x.copy()
            xk[k] += h * scale[k]
            res = evaluate(xk)
            if res is None:
                xk[k] = x[k] - h * scale[k]
                res = evaluate(xk)
                h = -h
            if res is None:
                continue  # this variable cannot move from here: leave its column zero
            J[:, k] = (res[0] - r) / norm0 / h
            A[:, k] = (res[1] - g) / h
        rn = r / norm0
        H = J.T @ J
        grad = J.T @ rn
        D = np.maximum(np.diag(H), 1e-12 * max(1.0, float(np.max(np.diag(H)))))
        accepted = False
        while evaluations[0] < max_evaluations and not accepted:
            dz, _ = _kkt_step(H + lam * np.diag(D), grad, A, g, eq, tol_active)
            # Damping shortens only the merit part of the step; the part that
            # meets the linearised constraints stays whole and can overshoot
            # a strongly curved constraint (e.g. a focal length against a
            # spacing), so shorter steps along it are tried too.
            for alpha in _STEP_FRACTIONS:
                if evaluations[0] >= max_evaluations:
                    break
                x_try = x + alpha * dz * scale
                res = evaluate(x_try)
                if (
                    res is not None
                    and violation(res[1]) > 0
                    and evaluations[0] < max_evaluations
                ):
                    # second-order correction: back onto the curved
                    # constraints with a minimum-norm step (the linearised
                    # step ignores their curvature, which otherwise forces
                    # tiny steps)
                    corr = _restore(A, res[1], eq, tol_active)
                    if corr is not None:
                        x_soc = x_try + corr * scale
                        res_soc = evaluate(x_soc)
                        if res_soc is not None and phi(res_soc[0], res_soc[1]) < phi(
                            res[0], res[1]
                        ):
                            x_try, res = x_soc, res_soc
                if res is not None and phi(res[0], res[1]) < phi(r, g) * (1 - 1e-12):
                    prev = phi(r, g)
                    x, r, g = x_try, res[0], res[1]
                    lam = max(lam / 5.0, 1e-12)
                    accepted = True
                    break
            if accepted:
                break
            lam *= 10.0
            if lam > 1e12:
                break
        history.append(
            {"merit": float(np.sum(r**2)), "violation": violation(g), "damping": lam}
        )
        if not accepted:
            message = "converged (no step lowers the merit further)"
            break
        if abs(prev - phi(r, g)) <= 1e-9 * max(prev, 1e-30) and violation(g) < 1e-18:
            message = "converged"
            break
    # final restoration: meet the constraints to round-off (Newton steps on
    # the constraints alone, Jacobian re-evaluated each time)
    for _ in range(8):
        if (
            violation(g) < 1e-24
            or evaluations[0] + len(x) + 1 > max_evaluations + 4 * len(x) + 8
        ):
            break
        A = np.zeros((g.size, len(x)))
        for k in range(len(x)):
            xk = x.copy()
            xk[k] += 1e-6 * scale[k]
            res = evaluate(xk)
            if res is not None:
                A[:, k] = (res[1] - g) / 1e-6
        corr = _restore(A, g, eq, tol_active)
        if corr is None:
            break
        res = evaluate(x + corr * scale)
        if res is None or violation(res[1]) >= violation(g):
            break
        x, r, g = x + corr * scale, res[0], res[1]
    best = resolve(apply(x))
    report = evaluate_constraints(best) if lens.constraints else []
    return {
        "lens": best,
        "system": to_system(best),
        "variables": {
            k: float(_to_radius(v) if c else v) for k, v, c in zip(keys, x, is_curv)
        },
        "merit_before": float(np.sum(r0**2)),
        "merit_after": float(np.sum(r**2)),
        "constraints": report,
        "evaluations": evaluations[0],
        "iterations": iterations,
        "history": history,
        "success": all(c["satisfied"] for c in report),
        "message": message,
    }


def _to_curvature(radius):
    radius = np.asarray(radius, dtype=float)
    with np.errstate(divide="ignore"):
        return np.where(radius == 0, 0.0, 1.0 / np.where(radius == 0, 1.0, radius))


def _to_radius(c: float) -> float:
    return 0.0 if c == 0 else 1.0 / float(c)


def _restore(A, g, eq, tol_active):
    """Minimum-norm step zeroing the violated and equality constraints
    (linearised), or None if there is nothing to restore."""
    rows = eq | (g < -tol_active)
    if not rows.any():
        return None
    step = np.zeros(A.shape[1])
    for _ in range(A.shape[0] + 1):
        step = -np.linalg.lstsq(A[rows], g[rows], rcond=None)[0]
        # inequalities the step would break are held on their boundary
        add = (~rows) & (g + A @ step < -tol_active)
        if not add.any():
            break
        rows |= add
    return step


def _kkt_step(Hd, grad, A, g, eq, tol_active):
    """Damped Gauss-Newton step meeting the active linearised constraints;
    returns (step, multipliers of every row, zero when inactive)."""
    n = Hd.shape[0]
    mu_full = np.zeros(A.shape[0])
    if A.shape[0] == 0:
        return np.linalg.lstsq(Hd, -grad, rcond=None)[0], mu_full
    active = eq | (g < tol_active)
    dz = np.zeros(n)
    idx = np.zeros(0, dtype=int)
    mu = np.zeros(0)
    for _ in range(2 * A.shape[0] + 2):
        idx = np.flatnonzero(active)
        if idx.size == 0:
            dz = np.linalg.lstsq(Hd, -grad, rcond=None)[0]
            mu = np.zeros(0)
        else:
            Aa = A[idx]
            K = np.block([[Hd, Aa.T], [Aa, np.zeros((idx.size, idx.size))]])
            rhs = np.concatenate([-grad, -g[idx]])
            sol = np.linalg.lstsq(K, rhs, rcond=None)[0]
            dz, mu = sol[:n], sol[n:]
        changed = False
        # inequalities the step would violate join the active set
        pred = g + A @ dz
        add = (~active) & (pred < -tol_active)
        if add.any():
            active |= add
            changed = True
        # satisfied inequalities whose multiplier pushes away leave it
        if idx.size:
            for j, m in zip(idx, mu):
                if not eq[j] and g[j] >= 0 and m > 1e-12:
                    active[j] = False
                    changed = True
        if not changed:
            break
    else:
        changed = True
    if changed or np.any(~eq & (g + A @ dz < -tol_active)):
        # the active-set iteration cycled (typically at a corner of the
        # glass map): solve the small QP directly
        dz = _qp(Hd, grad, A, g, eq, dz)
        return dz, mu_full
    mu_full[idx] = mu
    return dz, mu_full


def _qp(Hd, grad, A, g, eq, start):
    """min 1/2 dz.Hd.dz + grad.dz  s.t.  g + A dz = 0 (eq), >= 0 (others)."""
    from scipy.optimize import minimize

    cons = []
    if eq.any():
        cons.append(
            {"type": "eq", "fun": lambda d: g[eq] + A[eq] @ d, "jac": lambda d: A[eq]}
        )
    if (~eq).any():
        cons.append(
            {
                "type": "ineq",
                "fun": lambda d: g[~eq] + A[~eq] @ d,
                "jac": lambda d: A[~eq],
            }
        )
    sol = minimize(
        lambda d: 0.5 * d @ Hd @ d + grad @ d,
        start,
        jac=lambda d: Hd @ d + grad,
        constraints=cons,
        method="SLSQP",
        options={"ftol": 1e-15, "maxiter": 500},
    )
    return sol.x if np.all(np.isfinite(sol.x)) else start


# =============================================================================
# Glass substitution
# =============================================================================


def nearest_catalog_glass(
    nd: float,
    vd: float,
    vendors: Optional[list[str]] = None,
    include_inquiry: bool = False,
    nd_per_vd: float = 0.01,
) -> str:
    """
    The catalog glass nearest to (nd, Vd) in the metric
    sqrt((d nd / nd_per_vd)^2 + (d Vd)^2): by default 0.01 in nd counts as
    much as 1 in Vd. SCHOTT 'inquiry' glasses (made on request) are skipped
    unless ``include_inquiry``.
    """
    from .materials import MATERIALS

    wanted = {v.lower() for v in (vendors or ["Schott", "Ohara", "Hoya", "CDGM"])}
    best, best_d = None, math.inf
    for name, m in MATERIALS.items():
        if (m.manufacturer or "").lower() not in wanted or m.nd is None or m.vd is None:
            continue
        if m.status == "inquiry" and not include_inquiry:
            continue
        d = math.hypot((m.nd - nd) / nd_per_vd, m.vd - vd)
        if d < best_d:
            best, best_d = name, d
    if best is None:
        raise ValueError("No catalog glass matches the vendor selection")
    return best


def snap_glasses(
    lens: LensData, vendors: Optional[list[str]] = None, include_inquiry: bool = False
) -> tuple[LensData, list[dict]]:
    """Replace every model glass by its nearest catalog glass; glass
    variables on those surfaces are dropped. Returns (lens, substitutions)."""
    from .materials import parse_model_glass

    out = lens.model_copy(deep=True)
    subs = []
    for i, s in enumerate(out.surfaces):
        model = parse_model_glass(s.material or "")
        if model is None:
            continue
        glass = nearest_catalog_glass(
            *model, vendors=vendors, include_inquiry=include_inquiry
        )
        subs.append({"surface": i, "model": s.material, "glass": glass})
        s.variables = [v for v in s.variables if v not in GLASS_PARAMS]
        s.pickups = {k: p for k, p in s.pickups.items() if k not in GLASS_PARAMS}
        s.material = glass
    return LensData.model_validate(out.model_dump()), subs
