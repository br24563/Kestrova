"""
Tolerance analysis (Phase 8).

Tolerance analysis estimates how manufacturing and alignment variations
affect the optical performance of a system. This is done with a Monte
Carlo simulation: each optical parameter is perturbed by a random amount
drawn from a normal distribution with a specified standard deviation,
and the system performance is re-analyzed many times.

This is purely statistical; all optical math is delegated to the
validated optics engine (analysis.py, systems.py).

All values are in SI base units (meters, radians).
"""

import random
from typing import Callable, Optional

import numpy as np

from .models import OpticalSystem
from .analysis import analyze_system
from .systems import update_component


# Default number of Monte Carlo trials and default per-tolerance scale.
_DEFAULT_TRIALS = 100
_DEFAULT_TOLERANCE = 1.0e-4  # 0.1 mm positional/parameter tolerance


def _perturb_system(
    system: OpticalSystem,
    tolerances: dict[str, float],
    rng: random.Random,
) -> OpticalSystem:
    """
    Return a copy of the system with each specified component parameter
    perturbed by a Gaussian draw with std equal to its tolerance.

    Args:
        system: The base optical system.
        tolerances: dict mapping "{component_id}.{field}" or "object.position"
            to a standard tolerance (meters). Each listed parameter is
            perturbed.
        rng: A seeded random.Random instance.

    Returns:
        A perturbed OpticalSystem.
    """
    result = system
    for spec, tol in tolerances.items():
        if "." not in spec:
            continue
        comp_id, field = spec.split(".", 1)
        delta = rng.gauss(0.0, tol)
        try:
            result = update_component(result, comp_id, **{field: delta})
        except Exception:
            # Component id not found or field not applicable; skip.
            continue
    return result


def tolerance_analysis(
    system: OpticalSystem,
    metric: Optional[Callable[[OpticalSystem], float]] = None,
    tolerances: Optional[dict[str, float]] = None,
    trials: int = _DEFAULT_TRIALS,
    seed: Optional[int] = 42,
) -> dict:
    """
    Run a Monte-Carlo tolerance analysis on an optical system.

    Args:
        system: The optical system.
        metric: Function returning the performance metric to track
            (e.g. RMS spot radius). If None, RMS spot radius is used.
        tolerances: dict mapping "component.field" to a std-dev tolerance
            (meters). If None, all ThinLens/ThickLens positions are given
            the default 0.1 mm tolerance.
        trials: Number of Monte Carlo samples.
        seed: Random seed for reproducibility.

    Returns:
        Dict with:
            - "mean": mean metric value
            - "std": standard deviation of the metric
            - "min": minimum metric value
            - "max": maximum metric value
            - "p95": 95th percentile
            - "worst": the worst (largest) metric system
            - "samples": the metric value for each trial
    """
    if metric is None:
        metric = lambda s: analyze_system(s).rms_spot_radius

    if tolerances is None:
        tolerances = {}
        for comp in system.components:
            if hasattr(comp, "position"):
                tolerances[f"{comp.id}.position"] = _DEFAULT_TOLERANCE

    rng = random.Random(seed)
    samples: list[float] = []
    worst_system: Optional[OpticalSystem] = None
    worst_value = float("-inf")

    for _ in range(max(1, trials)):
        perturbed = _perturb_system(system, tolerances, rng)
        try:
            value = float(metric(perturbed))
        except Exception:
            continue
        samples.append(value)
        if value > worst_value:
            worst_value = value
            worst_system = perturbed

    if not samples:
        return {
            "mean": float("nan"), "std": float("nan"),
            "min": float("nan"), "max": float("nan"),
            "p95": float("nan"), "trend": [], "worst": None,
        }

    arr = np.array(samples)
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "p95": float(np.percentile(arr, 95)),
        "trials": len(samples),
        "trend": samples,
        "worst": worst_system,
    }