"""
Optical system optimization.

This module provides tools for optimizing optical systems:
    - Parameter sweeps: evaluate a system across a range of a parameter.
    - Numerical optimization: use SciPy to find optimal parameter values
      that minimize an objective function.

All calculations are performed by the validated optics engine
(analysis.py, rays.py, lenses.py). This module only orchestrates the
search over parameter space; it never invents optical math.

All length values are in meters (SI base unit).

Sign convention (optics, used in optical design software):
    - Object distance (s): NEGATIVE if object is to the LEFT of the lens.
    - Image distance (s'): NEGATIVE if image is to the LEFT of the lens.
    - Image distance (s'): POSITIVE if image is to the RIGHT of the lens.
    - Magnification: m = s' / s (negative = inverted).
"""

from typing import Callable, Optional, Union

import numpy as np
from scipy.optimize import differential_evolution

from .models import OpticalSystem, AnalysisResult
from .analysis import analyze_system, effective_focal_length, system_magnification
from .systems import update_component


# ---------------------------------------------------------------------------
# Constraint Handling
# ---------------------------------------------------------------------------

# Constraint penalty applied when a constraint is violated.
CONSTRAINT_PENALTY = 1e6


def _constraint_value(system: OpticalSystem, field: str) -> float:
    """
    Extract a scalar value from an analyzed system for constraint checking.

    Supported fields:
        - "magnification"
        - "effective_focal_length"
        - "f_number"
        - "numerical_aperture"
        - "rms_spot_radius"
        - "image_distance"
        - "object_distance"
        - "working_distance"
        - "aperture_diameter"

    Args:
        system: The optical system.
        field: The analysis field name.

    Returns:
        The scalar value (meters or dimensionless).

    Raises:
        ValueError: If the field is not supported.
    """
    result = analyze_system(system)
    mapping = {
        "magnification": result.magnification,
        "effective_focal_length": result.effective_focal_length,
        "f_number": result.f_number,
        "numerical_aperture": result.numerical_aperture,
        "rms_spot_radius": result.rms_spot_radius,
        "image_distance": result.image_distance,
        "object_distance": result.object_distance,
        "working_distance": result.working_distance,
        "aperture_diameter": result.aperture_diameter,
    }
    if field not in mapping:
        raise ValueError(
            f"Unsupported constraint field: '{field}'. "
            f"Supported: {list(mapping.keys())}"
        )
    return mapping[field]


def _constraint_penalty(system: OpticalSystem, constraints: list[dict]) -> float:
    """
    Compute the total penalty for a system given a list of constraints.

    Each constraint is a dict of the form:
        {"type": "range", "field": "magnification", "min": -2.0, "max": -1.0}

    A penalty is added if the field value falls outside [min, max]. The
    penalty is proportional to the amount of violation, scaled by
    CONSTRAINT_PENALTY.

    Args:
        system: The optical system.
        constraints: List of constraint dicts.

    Returns:
        Total penalty (0.0 if all constraints are satisfied).
    """
    total = 0.0
    for c in constraints:
        ctype = c.get("type", "range")
        if ctype != "range":
            raise ValueError(f"Unsupported constraint type: '{ctype}'")
        field = c.get("field")
        if not field:
            raise ValueError("Constraint requires a 'field'.")
        value = _constraint_value(system, field)
        lo = c.get("min")
        hi = c.get("max")
        if lo is not None and value < lo:
            total += CONSTRAINT_PENALTY * (lo - value)
        if hi is not None and value > hi:
            total += CONSTRAINT_PENALTY * (value - hi)
    return total


# ---------------------------------------------------------------------------
# Parameter Specification
# ---------------------------------------------------------------------------

