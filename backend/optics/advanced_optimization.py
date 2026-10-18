"""
Advanced Optimization for Professional Optical Design.

Features:
- Global search (Differential Evolution, Particle Swarm)
- Local refinement (Damped Least Squares, L-BFGS-B)
- Hybrid pipeline (Global → Local)
- Advanced constraints (thickness, air gaps, glass availability)
- Multi-configuration optimization
- Pareto optimization for trade-off exploration
- High-yield optimization (nominal + tolerance sensitivity)

All calculations use the validated optics engine.
"""

import math
from typing import Callable, Optional
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from scipy.optimize import differential_evolution, minimize, least_squares

from .models import OpticalSystem, ThinLens, ThickLens, AnalysisResult
from .analysis import analyze_system, back_focal_length
from .systems import update_component
from .tolerance import tolerance_analysis, compute_yield


# =============================================================================
# Optimization Algorithms
# =============================================================================

class GlobalAlgorithm(str, Enum):
    DIFFERENTIAL_EVOLUTION = "differential_evolution"
    PARTICLE_SWARM = "particle_swarm"

class LocalAlgorithm(str, Enum):
    DLS = "damped_least_squares"  # bounded trust-region (LM-style damping)
    L_BFGS_B = "l_bfgs_b"
    NELDER_MEAD = "nelder_mead"


# =============================================================================
# Constraint Definitions
# =============================================================================

@dataclass
class OptimizationConstraint:
    """A constraint for optimization."""
    # "efl", "bfl", "image_distance", "magnification", "f_number", "rms_spot",
    # "numerical_aperture", "distortion", "center_thickness",
    # "edge_thickness", "air_gap", "total_track"
    type: str
    surface_index: Optional[int] = None  # None for system-wide
    lower: float = -np.inf
    upper: float = np.inf
    target: Optional[float] = None
    weight: float = 1.0
    active: bool = True

@dataclass
class OptimizationConfig:
    """Configuration for advanced optimization."""
    # Algorithm selection
    global_algorithm: GlobalAlgorithm = GlobalAlgorithm.DIFFERENTIAL_EVOLUTION
    local_algorithm: LocalAlgorithm = LocalAlgorithm.DLS

    # Search parameters
    global_maxiter: int = 500
    global_popsize: int = 15
    global_tol: float = 1e-8
    local_maxiter: int = 200
    local_tol: float = 1e-10

    # Hybrid pipeline
    use_hybrid: bool = True  # Run global then local

    # Constraints
    constraints: list[OptimizationConstraint] = field(default_factory=list)

    # Multi-config
    configurations: list[dict] = field(default_factory=list)  # wavelength/field weights

    # High-yield
    optimize_yield: bool = False
    yield_threshold: float = 0.95
    tolerance_specs: dict[str, float] = field(default_factory=dict)
    n_monte_carlo: int = 50

    # Reproducibility
    seed: Optional[int] = 42


# =============================================================================
# Constraint Evaluation
# =============================================================================

def _evaluate_constraints(
    system: OpticalSystem,
    constraints: list[OptimizationConstraint],
) -> tuple[float, dict[str, float]]:
    """
    Total penalty for violated constraints and the violation of each.

    The penalty is weight * violation * 1e6 summed over violated constraints.
    """
    penalty = 0.0
    details: dict[str, float] = {}
    active = [c for c in constraints if c.active]
    if not active:
        return 0.0, details
    analysis = analyze_system(system)
    for constraint in active:
        value = _get_constraint_value(system, analysis, constraint)
        violation = 0.0
        if value < constraint.lower:
            violation = constraint.lower - value
        elif value > constraint.upper:
            violation = value - constraint.upper
        if violation > 0:
            penalty += constraint.weight * violation * 1e6
            details[constraint.type] = violation
    return penalty, details


def _edge_thickness(lens: ThickLens) -> float:
    """Edge thickness of a thick lens at its clear aperture."""
    h = lens.aperture_diameter / 2.0

    def sag(R):
        if not R or not math.isfinite(R) or abs(R) >= 1e9:
            return 0.0
        if abs(R) < h:
            raise ValueError(f"Lens '{lens.id}': radius {R} is smaller than the semi-aperture")
        return R - math.copysign(math.sqrt(R * R - h * h), R)

    return lens.thickness - sag(lens.radius1) + sag(lens.radius2)


def _component_at(system: OpticalSystem, index: Optional[int]):
    if index is None or not 0 <= index < len(system.components):
        raise ValueError(f"Constraint needs a valid component index (got {index})")
    return system.components[index]


