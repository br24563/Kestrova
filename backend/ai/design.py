"""
Design-from-requirements (Phase 7).

This module translates a set of design requirements into optical-system
candidate designs. Critically, it does NOT perform optical calculations
itself: it delegates all mathematics to the validated optics engine
(optimization, analysis). The AI or rule-based parser only supplies the
parsed requirements; this module orchestrates the search over design
space.

A design request such as

    "Design a 5x imaging system at 532 nm with a 10 mm aperture and
     minimize RMS spot size."

becomes a DesignCommand with magnification=5, wavelength=532nm,
aperture_diameter=10mm, objective="rms_spot". This module then:

    1. Builds a starting two-lens candidate system configured for the
       required wavelength and aperture.
    2. Optimizes lens focal lengths and positions using the SciPy-based
       multi-objective optimizer to drive toward the target magnification
       while minimizing the RMS spot radius, subject to the aperture
       requirement.
    3. Returns one or more candidate designs with full analysis.

The candidates are first-order layouts of two ideal thin lenses (see
optics.raytrace): ideal lenses have no monochromatic aberrations, so the
RMS-spot objective only brings the image into focus on the fixed 300 mm
image plane, and the result says nothing about real-lens aberrations. Turn
each thin lens into real elements (e.g. optics.standards.PartDefinition)
before judging image quality.

All length values are in SI base units (meters, radians).
"""

import math
from typing import Optional

from optics.models import (
    OpticalSystem,
    ThinLens,
    Object,
    ImagePlane,
    AnalysisSettings,
)
from optics.systems import validate_system, sort_components
from optics.analysis import analyze_system
from optics.optimization import (
    multi_objective_optimize,
    minimize_rms_spot,
    target_magnification,
)

# Default wavelength when the request does not specify one (green).
_DEFAULT_WAVELENGTH = 550e-9
# Default object height for building candidate designs.
_DEFAULT_OBJECT_HEIGHT = 0.010


# ---------------------------------------------------------------------------
# Building the starting system
# ---------------------------------------------------------------------------


def _build_starting_system(
    wavelength: float, aperture_diameter: Optional[float]
) -> OpticalSystem:
    """
    Build a starting two-lens relay system for the given requirements.

    Lens 1 at 100mm and Lens 2 at 200mm, each with the required aperture
    (or a 25mm default). The object is placed at 0mm. The image plane is
    positioned at a nominal 300mm.
    """
    ap = aperture_diameter if aperture_diameter and aperture_diameter > 0 else 0.025

    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1",
                position=0.100,
                focal_length=0.050,
                aperture_diameter=ap,
                material="N-BK7",
            ),
            ThinLens(
                id="lens_2",
                position=0.200,
                focal_length=0.050,
                aperture_diameter=ap,
                material="N-BK7",
            ),
        ],
        wavelengths=[wavelength],
        object=Object(position=0.0, height=_DEFAULT_OBJECT_HEIGHT, orientation=0.0),
        image_plane=ImagePlane(position=0.300),
        analysis_settings=AnalysisSettings(
            num_rays=21,
            ray_types=["chief", "marginal", "fill"],
            aperture_fraction=1.0,
            wavelength=wavelength,
        ),
    )


def _design_objectives(magnification: Optional[float], objective: str):
    """
    Build the objective list and (optionally) weights for the design.

    Returns (objectives, weights):
        objectives: list of Callable[[OpticalSystem], float]
        weights: list of floats
    """
    objectives = [minimize_rms_spot]
    weights = [1.0]

    if magnification is not None and abs(magnification) > 1e-9:
        objectives.append(lambda s, m=magnification: target_magnification(s, m))
        weights.append(1.0)

    return objectives, weights


# ---------------------------------------------------------------------------
# Design search
# ---------------------------------------------------------------------------


