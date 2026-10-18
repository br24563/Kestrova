"""
GRIN ray tracing.

Traces rays through gradient index media using numerical integration.
"""

from typing import Optional, Tuple, List
from dataclasses import dataclass, field
import numpy as np
from .profile import GRINProfile, RadialGRIN


@dataclass
class GRINRay:
    """Ray state in GRIN media."""
    position: np.ndarray  # [x, y, z]
    direction: np.ndarray  # [dx, dy, dz] (unit vector)
    optical_path: float = 0.0
    intensity: float = 1.0
    wavelength: float = 550e-9


def trace_grin(
    ray: GRINRay,
    profile: GRINProfile,
    length: float,
    step_size: float = 1e-4,
    method: str = 'rk4',
) -> List[GRINRay]:
    """
    Trace ray through GRIN media.

    Args:
        ray: Initial ray state
        profile: GRIN profile
        length: Path length to integrate (same length unit as the profile)
        step_size: Integration step (same unit)
        method: Integration method ('euler' or 'rk4')

    Returns:
        List of ray states along path
    """
    path = [ray]
    current = ray
    num_steps = int(length / step_size)

    for _ in range(num_steps):
        if method == 'rk4':
            current = _rk4_step(current, profile, step_size)
        else:
            current = _euler_step(current, profile, step_size)
        path.append(current)

    return path


def _euler_step(ray: GRINRay, profile: GRINProfile, ds: float) -> GRINRay:
    """Single Euler integration step."""
    pos = ray.position
    dir = ray.direction

    # Calculate index and gradient at current position
    n = profile.index(pos[0], pos[1], pos[2])
    grad = profile.gradient(pos[0], pos[1], pos[2])

    # Ray equation d/ds(n dr/ds) = grad(n) with |dr/ds| = 1 gives
    # d(dr/ds)/ds = (grad(n) - (grad(n) . dr/ds) dr/ds) / n
    grad_dot_dir = np.dot(grad, dir)
    ddir_ds = (grad - dir * grad_dot_dir) / n

    # Update position and direction
    new_pos = pos + dir * ds
    new_dir = dir + ddir_ds * ds
    new_dir = new_dir / np.linalg.norm(new_dir)  # Normalize

    return GRINRay(
        position=new_pos,
        direction=new_dir,
        optical_path=ray.optical_path + n * ds,
        intensity=ray.intensity,
        wavelength=ray.wavelength
    )


def _rk4_step(ray: GRINRay, profile: GRINProfile, ds: float) -> GRINRay:
    """Single 4th-order Runge-Kutta integration step."""
    def derivatives(state):
        pos = state[:3]
        dir = state[3:6]

        n = profile.index(pos[0], pos[1], pos[2])
        grad = profile.gradient(pos[0], pos[1], pos[2])

        # d(pos)/ds = dir;  d(dir)/ds = (grad - dir (grad.dir)) / n
        grad_dot_dir = np.dot(grad, dir)
        ddir = (grad - dir * grad_dot_dir) / n

        return np.concatenate([dir, ddir])

    # Current state
    state = np.concatenate([ray.position, ray.direction])

    # RK4 coefficients
    k1 = derivatives(state)
    k2 = derivatives(state + ds/2 * k1)
    k3 = derivatives(state + ds/2 * k2)
    k4 = derivatives(state + ds * k3)

    # Update state
    new_state = state + ds/6 * (k1 + 2*k2 + 2*k3 + k4)

    new_pos = new_state[:3]
    new_dir = new_state[3:6]
    new_dir = new_dir / np.linalg.norm(new_dir)  # Normalize

    # Optical path by Simpson's rule over the step
    p0, p2 = state[:3], new_pos
    p1 = state[:3] + ds / 2 * state[3:6]
    n_avg = (profile.index(*p0) + 4 * profile.index(*p1) + profile.index(*p2)) / 6.0

    return GRINRay(
        position=new_pos,
        direction=new_dir,
        optical_path=ray.optical_path + n_avg * ds,
        intensity=ray.intensity,
        wavelength=ray.wavelength
    )


def grin_lens_focus(
    profile: RadialGRIN,
    length: float,
    r0: float = 0.0,
    theta0: float = 0.01,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate focus of GRIN lens.

    Args:
        profile: Radial GRIN profile
        length: Lens length (m)
        r0: Initial ray height (m)
        theta0: Initial ray angle inside the medium (rad)

    Returns:
        (z_positions, r_positions)
    """
    ray = GRINRay(
        position=np.array([r0, 0.0, 0.0]),
        direction=np.array([np.sin(theta0), 0.0, np.cos(theta0)])
    )

    path = trace_grin(ray, profile, length, step_size=length/1000)

    z = [r.position[2] for r in path]
    r = [r.position[0] for r in path]

    return np.array(z), np.array(r)