def _get_constraint_value(
    system: OpticalSystem,
    analysis: AnalysisResult,
    constraint: OptimizationConstraint,
) -> float:
    """Value of the constrained quantity. Unknown types raise ValueError."""
    t = constraint.type
    if t == "efl":
        return analysis.effective_focal_length
    if t in ("bfl", "back_focal_length"):
        return back_focal_length(system)
    if t == "image_distance":
        return analysis.image_distance
    if t == "magnification":
        return analysis.magnification
    if t == "f_number":
        return analysis.f_number
    if t == "rms_spot":
        return analysis.rms_spot_radius
    if t == "numerical_aperture":
        return analysis.numerical_aperture
    if t == "distortion":
        # real chief-ray distortion at full field, as a fraction
        from .high_order import field_curves
        return field_curves(system, num_fields=2)["distortion"][-1]
    if t == "center_thickness":
        comp = _component_at(system, constraint.surface_index)
        if not isinstance(comp, ThickLens):
            raise ValueError("center_thickness applies to a ThickLens")
        return comp.thickness
    if t == "edge_thickness":
        comp = _component_at(system, constraint.surface_index)
        if not isinstance(comp, ThickLens):
            raise ValueError("edge_thickness applies to a ThickLens")
        return _edge_thickness(comp)
    if t == "air_gap":
        comps = sorted(system.components, key=lambda c: c.position)
        comp = _component_at(system, constraint.surface_index)
        k = comps.index(comp)
        if k + 1 >= len(comps):
            raise ValueError("air_gap needs a following component")
        end = comp.position + (comp.thickness if isinstance(comp, ThickLens) else 0.0)
        return comps[k + 1].position - end
    if t == "total_track":
        first = min(c.position for c in system.components)
        return system.image_plane.position - first
    raise ValueError(f"Unsupported constraint type '{t}'")


# =============================================================================
# Merit function: transverse ray aberrations
# =============================================================================

def ray_aberration_residuals(
    system: OpticalSystem,
    field_fractions: tuple = (0.0, 0.7, 1.0),
    rings: int = 3,
    wavelengths: Optional[list] = None,
) -> np.ndarray:
    """
    Residual vector of transverse ray errors (x and y, meters) relative to
    the chief ray at the image plane, over a hexapolar pupil sampling at
    several fields and wavelengths, each divided by sqrt(number of rays) so
    the sum of squares is the mean-square spot size. Vignetted rays give a
    residual equal to the semi-diagonal of the pupil footprint at the image,
    which pushes the optimiser away from vignetting.
    """
    from . import raytrace as rt
    wavelengths = wavelengths or [system.analysis_settings.wavelength]
    px, py = rt.pupil_grid(rings, "hexapolar")
    res = []
    for wl in wavelengths:
        seq = rt.build_sequence(system, wl)
        fo = rt.first_order(system, seq=seq)
        for ff in field_fractions:
            if ff and not system.object.height:
                continue
            b, _, _ = rt.trace_field_rays(system, 0.0, ff, np.concatenate([[0.0], px]),
                                          np.concatenate([[0.0], py]), seq=seq, fo=fo)
            P = rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)[0]
            if not b.valid[0]:
                raise ValueError("Chief ray failed")
            ex = P[1:, 0] - P[0, 0]
            ey = P[1:, 1] - P[0, 1]
            bad = ~b.valid[1:]
            if bad.any():
                big = 2.0 * fo.entrance_pupil_semi_diameter
                ex = np.where(bad, big, ex)
                ey = np.where(bad, big, ey)
            n = len(ex)
            res.append(ex / math.sqrt(n))
            res.append(ey / math.sqrt(n))
    return np.concatenate(res)


# =============================================================================
# Particle Swarm Optimization
# =============================================================================

