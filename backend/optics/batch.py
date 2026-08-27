"""
Batch analysis (Phase 8).

Batch analysis runs a full analysis over many optical systems, either
provided directly or generated from a parameter sweep. This is useful
for tolerance studies, design-space exploration, and generating tables
for engineering reports.

All calculations are delegated to the validated optics engine
(analysis.py). This module only orchestrates the loop over systems.

All values are in SI base units (meters, radians).
"""

from typing import Optional, Union

from .models import OpticalSystem, AnalysisResult
from .analysis import analyze_system
from .optimization import parameter_sweep


def batch_analyze_systems(systems: list[OpticalSystem]) -> list[dict]:
    """
    Analyze a list of optical systems and return per-system summaries.

    Args:
        systems: List of optical systems.

    Returns:
        List of dicts, one per system, with:
            - "index": position in the input list
            - "analysis": the full AnalysisResult
            - "summary": a compact dict of key metrics
    """
    results: list[dict] = []
    for i, system in enumerate(systems):
        analysis = analyze_system(system)
        results.append({
            "index": i,
            "analysis": analysis,
            "summary": {
                "magnification": analysis.magnification,
                "efl_mm": analysis.effective_focal_length * 1000.0,
                "f_number": analysis.f_number,
                "numerical_aperture": analysis.numerical_aperture,
                "rms_spot_um": analysis.rms_spot_radius * 1e6,
                "image_distance_mm": analysis.image_distance * 1000.0,
            },
        })
    return results


def batch_sweep_and_analyze(
    system: OpticalSystem,
    param_spec: dict,
    values: list[float],
    num_rays: Optional[int] = None,
    aperture_fraction: Optional[float] = None,
) -> list[dict]:
    """
    Sweep a single parameter and analyze each resulting system.

    This is a convenience wrapper that produces the same shape of results
    as batch_analyze_systems but drives the systems via parameter_sweep.

    Args:
        system: The base optical system.
        param_spec: Dict describing which parameter to sweep.
        values: List of parameter values (meters).
        num_rays: Optional ray count override.
        aperture_fraction: Optional aperture fraction.

    Returns:
        List of dicts (one per value) with "value", "analysis", "summary".
    """
    swept = parameter_sweep(
        system, param_spec, values,
        num_rays=num_rays, aperture_fraction=aperture_fraction,
    )
    out: list[dict] = []
    for value, analysis in swept:
        out.append({
            "value": value,
            "analysis": analysis,
            "summary": {
                "magnification": analysis.magnification,
                "efl_mm": analysis.effective_focal_length * 1000.0,
                "f_number": analysis.f_number,
                "rms_spot_um": analysis.rms_spot_radius * 1e6,
            },
        })
    return out