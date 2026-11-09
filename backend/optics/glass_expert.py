"""
Glass substitution (in the spirit of Code V's glass expert): try the
catalogue glasses nearest each glass of the lens, re-optimize with the
lens's variables, merit and constraints, and keep each substitution that
lowers the merit, in passes until none does. A model glass
(``MODEL:<nd>:<vd>``) is always replaced by its best catalogue candidate.

Nearness is measured in (nd, Vd) with 0.01 in nd counting as 1 in Vd, as
for glass snapping.
"""

from __future__ import annotations

import math
from typing import Optional

from .lens_data import GLASS_PARAMS, LensData
from .lens_optimize import (
    evaluate_constraints,
    merit_report,
    nearest_catalog_glasses,
    optimize,
    variable_keys,
)
from .materials import MATERIALS, parse_model_glass


def _glass_point(material: str) -> tuple[float, float]:
    model = parse_model_glass(material)
    if model is not None:
        return model
    m = MATERIALS.get(material)
    if m is None or m.nd is None or m.vd is None:
        raise ValueError(f"Glass '{material}' has no catalogue nd and Vd")
    return m.nd, m.vd


def _with_glass(lens: LensData, i: int, glass: str) -> LensData:
    out = lens.model_copy(deep=True)
    s = out.surfaces[i]
    s.material = glass
    s.variables = [v for v in s.variables if v not in GLASS_PARAMS]
    s.pickups = {k: p for k, p in s.pickups.items() if k not in GLASS_PARAMS}
    return LensData.model_validate(out.model_dump())


def substitute_glasses(
    lens: LensData,
    surfaces: Optional[list[int]] = None,
    candidates: int = 8,
    vendors: Optional[list[str]] = None,
    include_inquiry: bool = False,
    max_evaluations: int = 150,
    passes: int = 2,
) -> dict:
    """
    Substitute catalogue glasses on ``surfaces`` (default: every surface
    with glass after it), trying the ``candidates`` nearest glasses of the
    chosen ``vendors`` for each.

    Returns the lens, its merit before (the lens as given, re-optimized if
    it has variables) and after, the substitutions made (surface, from, to,
    merit) and the merit evaluations used.
    """
    has_vars = bool(variable_keys(lens))
    evaluations = 0

    def solve(L: LensData) -> Optional[tuple[LensData, float]]:
        nonlocal evaluations
        try:
            if has_vars:
                r = optimize(L, max_evaluations=max_evaluations)
                evaluations += r["evaluations"]
                if not r["success"] or not math.isfinite(r["merit_after"]):
                    return None
                return r["lens"], float(r["merit_after"])
            evaluations += 1
            if L.constraints and not all(
                c["satisfied"] for c in evaluate_constraints(L)
            ):
                return None
            return L, float(merit_report(L)["merit"])
        except ValueError:
            return None

    start = solve(lens)
    if start is None:
        raise ValueError(
            "The lens as given cannot be optimized to meet its constraints"
        )
    best, best_merit = start
    merit_before = best_merit
    if surfaces is None:
        surfaces = [
            i
            for i, s in enumerate(lens.surfaces)
            if s.material is not None and s.material != "MIRROR"
        ]
    log = []
    for _ in range(int(passes)):
        changed = False
        for i in surfaces:
            current = best.surfaces[i].material
            if current is None or current == "MIRROR":
                raise ValueError(f"Surface {i} has no glass to substitute")
            nd, vd = _glass_point(current)
            is_model = parse_model_glass(current) is not None
            options = nearest_catalog_glasses(
                nd,
                vd,
                count=candidates,
                vendors=vendors,
                include_inquiry=include_inquiry,
                exclude={current},
            )
            tried = []
            for g in options:
                out = solve(_with_glass(best, i, g))
                if out is not None:
                    tried.append((out[1], g, out[0]))
            if not tried:
                continue
            m, g, L = min(tried, key=lambda t: t[0])
            if is_model or m < best_merit * (1 - 1e-9):
                log.append({"surface": i, "from": current, "to": g, "merit": m})
                best, best_merit = L, m
                changed = True
        if not changed:
            break
    return {
        "lens": best,
        "merit_before": merit_before,
        "merit_after": best_merit,
        "substitutions": log,
        "evaluations": evaluations,
    }
