"""
Global search optimization.

Combines global search with local refinement for robust optimization.
"""

from typing import Optional, Callable
from dataclasses import dataclass
import numpy as np
from scipy.optimize import differential_evolution, minimize


@dataclass
class OptimizationResult:
    """Result of optimization."""
    params: list[float]
    objective: float
    success: bool
    n_iterations: int
    n_evaluations: int
    history: Optional[list[float]] = None


def global_search(
    objective: Callable[[np.ndarray], float],
    bounds: list[tuple[float, float]],
    method: str = 'auto',
    maxiter: int = 1000,
    seed: Optional[int] = None,
    **kwargs,
) -> OptimizationResult:
    """
    Global optimization with automatic method selection.
    
    Args:
        objective: Function to minimize
        bounds: List of (min, max) for each parameter
        method: 'auto', 'de', 'pso', 'sa', 'ga'
        maxiter: Maximum iterations
        seed: Random seed
        
    Returns:
        OptimizationResult
    """
    if method == 'auto':
        # Choose based on dimensionality
        n_params = len(bounds)
        if n_params <= 5:
            method = 'de'
        else:
            method = 'pso'
    
    rng = np.random.RandomState(seed)
    
    if method == 'de':
        result = differential_evolution(
            objective,
            bounds=bounds,
            maxiter=maxiter,
            seed=rng,
            polish=False,
            **kwargs
        )
        return OptimizationResult(
            params=result.x.tolist(),
            objective=result.fun,
            success=result.success,
            n_iterations=result.nit,
            n_evaluations=result.nfev
        )
    
    elif method == 'pso':
        return _pso_optimize(objective, bounds, maxiter, rng, **kwargs)
    
    elif method == 'sa':
        return _sa_optimize(objective, bounds, maxiter, rng, **kwargs)
    
    else:
        raise ValueError(f"Unknown method: {method}")


def hybrid_optimize(
    objective: Callable[[np.ndarray], float],
    bounds: list[tuple[float, float]],
    global_method: str = 'auto',
    maxiter_global: int = 500,
    maxiter_local: int = 500,
    seed: Optional[int] = None,
) -> OptimizationResult:
    """
    Hybrid optimization: global search + local refinement.
    
    Args:
        objective: Function to minimize
        bounds: Parameter bounds
        global_method: Global search method
        maxiter_global: Max global iterations
        maxiter_local: Max local iterations
        seed: Random seed
        
    Returns:
        OptimizationResult
    """
    # Phase 1: Global search
    global_result = global_search(
        objective, bounds, method=global_method,
        maxiter=maxiter_global, seed=seed
    )
    
    # Phase 2: Local refinement
    local_result = minimize(
        objective,
        x0=np.array(global_result.params),
        method='L-BFGS-B',
        bounds=bounds,
        options={'maxiter': maxiter_local}
    )
    
    # Return best result
    if local_result.fun < global_result.objective:
        return OptimizationResult(
            params=local_result.x.tolist(),
            objective=local_result.fun,
            success=local_result.success,
            n_iterations=local_result.nit,
            n_evaluations=local_result.nfev
        )
    else:
        return global_result


def _pso_optimize(objective, bounds, maxiter, rng, n_particles=30, **kwargs):
    """Particle Swarm Optimization."""
    n_params = len(bounds)
    
    # Initialize particles
    positions = np.array([
        [rng.uniform(b[0], b[1]) for b in bounds]
        for _ in range(n_particles)
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
    w = 0.7   # Inertia
    c1 = 1.5  # Cognitive
    c2 = 1.5  # Social
    
    history = [global_best_val]
    
    for iteration in range(maxiter):
        for i in range(n_particles):
            r1, r2 = rng.rand(n_params), rng.rand(n_params)
            
            # Update velocity
            velocities[i] = (
                w * velocities[i]
                + c1 * r1 * (personal_best_pos[i] - positions[i])
                + c2 * r2 * (global_best_pos - positions[i])
            )
            
            # Update position
            positions[i] += velocities[i]
            
            # Enforce bounds
            for j, (lo, hi) in enumerate(bounds):
                positions[i][j] = np.clip(positions[i][j], lo, hi)
            
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
    
    return OptimizationResult(
        params=global_best_pos.tolist(),
        objective=global_best_val,
        success=True,
        n_iterations=maxiter,
        n_evaluations=maxiter * n_particles,
        history=history
    )


def _sa_optimize(objective, bounds, maxiter, rng, **kwargs):
    """Simulated Annealing."""
    n_params = len(bounds)
    
    # Initial point
    current = np.array([rng.uniform(b[0], b[1]) for b in bounds])
    current_val = objective(current)
    
    best = current.copy()
    best_val = current_val
    
    # Temperature schedule
    T_initial = 1.0
    T_final = 1e-6
    cooling_rate = (T_final / T_initial) ** (1.0 / maxiter)
    T = T_initial
    
    for iteration in range(maxiter):
        # Generate neighbor
        neighbor = current + rng.randn(n_params) * T * 0.1
        
        # Enforce bounds
        for j, (lo, hi) in enumerate(bounds):
            neighbor[j] = np.clip(neighbor[j], lo, hi)
        
        # Evaluate
        neighbor_val = objective(neighbor)
        
        # Accept or reject
        delta = neighbor_val - current_val
        if delta < 0 or rng.rand() < np.exp(-delta / T):
            current = neighbor
            current_val = neighbor_val
            
            if current_val < best_val:
                best = current.copy()
                best_val = current_val
        
        # Cool down
        T *= cooling_rate
    
    return OptimizationResult(
        params=best.tolist(),
        objective=best_val,
        success=True,
        n_iterations=maxiter,
        n_evaluations=maxiter
    )
