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
) -> dict:
    """
    Optimize a set of system parameters to minimize an objective function.

    Uses SciPy's differential_evolution, a global optimizer that does not
    require gradients. This is robust for optical systems where the
    objective may be non-smooth (e.g. spot radius).

    Args:
        system: The optical system to optimize.
        objective: Function that takes an OpticalSystem and returns a
            scalar to minimize.
        params: List of parameter specs (see _set_parameter for format).
        bounds: List of (min, max) tuples, one per parameter (meters).
        seed: Random seed for reproducibility.
        maxiter: Maximum number of generations for the optimizer.
        tol: Relative tolerance for convergence.

    Returns:
        Dict with keys:
            - "params": list of optimal parameter values (meters)
            - "objective": the objective value at the optimum
            - "system": the optimized OpticalSystem
            - "success": bool indicating whether optimization converged

    Raises:
        ValueError: If len(params) != len(bounds).
    """
    if len(params) != len(bounds):
        raise ValueError("params and bounds must have the same length.")

    def cost(x: np.ndarray) -> float:
        modified = system
        for spec, value in zip(params, x):
            modified = _set_parameter(modified, spec, float(value))
        return float(objective(modified))

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

    return {
        "params": [float(v) for v in result.x],
        "objective": float(result.fun),
        "system": optimized,
        "success": result.success,
    }