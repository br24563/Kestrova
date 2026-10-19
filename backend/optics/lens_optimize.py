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
    Constraint,
    LensData,
    _merit_system,
    _set,
    get_parameter,
    resolve,
    to_system,
    variables,
)
from .models import OpticalSystem

# =============================================================================
# Constraint values
# =============================================================================


def _surface_sag(surface, h: float) -> float:
    """Sag at height h of a standard or even-asphere surface (m)."""
    if surface.surface_type not in ("standard", "even_asphere"):
        raise ValueError(
            f"Edge thickness needs standard surfaces, not {surface.surface_type}"
        )
    sag = 0.0
    if surface.radius:
        c = 1.0 / surface.radius
        arg = 1.0 - (1.0 + surface.conic) * c * c * h * h
        if arg < 0:
            raise ValueError("The semi-diameter exceeds the conic's extent")
        sag = c * h * h / (1.0 + math.sqrt(arg))
    for k, a in enumerate(surface.aspheric_coefficients):
        sag += a * h ** (2 * k + 4)
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


def constraint_value(c: Constraint, lens: LensData, system: OpticalSystem, fo) -> float:
    """Current value of a constraint's property."""
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
    assert c.surface is not None
    if c.kind == "center_thickness":
        return abs(lens.surfaces[c.surface].thickness)
    return edge_thickness(lens, c.surface)


def _needs_apertures(lens: LensData) -> bool:
    return any(c.kind == "edge_thickness" for c in lens.constraints)


def evaluate_constraints(lens: LensData) -> list[dict]:
    """Every constraint with its current value and whether it is met (to
    1e-9 relative)."""
    resolved = resolve(lens, fill_apertures=_needs_apertures(lens))
    system = to_system(resolved) if _needs_apertures(lens) else _merit_system(lens)
    fo = rt.first_order(system)
    out = []
    for c in lens.constraints:
        v = constraint_value(c, resolved, system, fo)
        tol = 1e-9 * max(abs(c.target or c.minimum or c.maximum or 0.0), 1e-9)
        met = (
            abs(v - c.target) <= max(tol, 1e-12)
            if c.target is not None
            else (c.minimum is None or v >= c.minimum - tol)
            and (c.maximum is None or v <= c.maximum + tol)
        )
        out.append({**c.model_dump(), "value": v, "satisfied": bool(met)})
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


_PARAM_SCALE = {
    "radius": 1e-3,
    "thickness": 1e-3,
    "conic": 1e-2,
    "semi_diameter": 1e-3,
    "focal_length": 1e-3,
    "glass_nd": 1e-2,
    "glass_vd": 1.0,
}


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

    Returns the optimized lens and system, the variables, the merit before
    and after (sum of squared residuals; for the default merit the
    mean-square spot in m^2), the constraint report, evaluations,
    iterations, success and a message.
    """
    from .advanced_optimization import ray_aberration_residuals

    var = variables(lens)
    if not var:
        raise ValueError("No surface parameter is flagged as a variable")
    if merit is None:

        def merit(system: OpticalSystem) -> np.ndarray:
            return ray_aberration_residuals(
                system, wavelengths=list(system.wavelengths), vignetting=False
            )

    bounds = dict(bounds or {})
    keys = [f"{i}.{name}" for i, name in var]
    for key in bounds:
        if key not in keys:
            raise ValueError(f"Bound '{key}' is not a variable (variables: {keys})")
    # Radii are varied as curvatures (c = 1/R, 0 = flat), as Code V does:
    # power, and so focal-length constraints, are nearly linear in them.
    is_curv = np.array([name == "radius" for _, name in var])
    raw0 = np.array([get_parameter(lens.surfaces[i], name) for i, name in var])
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
    for i in sorted({i for i, name in var if name in GLASS_PARAMS}):
        nd_k = keys.index(f"{i}.glass_nd") if f"{i}.glass_nd" in keys else None
        vd_k = keys.index(f"{i}.glass_vd") if f"{i}.glass_vd" in keys else None
        glass_pairs.append((nd_k, vd_k, i))

    def apply(x) -> LensData:
        out = lens.model_copy(deep=True)
        for (i, name), v, c in zip(var, x, is_curv):
            _set(out.surfaces[i], name, _to_radius(v) if c else v)
        return out

    evaluations = [0]

    def evaluate(x):
        """(residuals, constraint rows g (normalised), rows) or None if the
        system cannot be traced."""
        evaluations[0] += 1
        try:
            L = apply(x)
            system = _merit_system(L)
            r = np.asarray(merit(system), dtype=float)
            if not np.all(np.isfinite(r)):
                return None
            g, rows = [], []
            if lens.constraints:
                resolved = resolve(L, fill_apertures=need_ap)
                fo = rt.first_order(system)
                for c in lens.constraints:
                    v = constraint_value(c, resolved, system, fo)
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
                        rows.append(_Row("eq", f"{c.kind}={c.target}"))
                    if c.minimum is not None:
                        g.append((v - c.minimum) / s)
                        rows.append(_Row("ineq", f"{c.kind}>={c.minimum}"))
                    if c.maximum is not None:
                        g.append((c.maximum - v) / s)
                        rows.append(_Row("ineq", f"{c.kind}<={c.maximum}"))
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
    norm0 = float(np.sqrt(np.sum(r0**2))) or 1.0
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
        while evaluations[0] < max_evaluations:
            dz, _ = _kkt_step(H + lam * np.diag(D), grad, A, g, eq, tol_active)
            x_try = x + dz * scale
            res = evaluate(x_try)
            if (
                res is not None
                and violation(res[1]) > 0
                and evaluations[0] < max_evaluations
            ):
                # second-order correction: back onto the curved constraints
                # with a minimum-norm step (the linearised step ignores
                # their curvature, which otherwise forces tiny steps)
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