def _set_parameter(system: OpticalSystem, param_spec: dict, value: float) -> OpticalSystem:
    """
    Return a copy of the system with a single parameter set to a value.

    The parameter spec is a dict with one of these forms:
        - {"component_id": "lens_1", "field": "position"}
        - {"component_id": "lens_1", "field": "focal_length"}
        - {"field": "object.position"}
        - {"field": "image_plane.position"}

    Args:
        system: The optical system.
        param_spec: Dict describing which parameter to modify.
        value: The new value (meters, or meters for focal length).

    Returns:
        A new OpticalSystem with the parameter updated.

    Raises:
        ValueError: If the param_spec is invalid.
    """
    if "component_id" in param_spec:
        field = param_spec.get("field")
        if not field:
            raise ValueError("param_spec with component_id requires a 'field'.")
        return update_component(system, param_spec["component_id"], **{field: value})

    field = param_spec.get("field", "")
    if field == "object.position":
        return system.model_copy(update={"object": system.object.model_copy(update={"position": value})})
    if field == "object.height":
        return system.model_copy(update={"object": system.object.model_copy(update={"height": value})})
    if field == "image_plane.position":
        return system.model_copy(update={"image_plane": system.image_plane.model_copy(update={"position": value})})

    raise ValueError(f"Unsupported param_spec: {param_spec}")


# ---------------------------------------------------------------------------
# Parameter Sweep
# ---------------------------------------------------------------------------

def parameter_sweep(
    system: OpticalSystem,
    param_spec: dict,
    values: list[float],
    num_rays: Optional[int] = None,
    aperture_fraction: Optional[float] = None,
) -> list[tuple[float, AnalysisResult]]:
    """
    Sweep a single parameter across a range of values and analyze each.

    This is useful for understanding how a system behaves as a parameter
    (e.g. lens position, focal length, object position) changes.

    Args:
        system: The optical system.
        param_spec: Dict describing which parameter to sweep
            (see _set_parameter for the format).
        values: List of parameter values to evaluate (meters).
        num_rays: Number of rays to trace for each analysis.
        aperture_fraction: Fraction of aperture to use.

    Returns:
        List of (value, AnalysisResult) tuples, one per input value.
    """
    results: list[tuple[float, AnalysisResult]] = []
    for value in values:
        modified = _set_parameter(system, param_spec, value)
        result = analyze_system(modified, num_rays, aperture_fraction)
        results.append((value, result))
    return results


# ---------------------------------------------------------------------------
# Objective Functions
# ---------------------------------------------------------------------------

def minimize_rms_spot(system: OpticalSystem) -> float:
    """
    Objective: minimize the RMS spot radius at the image plane.

    A smaller spot radius means a sharper image.

    Args:
        system: The optical system.

    Returns:
        RMS spot radius (meters). Lower is better.
    """
    result = analyze_system(system)
    return result.rms_spot_radius


def target_magnification(system: OpticalSystem, target: float) -> float:
    """
    Objective: drive the system magnification toward a target value.

    Args:
        system: The optical system.
        target: Desired magnification (dimensionless).

    Returns:
        Absolute error between actual and target magnification.
    """
    mag = system_magnification(system)
    return abs(mag - target)


def target_efl(system: OpticalSystem, target: float) -> float:
    """
    Objective: drive the effective focal length toward a target value.

    Args:
        system: The optical system.
        target: Desired effective focal length (meters).

    Returns:
        Absolute error between actual and target EFL (meters).
    """
    try:
        efl = effective_focal_length(system)
    except ValueError:
        # Afocal system: return a large penalty
        return 1e6
    return abs(efl - target)


# ---------------------------------------------------------------------------
# Numerical Optimization
# ---------------------------------------------------------------------------

