"""
Tests for the optical optimization module.

These tests verify that parameter sweeps and numerical optimization
produce correct results for known optical systems.
"""

import math
import pytest
from optics.models import (
    OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings,
)
from optics.analysis import effective_focal_length, system_magnification
from optics.optimization import (
    parameter_sweep, optimize_system,
    minimize_rms_spot, target_magnification, target_efl,
)


# ---------------------------------------------------------------------------
# Helper to create test systems
# ---------------------------------------------------------------------------

def make_single_lens_system(
    f: float = 0.050,
    aperture: float = 0.025,
    obj_pos: float = 0.0,
    obj_height: float = 0.010,
    lens_pos: float = 0.100,
    image_pos: float = 0.200,
) -> OpticalSystem:
    """Create a simple single-lens system for testing."""
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1",
                position=lens_pos,
                focal_length=f,
                aperture_diameter=aperture,
            ),
        ],
        object=Object(position=obj_pos, height=obj_height),
        image_plane=ImagePlane(position=image_pos),
        analysis_settings=AnalysisSettings(num_rays=11),
    )


# ---------------------------------------------------------------------------
# Parameter Sweep Tests
# ---------------------------------------------------------------------------

def test_parameter_sweep_lens_position():
    """Sweeping lens position should change the image distance."""
    system = make_single_lens_system()

    positions = [0.08, 0.10, 0.12]
    results = parameter_sweep(system, {"component_id": "lens_1", "field": "position"}, positions)

    assert len(results) == 3
    # Results should be in the same order as the input values
    assert [r[0] for r in results] == positions

    # Image distance should differ across the sweep
    image_dists = [r[1].image_distance for r in results]
    assert len(set(round(d, 6) for d in image_dists)) == 3


def test_parameter_sweep_focal_length():
    """Sweeping focal length should change the effective focal length."""
    system = make_single_lens_system()

    focal_lengths = [0.040, 0.050, 0.060]
    results = parameter_sweep(system, {"component_id": "lens_1", "field": "focal_length"}, focal_lengths)

    assert len(results) == 3
    # For a single lens, EFL equals the focal length
    for value, result in results:
        assert abs(result.effective_focal_length - value) < 1e-9


def test_parameter_sweep_object_position():
    """Sweeping object position should change the magnification."""
    system = make_single_lens_system()

    obj_positions = [-0.05, -0.10, -0.15]
    results = parameter_sweep(system, {"field": "object.position"}, obj_positions)

    assert len(results) == 3
    # Magnification should differ across the sweep
    mags = [r[1].magnification for r in results]
    assert len(set(round(m, 6) for m in mags)) == 3


def test_parameter_sweep_invalid_spec():
    """An invalid parameter spec should raise ValueError."""
    system = make_single_lens_system()
    with pytest.raises(ValueError):
        parameter_sweep(system, {"field": "bogus"}, [0.1])


# ---------------------------------------------------------------------------
# Objective Function Tests
# ---------------------------------------------------------------------------

def test_minimize_rms_spot_returns_positive():
    """RMS spot radius should be a non-negative scalar."""
    system = make_single_lens_system()
    value = minimize_rms_spot(system)
    assert value >= 0
    assert isinstance(value, float)


def test_target_magnification_zero_error_at_target():
    """target_magnification should be ~0 when the system already matches."""
    # Single lens: obj at 0, lens at 0.1, f=0.05 => s=-0.1, s'=0.1, m=-1
    system = make_single_lens_system()
    error = target_magnification(system, -1.0)
    assert abs(error) < 1e-6


def test_target_efl_zero_error_at_target():
    """target_efl should be ~0 when the system already matches."""
    system = make_single_lens_system(f=0.050)
    error = target_efl(system, 0.050)
    assert abs(error) < 1e-9


def test_target_efl_afocal_penalty():
    """An afocal system should return a large penalty."""
    # Two lenses with equal and opposite focal lengths, zero separation
    system = OpticalSystem(
        components=[
            ThinLens(id="l1", position=0.1, focal_length=0.05, aperture_diameter=0.025),
            ThinLens(id="l2", position=0.1, focal_length=-0.05, aperture_diameter=0.025),
        ],
        object=Object(position=0.0, height=0.01),
        image_plane=ImagePlane(position=0.2),
        analysis_settings=AnalysisSettings(num_rays=11),
    )
    error = target_efl(system, 0.05)
    assert error > 1e5


# ---------------------------------------------------------------------------
# Numerical Optimization Tests
# ---------------------------------------------------------------------------

def test_optimize_efl_single_lens():
    """Optimizing focal length should find the target EFL."""
    system = make_single_lens_system(f=0.050)
    target = 0.075

    result = optimize_system(
        system,
        lambda s: target_efl(s, target),
        params=[{"component_id": "lens_1", "field": "focal_length"}],
        bounds=[(0.01, 0.20)],
        seed=42,
        maxiter=200,
    )

    assert result["success"] is True
    # The optimal focal length should be close to the target
    assert abs(result["params"][0] - target) < 1e-3
    # The objective should be near zero
    assert result["objective"] < 1e-3


def test_optimize_magnification():
    """Optimizing focal length should achieve a target magnification."""
    system = make_single_lens_system(f=0.050)
    target_mag = -2.0

    result = optimize_system(
        system,
        lambda s: target_magnification(s, target_mag),
        params=[{"component_id": "lens_1", "field": "focal_length"}],
        bounds=[(0.01, 0.20)],
        seed=42,
        maxiter=200,
    )

    assert result["success"] is True
    # Verify the optimized system actually achieves the target magnification
    optimized_mag = system_magnification(result["system"])
    assert abs(optimized_mag - target_mag) < 1e-3


def test_optimize_rms_spot():
    """Optimizing lens position should reduce the RMS spot radius."""
    system = make_single_lens_system()

    result = optimize_system(
        system,
        minimize_rms_spot,
        params=[{"component_id": "lens_1", "field": "position"}],
        bounds=[(0.05, 0.15)],
        seed=42,
        maxiter=200,
    )

    assert result["success"] is True
    # The optimized system should have a small spot radius
    assert result["objective"] < 1e-4


def test_optimize_mismatched_params_bounds():
    """Mismatched params and bounds should raise ValueError."""
    system = make_single_lens_system()
    with pytest.raises(ValueError):
        optimize_system(
            system,
            minimize_rms_spot,
            params=[{"component_id": "lens_1", "field": "position"}],
            bounds=[(0.05, 0.15), (0.05, 0.15)],
        )