def design_from_requirements(
    magnification: Optional[float] = None,
    wavelength: Optional[float] = None,
    aperture_diameter: Optional[float] = None,
    objective: str = "rms_spot",
    num_candidates: int = 1,
    seed: Optional[int] = 42,
    maxiter: int = 60,
) -> dict:
    """
    Generate candidate optical-system designs from parsed requirements.

    The search is carried out entirely by the validated optics engine;
    no optical math lives in this module.

    Args:
        magnification: Optional target magnification (signed, dimensionless).
        wavelength: Operating wavelength (meters). Defaults to 550 nm.
        aperture_diameter: Required aperture diameter (meters).
        objective: Primary objective ("rms_spot" or "magnification").
        num_candidates: Number of candidate designs (1..5).
        seed: Random seed for the optimizer (reproducible).
        maxiter: Max generations for the optimizer.

    Returns:
        Dict with:
            - "candidates": list of dicts, each: {"index", "system",
              "analysis", "warnings", "magnification", "efl_mm",
              "rms_spot_um", "f_number"}
            - "requirements": the parsed requirements used
    """
    wl = wavelength if wavelength and wavelength > 0 else _DEFAULT_WAVELENGTH
    base_system = _build_starting_system(wl, aperture_diameter)

    objectives, weights = _design_objectives(magnification, objective)

    params = [
        {"component_id": "lens_1", "field": "focal_length"},
        {"component_id": "lens_1", "field": "position"},
        {"component_id": "lens_2", "field": "focal_length"},
        {"component_id": "lens_2", "field": "position"},
    ]
    bounds = [
        (0.010, 0.200),  # lens_1 focal length
        (0.050, 0.150),  # lens_1 position
        (0.010, 0.200),  # lens_2 focal length
        (0.150, 0.280),  # lens_2 position
    ]

    # Constraint: keep the achieved magnification near the target (so the
    # optimizer cannot drift away from the design goal).
    constraints = []
    if magnification is not None and abs(magnification) > 1e-9:
        tol = max(0.05, abs(magnification) * 0.25)
        constraints.append(
            {
                "type": "range",
                "field": "magnification",
                "min": magnification - tol,
                "max": magnification + tol,
            }
        )

    try:
        result = multi_objective_optimize(
            base_system,
            objectives=objectives,
            weights=weights,
            params=params,
            bounds=bounds,
            seed=seed,
            maxiter=maxiter,
            constraints=constraints,
        )
        designed = sort_components(result["system"])
    except Exception:
        # Fallback: return the starting system with its analysis.
        designed = base_system

    analysis = analyze_system(designed)
    warnings = validate_system(designed)

    candidates = [
        {
            "index": 0,
            "system": designed,
            "analysis": analysis,
            "warnings": warnings,
            "magnification": analysis.magnification,
            "efl_mm": analysis.effective_focal_length * 1000.0,
            "rms_spot_um": analysis.rms_spot_radius * 1e6,
            "f_number": analysis.f_number,
        }
    ]

    # If multiple candidates requested, append the starting system analysis
    # as a baseline reference (kept small and deterministic).
    try:
        ref_analysis = analyze_system(base_system)
    except ValueError:
        # Afocal baseline has no well-defined EFL supported by analyze.
        ref_analysis = None
    for i in range(1, num_candidates):
        if ref_analysis is not None:
            candidates.append(
                {
                    "index": i,
                    "system": base_system,
                    "analysis": ref_analysis,
                    "warnings": validate_system(base_system),
                    "magnification": ref_analysis.magnification,
                    "efl_mm": ref_analysis.effective_focal_length * 1000.0,
                    "rms_spot_um": ref_analysis.rms_spot_radius * 1e6,
                    "f_number": ref_analysis.f_number,
                }
            )
        else:
            candidates.append(
                {
                    "index": i,
                    "system": base_system,
                    "analysis": None,
                    "warnings": validate_system(base_system),
                    "magnification": float("nan"),
                    "efl_mm": float("inf"),
                    "rms_spot_um": float("nan"),
                    "f_number": float("nan"),
                }
            )

    return {
        "candidates": candidates,
        "requirements": {
            "magnification": magnification,
            "wavelength": wl,
            "aperture_diameter": aperture_diameter,
            "objective": objective,
        },
    }