def optimize_system(
    system: OpticalSystem,
    objective: Callable[[OpticalSystem], float],
    params: list[dict],
    bounds: list[tuple[float, float]],
    seed: Optional[int] = None,
    maxiter: int = 1000,
    tol: float = 1e-6,
    constraints: Optional[list[dict]] = None,
) -> dict:
    """
    Optimize a set of system parameters to minimize an objective function.

    Uses SciPy's differential_evolution, a global optimizer that does not
    require gradients. This is robust for optical systems where the
    objective may be non-smooth (e.g. spot radius).

    Constraints are handled via a penalty method: any constraint violation
    adds a large penalty to the objective, steering the optimizer toward
    feasible solutions.

    Args:
        system: The optical system to optimize.
        objective: Function that takes an OpticalSystem and returns a
            scalar to minimize.
        params: List of parameter specs (see _set_parameter for format).
        bounds: List of (min, max) tuples, one per parameter (meters).
        seed: Random seed for reproducibility.
        maxiter: Maximum number of generations for the optimizer.
        tol: Relative tolerance for convergence.
        constraints: Optional list of constraint dicts, each of the form
            {"type": "range", "field": "magnification", "min": -2.0, "max": -1.0}.
            Supported fields: magnification, effective_focal_length, f_number,
            numerical_aperture, rms_spot_radius, image_distance, object_distance,
            working_distance, aperture_diameter.

    Returns:
        Dict with keys:
            - "params": list of optimal parameter values (meters)
            - "objective": the objective value at the optimum
            - "system": the optimized OpticalSystem
            - "success": bool indicating whether optimization converged
            - "constraints_satisfied": bool indicating whether all
              constraints are met at the optimum

    Raises:
        ValueError: If len(params) != len(bounds).
    """
    if len(params) != len(bounds):
        raise ValueError("params and bounds must have the same length.")

    constraints = constraints or []

    def cost(x: np.ndarray) -> float:
        modified = system
        for spec, value in zip(params, x):
            modified = _set_parameter(modified, spec, float(value))
        base = float(objective(modified))
        penalty = _constraint_penalty(modified, constraints)
        return base + penalty

    result = differential_evolution(
        cost,
        bounds=bounds,
        seed=seed,
        maxiter=maxiter,
        tol=tol,
        polish=True,
    )

    # Build the optimized system
    optimized = system
    for spec, value in zip(params, result.x):
        optimized = _set_parameter(optimized, spec, float(value))

    # Check whether constraints are satisfied at the optimum
    constraints_satisfied = _constraint_penalty(optimized, constraints) == 0.0

    return {
        "params": [float(v) for v in result.x],
        "objective": float(result.fun),
        "system": optimized,
        "success": result.success,
        "constraints_satisfied": constraints_satisfied,
    }


# ---------------------------------------------------------------------------
# Multi-Objective Optimization
# ---------------------------------------------------------------------------