def _particle_swarm_optimize(
    objective: Callable[[np.ndarray], float],
    bounds: list[tuple[float, float]],
    maxiter: int = 500,
    popsize: int = 20,
    seed: Optional[int] = None,
) -> dict:
    """
    Simple Particle Swarm Optimization implementation.

    Good for global search in multimodal landscapes.
    """
    rng = np.random.RandomState(seed)
    n_dims = len(bounds)

    # Initialize particles
    positions = np.array([
        [rng.uniform(b[0], b[1]) for b in bounds]
        for _ in range(popsize)
    ])
    velocities = np.zeros_like(positions)

    # Personal best
    personal_best_pos = positions.copy()
    personal_best_val = np.array([objective(p) for p in positions])

    # Global best
    global_best_idx = np.argmin(personal_best_val)
    global_best_pos = positions[global_best_idx].copy()
    global_best_val = personal_best_val[global_best_idx]

    # PSO parameters
    w = 0.7   # inertia
    c1 = 1.5  # cognitive
    c2 = 1.5  # social

    history = []

    for iteration in range(maxiter):
        for i in range(popsize):
            r1, r2 = rng.rand(n_dims), rng.rand(n_dims)

            # Update velocity
            velocities[i] = (
                w * velocities[i]
                + c1 * r1 * (personal_best_pos[i] - positions[i])
                + c2 * r2 * (global_best_pos - positions[i])
            )

            # Update position
            positions[i] += velocities[i]

            # Enforce bounds
            for d in range(n_dims):
                positions[i][d] = np.clip(positions[i][d], bounds[d][0], bounds[d][1])

            # Evaluate
            val = objective(positions[i])

            # Update personal best
            if val < personal_best_val[i]:
                personal_best_val[i] = val
                personal_best_pos[i] = positions[i].copy()

            # Update global best
            if val < global_best_val:
                global_best_val = val
                global_best_pos = positions[i].copy()

        history.append(global_best_val)

    return {
        "params": global_best_pos.tolist(),
        "objective": global_best_val,
        "success": True,
        "n_iterations": maxiter,
        "history": history,
    }


# =============================================================================
# Damped Least Squares (Levenberg-Marquardt)
# =============================================================================

def _damped_least_squares(
    objective: Callable[[np.ndarray], object],
    x0: np.ndarray,
    bounds: list[tuple[float, float]],
    maxiter: int = 200,
    tol: float = 1e-10,
) -> dict:
    """
    Damped least squares on a residual vector.

    ``objective`` returns either a residual vector (the usual optical merit
    function, e.g. :func:`ray_aberration_residuals`) or a scalar merit
    value f >= 0, used as the single residual sqrt(f). Bounds are honoured
    with SciPy's trust-region-reflective solver, whose Levenberg-Marquardt
    style damping is the bounded counterpart of classic DLS.
    """
    def residual(x):
        r = objective(x)
        r = np.atleast_1d(np.asarray(r, dtype=float))
        if r.size == 1:
            return np.sqrt(np.maximum(r, 0.0))
        return r

    result = least_squares(
        residual, x0,
        bounds=([b[0] for b in bounds], [b[1] for b in bounds]),
        method="trf", max_nfev=maxiter, ftol=tol, xtol=tol, gtol=tol,
    )
    return {
        "params": result.x.tolist(),
        "objective": float(np.sum(result.fun ** 2)),
        "success": bool(result.success),
        "n_iterations": int(result.nfev),
        "message": result.message,
    }


# =============================================================================
# Hybrid Optimization Pipeline
# =============================================================================

