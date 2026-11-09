"""
Global optimization of a lens prescription (in the spirit of Code V's
Global Synthesis): many local optimizations from starting points spread
over the variables' ranges, keeping the distinct designs that meet every
constraint, best merit first.

Starting points are a scrambled Sobol sequence over each variable's range
(radii are sampled as curvatures, so a range may pass through flat), plus
the lens as given. Each start runs the full constrained damped least
squares of :mod:`optics.lens_optimize` with the lens's merit, operands and
constraints. Two results are the same design when every variable agrees to
1e-3 of its range.
"""

from __future__ import annotations

import math
import warnings
from typing import Optional

import numpy as np
from scipy.stats import qmc

from .lens_data import LensData, resolve
from .lens_optimize import (
    _PARAM_SCALE,
    optimize,
    variable_keys,
    variable_values,
    with_variable_values,
)

Range = tuple[float, float]


def _semi_max(lens: LensData) -> float:
    try:
        semis = [s.semi_diameter for s in resolve(lens).surfaces if s.semi_diameter]
    except ValueError:
        semis = [s.semi_diameter for s in lens.surfaces if s.semi_diameter]
    return max(semis) if semis else 0.01


def sampling_ranges(
    lens: LensData, ranges: Optional[dict[str, Range]] = None
) -> dict[str, tuple[str, float, float]]:
    """
    The range each variable's starting values are drawn from, as
    (space, low, high) with space "curvature" (1/m) for radii and "value"
    otherwise. ``ranges`` overrides any variable: radii are given as
    curvatures (1/m), everything else in its own units.

    Defaults: a curvature within max(2 |c|, 0.5 / largest semi-diameter) of
    its value; a thickness from half to 1.5 times its value; any other
    parameter within max(|v|, its scale) of its value.
    """
    ranges = dict(ranges or {})
    values = variable_values(lens)
    semi = _semi_max(lens)
    out = {}
    for key, v in values.items():
        name = key.split(".", 1)[1].split("@")[0]
        if name == "radius":
            c = 1.0 / v if v else 0.0
            if key in ranges:
                lo, hi = sorted(ranges[key])
            else:
                d = max(2.0 * abs(c), 0.5 / semi)
                lo, hi = c - d, c + d
            out[key] = ("curvature", lo, hi)
            continue
        if key in ranges:
            lo, hi = sorted(ranges[key])
        elif name == "thickness":
            lo, hi = sorted((0.5 * v, 1.5 * v))
        else:
            d = max(abs(v), _PARAM_SCALE.get(name, 1e-3))
            lo, hi = v - d, v + d
        out[key] = ("value", lo, hi)
    for key in ranges:
        if key not in out:
            raise ValueError(
                f"Range '{key}' is not a variable (variables: {list(out)})"
            )
    return out


def _to_value(space: str, u: float) -> float:
    if space == "curvature":
        return 1.0 / u if u else 0.0
    return u


def _coords(values: dict[str, float], rng: dict) -> np.ndarray:
    """Variable values as fractions of their sampling ranges."""
    out = []
    for key, (space, lo, hi) in rng.items():
        v = values[key]
        u = (1.0 / v if v else 0.0) if space == "curvature" else v
        out.append((u - lo) / (hi - lo) if hi > lo else 0.0)
    return np.array(out)


def _run_start(job) -> Optional[dict]:
    """One local optimization (module level so worker processes can run it)."""
    start, bounds, max_evaluations = job
    try:
        r = optimize(start, bounds=bounds, max_evaluations=max_evaluations)
    except ValueError:
        return None
    return {
        k: r[k] for k in ("lens", "merit_after", "variables", "evaluations", "success")
    }


def global_optimize(
    lens: LensData,
    starts: int = 16,
    max_evaluations: int = 200,
    bounds: Optional[dict[str, tuple[float, float]]] = None,
    ranges: Optional[dict[str, Range]] = None,
    seed: Optional[int] = 0,
    keep: int = 5,
    workers: int = 1,
) -> dict:
    """
    Local optimizations from ``starts`` Sobol points (plus the lens as
    given), each limited to ``max_evaluations``. ``bounds`` are passed to
    every local optimization (as :func:`optimize` takes them); ``ranges``
    set where starts are drawn (see :func:`sampling_ranges`).

    Returns ``solutions`` (up to ``keep`` distinct designs meeting every
    constraint, best merit first, each with its lens, merit, variables and
    the start it came from), and the numbers of starts, feasible results,
    distinct designs and merit evaluations. ``workers`` > 1 runs the starts
    in that many processes.
    """
    keys = variable_keys(lens)
    if not keys:
        raise ValueError("No surface parameter is flagged as a variable")
    rng = sampling_ranges(lens, ranges)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # Sobol balance warning for non-powers of 2
        unit = qmc.Sobol(len(keys), scramble=True, seed=seed).random(int(starts))
    candidates: list[dict[str, float]] = [variable_values(lens)]
    for row in unit:
        candidates.append(
            {
                key: _to_value(space, lo + t * (hi - lo))
                for t, (key, (space, lo, hi)) in zip(row, rng.items())
            }
        )
    jobs = [
        (with_variable_values(lens, values), bounds, max_evaluations)
        for values in candidates
    ]
    if workers > 1 and len(jobs) > 1:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        # "spawn": forking a process that holds compiled kernels and threads
        # is unsafe (see optics.performance)
        with ProcessPoolExecutor(
            max_workers=min(int(workers), len(jobs)),
            mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            results = list(pool.map(_run_start, jobs))
    else:
        results = [_run_start(job) for job in jobs]
    found: list[dict] = []
    evaluations = 0
    feasible = 0
    for index, r in enumerate(results):
        if r is None:
            continue  # this start cannot be traced
        evaluations += r["evaluations"]
        if not r["success"] or not math.isfinite(r["merit_after"]):
            continue
        feasible += 1
        found.append(
            {
                "lens": r["lens"],
                "merit": float(r["merit_after"]),
                "variables": r["variables"],
                "start": index,
                "coords": _coords(r["variables"], rng),
            }
        )
    found.sort(key=lambda s: s["merit"])
    distinct: list[dict] = []
    for s in found:
        if all(np.max(np.abs(s["coords"] - d["coords"])) > 1e-3 for d in distinct):
            distinct.append(s)
    for s in distinct:
        s.pop("coords")
    return {
        "solutions": distinct[: int(keep)],
        "starts": len(candidates),
        "feasible": feasible,
        "distinct": len(distinct),
        "evaluations": evaluations,
    }