def multi_objective_optimize(
    system: OpticalSystem,
    objectives: list[Callable[[OpticalSystem], float]],
    weights: Optional[list[float]] = None,
    params: Optional[list[dict]] = None,
    bounds: Optional[list[tuple[float, float]]] = None,
    seed: Optional[int] = None,
    maxiter: int = 1000,
    tol: float = 1e-6,
    constraints: Optional[list[dict]] = None,
) -> dict:
    """
    Optimize a set of system parameters against multiple objectives.

    Uses a weighted-sum scalarization: the combined objective is
    sum(weights[i] * objectives[i](system)). This is a simple and robust
    approach for multi-objective optical design where the objectives are
    typically competing (e.g. minimize spot size while achieving a target
    magnification).

    Args:
        system: The optical system to optimize.
        objectives: List of objective functions, each taking an
            OpticalSystem and returning a scalar to minimize.
        weights: Optional list of weights, one per objective. If None,
            equal weights are used. Weights are normalized to sum to 1.
        params: List of parameter specs. If None, defaults to optimizing
            the first lens focal length.
        bounds: List of (min, max) tuples, one per parameter. If None,
            defaults to a reasonable range around the current value.
        seed: Random seed for reproducibility.
        maxiter: Maximum number of generations for the optimizer.
        tol: Relative tolerance for convergence.
        constraints: Optional list of constraint dicts (see optimize_system).

    Returns:
        Dict with keys:
            - "params": list of optimal parameter values (meters)
            - "objective": the combined weighted objective value
            - "objectives": list of individual objective values at the optimum
            - "system": the optimized OpticalSystem
            - "success": bool indicating whether optimization converged
            - "constraints_satisfied": bool

    Raises:
        ValueError: If objectives is empty, or weights length mismatches.
    """
    if not objectives:
        raise ValueError("At least one objective is required.")

    if weights is None:
        weights = [1.0] * len(objectives)
    if len(weights) != len(objectives):
        raise ValueError("weights and objectives must have the same length.")

    # Normalize weights to sum to 1
    total_w = sum(abs(w) for w in weights)
    if total_w < 1e-15:
        raise ValueError("Weights must not all be zero.")
    norm_weights = [w / total_w for w in weights]

    # Default params: first lens focal length
    if params is None:
        from .models import ThinLens, ThickLens
        lenses = [
            c for c in system.components
            if isinstance(c, (ThinLens, ThickLens))
        ]
        if not lenses:
            raise ValueError("System has no lens to optimize.")
        first = min(lenses, key=lambda l: l.position)
        field = "focal_length" if isinstance(first, ThinLens) else "radius1"
        params = [{"component_id": first.id, "field": field}]

    # Default bounds: 0.5x to 2x the current value (ordered for either sign)
    if bounds is None:
        bounds = []
        for spec in params:
            current = _current_parameter(system, spec)
            if current == 0:
                raise ValueError(f"Cannot derive default bounds for a zero parameter: {spec}")
            lo, hi = current * 0.5, current * 2.0
            bounds.append((min(lo, hi), max(lo, hi)))

    if len(params) != len(bounds):
        raise ValueError("params and bounds must have the same length.")

    constraints = constraints or []

    def combined_objective(modified: OpticalSystem) -> float:
        total = 0.0
        for w, obj in zip(norm_weights, objectives):
            total += w * float(obj(modified))
        return total

    def cost(x: np.ndarray) -> float:
        modified = system
        for spec, value in zip(params, x):
            modified = _set_parameter(modified, spec, float(value))
        base = combined_objective(modified)
        penalty = _constraint_penalty(modified, constraints)
        return base + penalty

    result = differential_evolution(
        cost,
        bounds=bounds,
        seed=seed,
        maxiter=maxiter,
        tol=tol,
        polish=True,
    )

    # Build the optimized system
    optimized = system
    for spec, value in zip(params, result.x):
        optimized = _set_parameter(optimized, spec, float(value))

    # Individual objective values at the optimum
    individual = [float(obj(optimized)) for obj in objectives]

    constraints_satisfied = _constraint_penalty(optimized, constraints) == 0.0

    return {
        "params": [float(v) for v in result.x],
        "objective": float(result.fun),
        "objectives": individual,
        "system": optimized,
        "success": result.success,
        "constraints_satisfied": constraints_satisfied,
    }


def _current_parameter(system: OpticalSystem, param_spec: dict) -> float:
    """
    Return the current value of a parameter described by a param_spec.

    Args:
        system: The optical system.
        param_spec: Dict describing the parameter (see _set_parameter).

    Returns:
        The current value (meters or dimensionless).

    Raises:
        ValueError: If the param_spec is invalid.
    """
    if "component_id" in param_spec:
        field = param_spec.get("field")
        if not field:
            raise ValueError("param_spec with component_id requires a 'field'.")
        comp = next(
            (c for c in system.components if c.id == param_spec["component_id"]),
            None,
        )
        if comp is None:
            raise ValueError(f"Component not found: {param_spec['component_id']}")
        return float(getattr(comp, field))

    field = param_spec.get("field", "")
    if field == "object.position":
        return system.object.position
    if field == "object.height":
        return system.object.height
    if field == "image_plane.position":
        return system.image_plane.position

    raise ValueError(f"Unsupported param_spec: {param_spec}")