def hybrid_optimize(
    system: OpticalSystem,
    objective: Callable[[OpticalSystem], float],
    params: list[dict],
    bounds: list[tuple[float, float]],
    config: Optional[OptimizationConfig] = None,
) -> dict:
    """
    Hybrid optimization: global search followed by local refinement.

    This is the professional standard workflow:
    1. Global search to find promising region
    2. Local refinement for precise optimum

    Args:
        system: Base optical system
        objective: Function to minimize (takes system, returns scalar)
        params: Parameter specifications [{"component_id": "L1", "field": "focal_length"}, ...]
        bounds: [(min, max), ...] for each parameter
        config: Optimization configuration

    Returns:
        Dict with optimization results
    """
    if config is None:
        config = OptimizationConfig()

    rng = np.random.RandomState(config.seed)

    def build(x):
        modified = system
        for spec, value in zip(params, x):
            modified = update_component(modified, spec["component_id"], **{spec["field"]: float(value)})
        return modified

    def residuals(x: np.ndarray):
        """Objective as residuals (vector merit functions stay vectors);
        constraint penalties are appended as one more residual."""
        try:
            modified = build(x)
            r = np.atleast_1d(np.asarray(objective(modified), dtype=float))
            penalty, _ = _evaluate_constraints(modified, config.constraints)
        except ValueError:
            return np.array([1e6])
        if r.size == 1:
            return np.array([math.sqrt(max(float(r[0]), 0.0) + penalty)])
        return np.concatenate([r, [math.sqrt(penalty)]])

    def wrapped_objective(x: np.ndarray) -> float:
        return float(np.sum(residuals(x) ** 2))

    # Phase 1: Global search
    if config.global_algorithm == GlobalAlgorithm.DIFFERENTIAL_EVOLUTION:
        global_result = differential_evolution(
            wrapped_objective,
            bounds=bounds,
            maxiter=config.global_maxiter,
            popsize=config.global_popsize,
            tol=config.global_tol,
            seed=rng,
            polish=False,  # We do our own polishing
        )
        x_global = global_result.x
        global_iters, global_ok = int(global_result.nit), bool(global_result.success)
    elif config.global_algorithm == GlobalAlgorithm.PARTICLE_SWARM:
        global_result = _particle_swarm_optimize(
            wrapped_objective,
            bounds=bounds,
            maxiter=config.global_maxiter,
            popsize=config.global_popsize * 2,
            seed=config.seed,
        )
        x_global = np.array(global_result["params"])
        global_iters, global_ok = int(global_result["n_iterations"]), True
    else:
        raise ValueError(f"Unknown global algorithm: {config.global_algorithm}")
    local_iters, local_ok = 0, True

    # Phase 2: Local refinement
    if config.use_hybrid:
        if config.local_algorithm == LocalAlgorithm.DLS:
            local_result = _damped_least_squares(
                residuals,
                x_global,
                bounds=bounds,
                maxiter=config.local_maxiter,
                tol=config.local_tol,
            )
            x_optimal = np.array(local_result["params"])
            final_objective = local_result["objective"]
            local_iters, local_ok = local_result["n_iterations"], local_result["success"]
        elif config.local_algorithm == LocalAlgorithm.L_BFGS_B:
            local_result = minimize(
                wrapped_objective,
                x_global,
                method='L-BFGS-B',
                bounds=bounds,
                options={'maxiter': config.local_maxiter, 'ftol': config.local_tol},
            )
            x_optimal = local_result.x
            final_objective = local_result.fun
            local_iters, local_ok = int(local_result.nit), bool(local_result.success)
        else:
            x_optimal = x_global
            final_objective = wrapped_objective(x_global)
    else:
        x_optimal = x_global
        final_objective = wrapped_objective(x_global)

    if wrapped_objective(x_optimal) > wrapped_objective(x_global):
        x_optimal = np.asarray(x_global)   # the local step must not make things worse
        final_objective = wrapped_objective(x_global)
    final_system = build(x_optimal)
    _, violations = _evaluate_constraints(final_system, config.constraints)
    return {
        "system": final_system,
        "params": np.asarray(x_optimal).tolist(),
        "objective": float(final_objective),
        "global_objective": float(wrapped_objective(x_global)),
        "n_global_iterations": global_iters,
        "n_local_iterations": local_iters,
        "constraint_violations": violations,
        "success": bool(global_ok and local_ok and not violations),
    }


# =============================================================================
# High-Yield Optimization
# =============================================================================

def high_yield_optimize(
    system: OpticalSystem,
    objective: Callable[[OpticalSystem], float],
    params: list[dict],
    bounds: list[tuple[float, float]],
    tolerance_specs: dict[str, float],
    yield_threshold: float = 0.95,
    n_monte_carlo: int = 50,
    config: Optional[OptimizationConfig] = None,
    spec_factor: float = 1.5,
) -> dict:
    """
    Optimize for as-built performance considering tolerances.

    A Monte Carlo trial passes when its metric is within ``spec_factor``
    times the nominal value; designs whose pass rate is below
    ``yield_threshold`` are penalised.

    This optimizes both nominal performance AND tolerance sensitivity.
    The merit function includes a penalty for low yield.

    Args:
        system: Base optical system
        objective: Nominal objective function
        params: Parameter specifications
        bounds: Parameter bounds
        tolerance_specs: Tolerance specifications for Monte Carlo
        yield_threshold: Minimum acceptable yield
        n_monte_carlo: Number of Monte Carlo samples for yield estimation
        config: Optimization configuration

    Returns:
        Dict with optimization results including yield statistics
    """
    if config is None:
        config = OptimizationConfig()
    if len(params) != len(bounds):
        raise ValueError("params and bounds must have the same length.")
    # Validate parameters up front: errors inside differential_evolution are
    # re-wrapped by SciPy into an unhelpful RuntimeError.
    for spec, (lo, hi) in zip(params, bounds):
        if not lo < hi:
            raise ValueError(f"Empty bounds [{lo}, {hi}] for {spec}")
        update_component(system, spec["component_id"], **{spec["field"]: 0.5 * (lo + hi)})

    def yield_aware_objective(x: np.ndarray) -> float:
        """Objective that penalizes low yield."""
        modified = system
        for spec, value in zip(params, x):
            modified = update_component(modified, spec["component_id"], **{spec["field"]: value})

        # Nominal performance
        nominal = float(objective(modified))

        # Constraint penalty
        penalty, _ = _evaluate_constraints(modified, config.constraints)

        # Yield estimation (expensive - only do periodically)
        yield_penalty = 0.0
        if config.optimize_yield and tolerance_specs:
            tol_result = tolerance_analysis(
                modified,
                metric=objective,
                tolerances=tolerance_specs,
                trials=n_monte_carlo,
                seed=config.seed or 42,
            )

            if tol_result["trend"]:
                # Compute yield against a threshold
                spec_limit = nominal * spec_factor
                yield_stats = compute_yield(tol_result["trend"], upper_limit=spec_limit)

                if yield_stats["yield"] < yield_threshold:
                    yield_penalty = 1e3 * (yield_threshold - yield_stats["yield"])

        return nominal + penalty + yield_penalty

    rng = np.random.RandomState(config.seed)

    # Run hybrid optimization with yield-aware objective
    global_result = differential_evolution(
        yield_aware_objective,
        bounds=bounds,
        maxiter=config.global_maxiter,
        popsize=config.global_popsize,
        seed=rng,
        polish=False,
    )

    if config.use_hybrid:
        local_result = _damped_least_squares(
            yield_aware_objective,
            global_result.x,
            bounds=bounds,
            maxiter=config.local_maxiter,
        )
        x_optimal = np.array(local_result["params"])
    else:
        x_optimal = global_result.x

    # Build final system
    final_system = system
    for spec, value in zip(params, x_optimal):
        final_system = update_component(final_system, spec["component_id"], **{spec["field"]: value})

    # Final yield analysis
    final_yield = None
    if tolerance_specs:
        tol_result = tolerance_analysis(
            final_system,
            metric=objective,
            tolerances=tolerance_specs,
            trials=n_monte_carlo * 2,
            seed=config.seed or 42,
        )
        if tol_result["trend"]:
            spec_limit = float(objective(final_system)) * spec_factor
            final_yield = compute_yield(tol_result["trend"], upper_limit=spec_limit)

    return {
        "system": final_system,
        "params": np.asarray(x_optimal).tolist(),
        "objective": float(yield_aware_objective(x_optimal)),
        "yield_stats": final_yield,
        "success": bool(global_result.success),
    }


# =============================================================================
# Pareto Optimization
# =============================================================================

def pareto_optimize(
    system: OpticalSystem,
    objectives: list[Callable[[OpticalSystem], float]],
    params: list[dict],
    bounds: list[tuple[float, float]],
    n_points: int = 20,
    config: Optional[OptimizationConfig] = None,
) -> dict:
    """
    Multi-objective optimization exploring the Pareto front of the first two
    objectives by the weighted-sum method (it reaches only the convex part of
    the front).

    Finds trade-off curve between competing objectives.
    Useful for exploring MTF vs. size vs. cost trade-offs.

    Args:
        system: Base optical system
        objectives: List of objective functions to minimize
        params: Parameter specifications
        bounds: Parameter bounds
        n_points: Number of Pareto front points to compute
        config: Optimization configuration

    Returns:
        Dict with Pareto front points and corresponding systems
    """
    if config is None:
        config = OptimizationConfig()

    pareto_points = []

    # Generate Pareto front by varying weights
    for i in range(n_points):
        w1 = i / (n_points - 1) if n_points > 1 else 0.5
        w2 = 1 - w1

        def weighted_objective(sys: OpticalSystem) -> float:
            return w1 * objectives[0](sys) + w2 * objectives[1](sys) if len(objectives) >= 2 else objectives[0](sys)

        result = hybrid_optimize(
            system,
            weighted_objective,
            params,
            bounds,
            config=config,
        )

        obj_values = [obj(result["system"]) for obj in objectives]

        pareto_points.append({
            "weights": [w1, w2],
            "objectives": obj_values,
            "system": result["system"],
            "params": result["params"],
        })

    # Keep only non-dominated points (weighted sums can return dominated or
    # duplicate solutions).
    front = []
    for p in pareto_points:
        dominated = any(
            all(a <= b for a, b in zip(q["objectives"], p["objectives"]))
            and any(a < b for a, b in zip(q["objectives"], p["objectives"]))
            for q in pareto_points)
        duplicate = any(np.allclose(q["objectives"], p["objectives"]) for q in front)
        if not dominated and not duplicate:
            front.append(p)
    front.sort(key=lambda p: p["objectives"][0])
    return {
        "pareto_front": front,
        "n_points": len(front),
        "n_evaluated": len(pareto_points),
    }
