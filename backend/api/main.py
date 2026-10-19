"""
FastAPI backend for the AI Optical Design Engineer.

This API provides endpoints for:
    - Getting and setting the optical system
    - Tracing rays through the system
    - Analyzing the system (focal length, magnification, etc.)

The API is stateless: the frontend sends the optical system with each
request, and the backend returns the results.

Run with:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

import sys
import os
from typing import Optional

import numpy as np

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add the backend directory to the Python path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from optics.models import (
    OpticalSystem,
    RayTraceResult,
    AnalysisResult,
)
from optics.systems import create_default_system, validate_system
from optics.rays import trace_system
from optics.analysis import analyze_system
from optics.aberration import chromatic_aberration_analysis
from optics.optimization import (
    optimize_system as run_optimization,
    parameter_sweep as run_parameter_sweep,
    minimize_rms_spot,
    target_magnification,
    target_efl,
)
from optics.batch import (
    batch_analyze_systems as run_batch_analyze,
    batch_sweep_and_analyze as run_batch_sweep,
)
from optics.tolerance import tolerance_analysis as run_tolerance
from optics.report import (
    compare_systems as run_compare,
    system_spot_svg as run_spot_svg,
    engineering_report_markdown as run_report_markdown,
)
from optics.diffraction import diffraction_analysis as run_diffraction
from optics.seidel import seidel_analysis as run_seidel
from optics.high_order import (
    ray_fan as run_ray_fan,
    opd_fan as run_opd_fan,
    field_curves as run_field_curves,
    field_extent,
    require_finite_image,
)
from persistence import (
    save_system as db_save_system,
    list_systems as db_list_systems,
    get_system as db_get_system,
    delete_system as db_delete_system,
)
from ai.commands import AICommand
from ai.engine import execute_command
from ai.local_provider import LocalLLMProvider

# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class TraceRequest(BaseModel):
    """Request body for ray tracing."""

    system: OpticalSystem
    num_rays: Optional[int] = None
    aperture_fraction: Optional[float] = None


class AnalyzeRequest(BaseModel):
    """Request body for analysis."""

    system: OpticalSystem
    num_rays: Optional[int] = None
    aperture_fraction: Optional[float] = None


class AberrationRequest(BaseModel):
    """Request body for chromatic aberration analysis."""

    system: OpticalSystem
    wavelengths: Optional[list[float]] = None


class OptimizeRequest(BaseModel):
    """Request body for numerical optimization."""

    system: OpticalSystem
    objective: str
    target: Optional[float] = None
    params: list[dict]
    bounds: list[list[float]]


class SweepRequest(BaseModel):
    """Request body for a parameter sweep."""

    system: OpticalSystem
    param: dict
    values: list[float]
    num_rays: Optional[int] = None
    aperture_fraction: Optional[float] = None


class CompareRequest(BaseModel):
    """Request body for comparing two systems."""

    system_a: OpticalSystem
    system_b: OpticalSystem
    label_a: str = "Design A"
    label_b: str = "Design B"


class BatchRequest(BaseModel):
    """Request body for batch analysis."""

    systems: list[OpticalSystem]


class ToleranceRequest(BaseModel):
    """Request body for Monte-Carlo tolerance analysis."""

    system: OpticalSystem
    tolerances: Optional[dict[str, float]] = None
    trials: int = 100
    seed: Optional[int] = None


class ReportRequest(BaseModel):
    """Request body for generating an engineering report."""

    system_a: Optional[OpticalSystem] = None
    system_b: Optional[OpticalSystem] = None
    label_a: str = "Design A"
    label_b: str = "Design B"
    include_svg: bool = False


class FieldAnalysisRequest(BaseModel):
    """Request body for ray-fan and OPD-fan analysis at one field point."""

    system: OpticalSystem
    field_fraction: float = Field(default=1.0, ge=0.0, le=1.0)
    num_rays: int = Field(default=21, ge=3, le=201)


class FieldCurvesRequest(BaseModel):
    """Request body for field curvature / distortion curves."""

    system: OpticalSystem
    num_fields: int = Field(default=11, ge=2, le=51)


class SystemResponse(BaseModel):
    """Response containing the optical system and validation warnings."""

    system: OpticalSystem
    warnings: list[str] = Field(default_factory=list)


class SaveSystemRequest(BaseModel):
    """Request body for saving a system to the database."""

    name: str
    system: OpticalSystem


class SystemMetadata(BaseModel):
    """Metadata for a saved system (without the full system JSON)."""

    id: int
    name: str
    created_at: str
    updated_at: str


class SavedSystemResponse(BaseModel):
    """A saved system with its metadata and JSON."""

    id: int
    name: str
    system_json: str
    created_at: str
    updated_at: str


class AICommandRequest(BaseModel):
    """Request body for executing an AI command."""

    system: OpticalSystem
    command: AICommand


class AICommandResponse(BaseModel):
    """Response from executing an AI command."""

    system: OpticalSystem
    warnings: list[str] = Field(default_factory=list)
    result: Optional[dict] = None
    message: str


class AIInterpretRequest(BaseModel):
    """Request body for interpreting a natural-language prompt."""

    system: OpticalSystem
    prompt: str


class AIInterpretResponse(BaseModel):
    """Response from interpreting a natural-language prompt."""

    commands: list[AICommand]
    message: str


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

from fastapi.responses import JSONResponse as _BaseJSONResponse


def _json_safe(obj):
    """Convert NumPy values, dataclasses and models to JSON types; inf and
    NaN (e.g. the EFL of an afocal system) become null, since JSON has no
    representation for them."""
    import dataclasses
    import math
    import numpy as np
    from pydantic import BaseModel as _BM

    if isinstance(obj, _BM):
        return _json_safe(obj.model_dump())
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _json_safe(
            {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
        )
    if isinstance(obj, np.ndarray):
        return _json_safe(obj.tolist())
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, (complex, np.complexfloating)):
        return {"real": _json_safe(obj.real), "imag": _json_safe(obj.imag)}
    return obj


def _register_numpy_encoders():
    """Let FastAPI's jsonable_encoder (used on endpoint return values before
    the response class renders them) accept NumPy scalars and arrays."""
    import numpy as np
    import fastapi.encoders as fe

    fe.ENCODERS_BY_TYPE[np.ndarray] = lambda a: a.tolist()
    fe.ENCODERS_BY_TYPE[np.generic] = lambda v: v.item()
    fe.encoders_by_class_tuples = fe.generate_encoders_by_class_tuples(
        fe.ENCODERS_BY_TYPE
    )


_register_numpy_encoders()


class SafeJSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        return super().render(_json_safe(content))


app = FastAPI(
    title="AI Optical Design Engineer API",
    description="A local-first optical design and ray-tracing engine.",
    version="0.1.0",
    default_response_class=SafeJSONResponse,
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for local development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handlers
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Handle validation errors with clear error messages."""
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append(f"{field}: {error['msg']}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": errors,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(ZeroDivisionError)
async def zero_division_handler(request, exc):
    """Handle division by zero (e.g., object at focal point)."""
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Optical calculation error: object may be at focal point or system configuration is invalid"
        },
    )


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "features": {
            "ray_tracing": True,
            "analysis": True,
            "diffraction": True,
            "seidel": True,
            "optimization": True,
            "tolerance": True,
            "comparison": True,
        },
    }


@app.get("/")
async def root():
    """Root endpoint - returns API information."""
    return {
        "name": "AI Optical Design Engineer API",
        "version": "0.1.0",
        "description": "A local-first optical design and ray-tracing engine.",
        "endpoints": {
            "GET /api/system/default": "Get the default optical system",
            "POST /api/trace": "Trace rays through an optical system",
            "POST /api/analyze": "Analyze an optical system",
            "POST /api/optimize": "Numerically optimize system parameters",
            "POST /api/sweep": "Sweep a parameter across a range of values",
            "POST /api/compare": "Compare two systems side by side",
            "POST /api/batch": "Batch-analyze a list of systems",
            "POST /api/tolerance": "Run Monte-Carlo tolerance analysis",
            "POST /api/report": "Generate an engineering (Markdown) report",
            "POST /api/analyze/aberration": "Analyze chromatic aberration",
            "POST /api/validate": "Validate an optical system",
            "GET /api/systems": "List saved projects",
            "POST /api/systems": "Save a project",
            "GET /api/systems/{id}": "Load a saved project",
            "DELETE /api/systems/{id}": "Delete a saved project",
            "POST /api/ai/interpret": "Interpret a natural-language prompt",
            "POST /api/ai/command": "Execute a structured AI command",
        },
    }


@app.get("/api/system/default", response_model=SystemResponse)
async def get_default_system():
    """
    Get the default two-lens optical system.

    Returns a simple two-lens relay system that can be used as a
    starting point for optical design.
    """
    system = create_default_system()
    warnings = validate_system(system)
    return SystemResponse(system=system, warnings=warnings)


@app.get("/api/presets")
async def get_presets_list():
    """
    Get a list of preset optical systems.

    Returns metadata for all available preset systems without the full
    system data. Use GET /api/presets/{id} to get a specific preset.
    """
    from optics.presets import get_presets

    presets = get_presets()
    # Return metadata only (without full system JSON)
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "category": p["category"],
        }
        for p in presets
    ]


@app.get("/api/presets/{preset_id}")
async def get_preset(preset_id: str):
    """
    Get a specific preset optical system by ID.

    Returns the full optical system for the requested preset.
    """
    from optics.presets import get_preset_by_id

    preset = get_preset_by_id(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    warnings = validate_system(preset["system"])
    return {
        "id": preset["id"],
        "name": preset["name"],
        "description": preset["description"],
        "category": preset["category"],
        "system": preset["system"],
        "warnings": warnings,
    }


@app.post("/api/trace", response_model=RayTraceResult)
async def trace_rays(request: TraceRequest):
    """
    Trace rays through an optical system.

    Accepts an optical system and returns the ray paths, image position,
    and image height.

    Args:
        request: Contains the optical system and optional ray tracing settings.

    Returns:
        RayTraceResult with ray paths and image information.
    """
    try:
        result = trace_system(
            request.system,
            num_rays=request.num_rays,
            aperture_fraction=request.aperture_fraction,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze", response_model=AnalysisResult)
async def analyze(request: AnalyzeRequest):
    """
    Analyze an optical system.

    Accepts an optical system and returns the effective focal length,
    magnification, F-number, numerical aperture, RMS spot radius,
    and other optical properties.

    Args:
        request: Contains the optical system and optional analysis settings.

    Returns:
        AnalysisResult with all calculated optical properties.
    """
    try:
        result = analyze_system(
            request.system,
            num_rays=request.num_rays,
            aperture_fraction=request.aperture_fraction,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/optimize")
async def optimize(request: OptimizeRequest):
    """
    Optimize a set of system parameters to minimize an objective.

    Uses SciPy's differential_evolution to find parameter values that
    minimize the chosen objective (rms_spot, magnification, or efl).

    Args:
        request: Contains the system, objective, params, and bounds.

    Returns:
        Dict with params, objective, system, and success.
    """
    try:
        if request.objective == "rms_spot":
            objective = minimize_rms_spot
        elif request.objective == "magnification":
            if request.target is None:
                raise ValueError("magnification objective requires a target.")
            objective = lambda s: target_magnification(s, request.target)
        elif request.objective == "efl":
            if request.target is None:
                raise ValueError("efl objective requires a target.")
            objective = lambda s: target_efl(s, request.target)
        else:
            raise ValueError(f"Unknown objective: {request.objective}")

        bounds = [(b[0], b[1]) for b in request.bounds]
        result = run_optimization(
            request.system,
            objective,
            params=request.params,
            bounds=bounds,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/sweep")
async def sweep(request: SweepRequest):
    """
    Sweep a single parameter across a range of values and analyze each.

    Useful for understanding how a system behaves as a parameter
    (e.g. lens position, focal length) changes.

    Args:
        request: Contains the system, param spec, and values to sweep.

    Returns:
        List of dicts, one per value, with the parameter value and
        the analysis result for that value.
    """
    try:
        results = run_parameter_sweep(
            request.system,
            request.param,
            request.values,
            num_rays=request.num_rays,
            aperture_fraction=request.aperture_fraction,
        )
        return [
            {
                "value": value,
                "analysis": result.model_dump(),
            }
            for value, result in results
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/compare")
async def compare(request: CompareRequest):
    """Compare two optical systems side by side."""
    try:
        return run_compare(
            request.system_a,
            request.system_b,
            request.label_a,
            request.label_b,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/batch")
async def batch_analyze(request: BatchRequest):
    """Analyze a list of optical systems in batch."""
    try:
        return run_batch_analyze(request.systems)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tolerance")
async def tolerance(request: ToleranceRequest):
    """Run a Monte-Carlo tolerance analysis on a system."""
    try:
        result = run_tolerance(
            request.system,
            tolerances=request.tolerances,
            trials=request.trials,
            seed=request.seed,
        )
        # Drop the heavy "worst" system from the response to keep it light.
        result.pop("worst", None)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/report")
async def report(request: ReportRequest):
    """Generate an engineering (Markdown) report for one or two designs."""
    try:
        return {
            "markdown": run_report_markdown(
                request.system_a,
                request.system_b,
                request.label_a,
                request.label_b,
                request.include_svg,
            )
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/aberration")
async def analyze_aberration(request: AberrationRequest):
    """
    Analyze chromatic aberration of an optical system.

    Computes image position and height at multiple wavelengths and
    returns the longitudinal and lateral chromatic aberration.

    Args:
        request: Contains the optical system and optional wavelengths.

    Returns:
        Dict with wavelengths, image_positions, image_heights, lca, tca.
    """
    try:
        result = chromatic_aberration_analysis(
            request.system,
            wavelengths=request.wavelengths,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _make_serializable(obj):
    """JSON-safe copy of an analysis result (see _json_safe)."""
    return _json_safe(obj)


@app.post("/api/analyze/diffraction")
async def analyze_diffraction(request: AnalyzeRequest):
    """
    Run diffraction analysis (PSF, MTF, OTF, Airy disk) on a system.

    Computes diffraction-based performance metrics including the Airy disk
    radius, point spread function, encircled energy, modulation transfer
    function, optical transfer function, and diffraction-limited assessment.

    Args:
        request: Contains the optical system.

    Returns:
        Dict with psf, encircled_energy, mtf, otf, airy_disk_radius,
        and diffraction_limited assessment.
    """
    try:
        result = run_diffraction(
            request.system,
            wavelength=request.system.analysis_settings.wavelength,
        )
        # Convert complex OTF to magnitude/phase for JSON serialization
        if "otf" in result and "otf" in result["otf"]:
            otf_complex = result["otf"]["otf"]
            result["otf"]["otf_mag"] = (
                [abs(v) for v in otf_complex]
                if not isinstance(otf_complex[0], complex)
                else [abs(v) for v in otf_complex]
            )
            result["otf"]["otf_phase"] = [0.0] * len(
                otf_complex
            )  # aberration-free => zero phase
            del result["otf"]["otf"]  # remove complex array
        return _make_serializable(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/seidel")
async def analyze_seidel(request: AnalyzeRequest):
    """
    Run Seidel (third-order) monochromatic aberration analysis.

    Measures the five Seidel aberrations using real (exact Snell's law)
    ray tracing: spherical aberration, coma, astigmatism, field curvature,
    and distortion.

    Args:
        request: Contains the optical system.

    Returns:
        Dict with spherical_aberration, coma, astigmatism, field_curvature,
        distortion, paraxial_image_position, and paraxial_image_height.
    """
    try:
        result = run_seidel(request.system)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/ray-fan")
async def analyze_ray_fan(request: FieldAnalysisRequest):
    """
    Real-ray tangential and sagittal ray fans at the system image plane.

    Returns transverse ray errors relative to the chief ray (meters, null
    for vignetted rays) against normalised pupil coordinate, plus the full
    field extent the ``field_fraction`` refers to.
    """
    try:
        require_finite_image(request.system)
        result = run_ray_fan(request.system, request.num_rays, request.field_fraction)
        result.update(field_extent(request.system))
        return _make_serializable(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/opd-fan")
async def analyze_opd_fan(request: FieldAnalysisRequest):
    """
    Optical path difference along the tangential and sagittal pupil axes at
    the system image plane (meters), with the 2D-pupil RMS, peak-to-valley
    and Strehl ratio.
    """
    try:
        require_finite_image(request.system)
        result = run_opd_fan(request.system, request.num_rays, request.field_fraction)
        result.update(field_extent(request.system))
        return _make_serializable(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/field-curves")
async def analyze_field_curves(request: FieldCurvesRequest):
    """
    Real-ray field curvature and distortion versus field.

    Tangential, sagittal and medial foci are relative to the paraxial image
    (meters, positive in the direction of travel); distortion is a fraction
    of the paraxial image height.
    """
    try:
        require_finite_image(request.system)
        result = run_field_curves(request.system, request.num_fields)
        result.update(field_extent(request.system))
        return _make_serializable(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Surface-by-surface prescription (lens data editor model)
# ---------------------------------------------------------------------------
# These work alongside the component-based endpoints: a LensData converts to
# the OpticalSystem every analysis endpoint accepts, and back.

from optics import lens_data as _ld  # noqa: E402


class LensFromSystemRequest(BaseModel):
    system: OpticalSystem


class LensRequest(BaseModel):
    lens: _ld.LensData


class LensOptimizeRequest(BaseModel):
    lens: _ld.LensData
    bounds: dict[str, list[float]] = Field(
        default_factory=dict, description='{"<surface>.<parameter>": [low, high]}'
    )
    max_evaluations: int = Field(300, ge=1, le=10000)


def _first_order_summary(system: OpticalSystem) -> dict:
    from optics import raytrace as rt

    fo = rt.first_order(system)
    return {
        "efl": fo.efl,
        "bfl": fo.bfl,
        "f_number": fo.f_number,
        "working_f_number": fo.working_f_number,
        "image_z": fo.image_z,
        "image_height": fo.image_height,
        "magnification": fo.magnification,
        "entrance_pupil_diameter": 2 * fo.entrance_pupil_semi_diameter,
        "exit_pupil_z": fo.exit_pupil_z,
    }


@app.post("/api/lens/from-system")
async def lens_from_system(request: LensFromSystemRequest):
    """Surface-by-surface prescription of a component-based system."""
    try:
        return {"lens": _ld.from_system(request.system)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lens/resolve")
async def lens_resolve(request: LensRequest):
    """
    Apply pickups and solves, fill automatic semi-diameters, and return the
    resolved prescription with its component-based system (for every other
    analysis endpoint) and its first-order properties.
    """
    try:
        resolved = _ld.resolve(request.lens)
        system = _ld.to_system(resolved)
        return {
            "lens": resolved,
            "system": system,
            "first_order": _first_order_summary(system),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/lens/optimize")
async def lens_optimize(request: LensOptimizeRequest):
    """
    Damped least squares over the prescription's variables, minimising the
    transverse ray errors (mean-square spot over fields 0, 0.7, 1 and all
    wavelengths) with solves and pickups held.
    """
    try:
        bounds = {}
        for key, pair in request.bounds.items():
            if len(pair) != 2:
                raise ValueError(f"Bound '{key}' needs [low, high]")
            bounds[key] = (pair[0], pair[1])
        result = _ld.optimize(
            request.lens, bounds=bounds, max_evaluations=request.max_evaluations
        )
        result["rms_spot_before"] = result["merit_before"] ** 0.5
        result["rms_spot_after"] = result["merit_after"] ** 0.5
        result["first_order"] = _first_order_summary(result["system"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Field table analyses
# ---------------------------------------------------------------------------


class FieldsRequest(BaseModel):
    system: OpticalSystem
    rings: int = Field(6, ge=1, le=20)


class FieldMtfRequest(BaseModel):
    system: OpticalSystem
    field: int = Field(0, ge=0)
    frequencies: Optional[list[float]] = Field(None, description="cycles/mm")
    grid: int = Field(64, ge=16, le=256)


@app.post("/api/analyze/fields")
async def analyze_fields(request: FieldsRequest):
    """
    Per-field results for the system's field table (or the default 0, 0.7
    and 1 of the object height): real chief ray and paraxial image position,
    distortion, wavelength-weighted RMS spot and centroid, vignetting, and
    the field-weighted RMS spot.
    """
    from optics.fields import field_summary

    try:
        return field_summary(request.system, rings=request.rings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/field-mtf")
async def analyze_field_mtf(request: FieldMtfRequest):
    """Wavelength-weighted diffraction MTF of one field point, tangential
    along its image direction and sagittal across it."""
    from optics.fields import field_mtf

    try:
        return field_mtf(
            request.system, request.field, request.frequencies, request.grid
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/validate", response_model=SystemResponse)
async def validate(system: OpticalSystem):
    """
    Validate an optical system.

    Checks for common issues such as overlapping components,
    objects after the first lens, and zero focal lengths.

    Args:
        system: The optical system to validate.

    Returns:
        SystemResponse with the system and a list of warnings.
    """
    warnings = validate_system(system)
    return SystemResponse(system=system, warnings=warnings)


# ---------------------------------------------------------------------------
# Persistence Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/systems", response_model=list[SystemMetadata])
async def list_saved_systems():
    """
    List all saved optical system projects.

    Returns metadata (id, name, timestamps) for each saved system,
    ordered by most recently updated first.
    """
    return db_list_systems()


@app.post("/api/systems", response_model=SystemMetadata)
async def save_system(request: SaveSystemRequest):
    """
    Save an optical system project to the database.

    If a system with the same name already exists, it is updated.

    Args:
        request: Contains the project name and the optical system.

    Returns:
        Metadata for the saved system.
    """
    system_json = request.system.model_dump_json()
    system_id = db_save_system(request.name, system_json)
    saved = db_get_system(system_id)
    return SystemMetadata(
        id=saved["id"],
        name=saved["name"],
        created_at=saved["created_at"],
        updated_at=saved["updated_at"],
    )


@app.get("/api/systems/{system_id}", response_model=SavedSystemResponse)
async def load_system(system_id: int):
    """
    Load a saved optical system project by id.

    Args:
        system_id: The id of the saved system.

    Returns:
        The saved system including its JSON representation.

    Raises:
        HTTPException: If the system id does not exist.
    """
    saved = db_get_system(system_id)
    if saved is None:
        raise HTTPException(status_code=404, detail=f"System {system_id} not found.")
    return SavedSystemResponse(**saved)


@app.get("/api/ai/provider")
async def ai_provider():
    """
    Report the current AI interpreter provider configuration.

    Returns whether Ollama is enabled and the model/URL in use.
    """
    return {
        "use_ollama": os.environ.get("OLLAMA_ENABLED", "").lower()
        in ("1", "true", "yes"),
        "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
        "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    }


@app.post("/api/ai/interpret", response_model=AIInterpretResponse)
async def ai_interpret(request: AIInterpretRequest):
    """
    Interpret a natural-language prompt into structured AI commands.

    Uses the local rule-based parser (or Ollama if enabled) to convert
    the user's request into structured commands. The commands are NOT
    executed here; use POST /api/ai/command to apply them.

    Args:
        request: Contains the optical system and the natural-language prompt.

    Returns:
        The interpreted commands and a human-readable message.
    """
    try:
        provider = LocalLLMProvider(
            use_ollama=os.environ.get("OLLAMA_ENABLED", "").lower()
            in ("1", "true", "yes"),
            model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        )
        commands = provider.interpret(
            request.prompt, {"component_ids": [c.id for c in request.system.components]}
        )
        return AIInterpretResponse(
            commands=commands,
            message=f"Interpreted {len(commands)} command(s).",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/ai/command", response_model=AICommandResponse)
async def ai_command(request: AICommandRequest):
    """
    Execute a structured AI command against an optical system.

    The AI never performs optical calculations directly. It emits a
    structured command (modify_component, add_component, analyze, etc.)
    which is validated and applied by the optics engine.

    Args:
        request: Contains the optical system and the AI command.

    Returns:
        The updated system, validation warnings, and any result
        (e.g. analysis or optimization result).
    """
    try:
        result = execute_command(request.system, request.command)
        return AICommandResponse(
            system=result["system"],
            warnings=result["warnings"],
            result=(
                _json_safe(result["result"]) if result["result"] is not None else None
            ),
            message=result["message"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/systems/{system_id}")
async def delete_system(system_id: int):
    """
    Delete a saved optical system project by id.

    Args:
        system_id: The id of the saved system.

    Returns:
        A confirmation message.

    Raises:
        HTTPException: If the system id does not exist.
    """
    deleted = db_delete_system(system_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"System {system_id} not found.")
    return {"message": f"System {system_id} deleted."}


# ---------------------------------------------------------------------------
# Advanced Optimization Endpoints
# ---------------------------------------------------------------------------


class HybridOptimizeRequest(BaseModel):
    """Request body for hybrid optimization."""

    system: OpticalSystem
    objective: str = "rms_spot"  # rms_spot, efl, magnification
    target: Optional[float] = None  # required for the efl / magnification objectives
    params: list[dict]  # [{"component_id": "L1", "field": "focal_length"}, ...]
    bounds: list[list[float]]  # [[min, max], ...]
    constraints: list[dict] = []  # [{"type": "efl", "lower": 0.09, "upper": 0.11}, ...]
    global_algorithm: str = "differential_evolution"  # or "particle_swarm"
    local_algorithm: str = "damped_least_squares"  # "l_bfgs_b", "nelder_mead"
    global_maxiter: int = 200
    local_maxiter: int = 100
    seed: Optional[int] = 42


@app.post("/api/optimize/hybrid")
async def hybrid_optimize(request: HybridOptimizeRequest):
    """
    Run hybrid optimization (global search + local refinement).

    This is the professional standard optimization workflow:
    1. Global search (Differential Evolution) to find promising region
    2. Local refinement (Damped Least Squares) for precise optimum

    Args:
        request: Contains system, objective, parameters, bounds, constraints.

    Returns:
        Optimized system and optimization statistics.
    """
    from optics.advanced_optimization import (
        hybrid_optimize as run_hybrid,
        OptimizationConfig,
        OptimizationConstraint,
        GlobalAlgorithm,
        LocalAlgorithm,
    )

    try:
        if request.objective not in ("rms_spot", "efl", "magnification"):
            raise ValueError(f"Unknown objective: {request.objective}")
        if request.objective != "rms_spot" and request.target is None:
            raise ValueError(f"{request.objective} objective requires a target.")

        # Build constraints
        constraints = []
        for c in request.constraints:
            # a missing or null bound means unbounded on that side
            constraints.append(
                OptimizationConstraint(
                    type=c.get("type", ""),
                    surface_index=c.get("surface_index"),
                    lower=c.get("lower") if c.get("lower") is not None else -np.inf,
                    upper=c.get("upper") if c.get("upper") is not None else np.inf,
                    weight=c.get("weight", 1.0),
                )
            )

        # Build config
        config = OptimizationConfig(
            global_algorithm=GlobalAlgorithm(request.global_algorithm),
            local_algorithm=LocalAlgorithm(request.local_algorithm),
            global_maxiter=request.global_maxiter,
            local_maxiter=request.local_maxiter,
            constraints=constraints,
            seed=request.seed,
        )

        # Build objective function
        def objective(sys: OpticalSystem) -> float:
            analysis = analyze_system(sys)
            if request.objective == "rms_spot":
                return analysis.rms_spot_radius
            if request.objective == "efl":
                return abs(analysis.effective_focal_length - request.target)
            return abs(analysis.magnification - request.target)

        result = run_hybrid(
            request.system,
            objective,
            request.params,
            [tuple(b) for b in request.bounds],
            config=config,
        )

        return _make_serializable(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConstraintValuesRequest(BaseModel):
    """Request body for evaluating optimization constraint operands."""

    system: OpticalSystem
    constraints: list[
        dict
    ]  # [{"type": "efl", "surface_index": None, "lower": .., "upper": .., "weight": ..}]


@app.post("/api/optimize/constraints")
async def evaluate_constraints(request: ConstraintValuesRequest):
    """
    Current value of each constraint operand and its penalty, exactly as
    the hybrid optimizer evaluates them (penalty = weight * violation * 1e6).
    Operands that cannot be evaluated for this system come back with a null
    value and an error message.
    """
    from optics.advanced_optimization import (
        OptimizationConstraint,
        _get_constraint_value,
    )

    try:
        analysis = analyze_system(request.system)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    rows = []
    for c in request.constraints:
        con = OptimizationConstraint(
            type=c.get("type", ""),
            surface_index=c.get("surface_index"),
            lower=c.get("lower") if c.get("lower") is not None else -np.inf,
            upper=c.get("upper") if c.get("upper") is not None else np.inf,
            weight=c.get("weight", 1.0),
        )
        try:
            value = float(_get_constraint_value(request.system, analysis, con))
        except ValueError as e:
            rows.append(
                {
                    "type": con.type,
                    "value": None,
                    "violation": None,
                    "penalty": None,
                    "error": str(e),
                }
            )
            continue
        violation = max(con.lower - value, value - con.upper, 0.0)
        rows.append(
            {
                "type": con.type,
                "value": value,
                "violation": violation,
                "penalty": con.weight * violation * 1e6,
                "error": None,
            }
        )
    return _make_serializable({"constraints": rows})


class HighYieldOptimizeRequest(BaseModel):
    """Request body for high-yield optimization."""

    system: OpticalSystem
    objective: str = "rms_spot"
    params: list[dict]
    bounds: list[list[float]]
    tolerances: dict[str, float]  # {"L1.position": 1e-4, ...}
    yield_threshold: float = 0.95
    n_monte_carlo: int = 30
    global_maxiter: int = 50
    local_maxiter: int = 25
    seed: Optional[int] = 42


@app.post("/api/optimize/high-yield")
async def high_yield_optimize(request: HighYieldOptimizeRequest):
    """
    Run high-yield optimization (nominal + tolerance sensitivity).

    Optimizes both nominal performance and tolerance sensitivity
    to maximize as-built yield.

    Args:
        request: Contains system, objective, parameters, tolerances.

    Returns:
        Optimized system and yield statistics.
    """
    from optics.advanced_optimization import (
        high_yield_optimize as run_high_yield,
        OptimizationConfig,
    )

    try:
        if request.objective != "rms_spot":
            raise ValueError(
                "High-yield optimization supports only the rms_spot objective."
            )
        config = OptimizationConfig(
            global_maxiter=request.global_maxiter,
            local_maxiter=request.local_maxiter,
            optimize_yield=True,
            yield_threshold=request.yield_threshold,
            tolerance_specs=request.tolerances,
            n_monte_carlo=request.n_monte_carlo,
            seed=request.seed,
        )

        def objective(sys: OpticalSystem) -> float:
            return analyze_system(sys).rms_spot_radius

        result = run_high_yield(
            request.system,
            objective,
            request.params,
            [tuple(b) for b in request.bounds],
            tolerance_specs=request.tolerances,
            yield_threshold=request.yield_threshold,
            n_monte_carlo=request.n_monte_carlo,
            config=config,
        )

        return _make_serializable(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Non-Sequential Analysis Endpoints
# ---------------------------------------------------------------------------


class GhostAnalysisRequest(BaseModel):
    """Request body for ghost reflection analysis."""

    system: OpticalSystem
    n_reflections: int = 2
    threshold: float = 1e-4


@app.post("/api/analyze/ghosts")
async def analyze_ghosts(request: GhostAnalysisRequest):
    """
    Analyze ghost reflections in the optical system.

    Ghost reflections occur when light reflects off two surfaces and
    returns to the image plane, creating unwanted artifacts.

    Args:
        request: Contains the system and analysis parameters.

    Returns:
        List of ghost paths sorted by intensity.
    """
    from optics.nonsequential import analyze_ghost_reflections

    try:
        ghosts = analyze_ghost_reflections(
            request.system,
            n_reflections=request.n_reflections,
            threshold=request.threshold,
        )

        return {
            "ghosts": [
                {
                    "surfaces": list(g.surfaces),
                    "reflection_count": g.reflection_count,
                    "relative_intensity": g.relative_intensity,
                    "image_position_offset": g.image_position,
                    "is_in_field": g.is_in_field,
                    "description": g.description,
                }
                for g in ghosts
            ],
            "n_ghosts": len(ghosts),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class StrayLightRequest(BaseModel):
    """Request body for stray light analysis."""

    system: OpticalSystem
    source_angle: float = 30.0
    brdf_model: str = "lambertian"
    diffuse_fraction: float = 0.01


@app.post("/api/analyze/straylight")
async def analyze_stray_light(request: StrayLightRequest):
    """
    Analyze stray light paths in the optical system.

    Args:
        request: Contains the system and analysis parameters.

    Returns:
        List of stray light paths sorted by intensity.
    """
    from optics.nonsequential import analyze_stray_light, BRDFParameters

    try:
        brdf_params = BRDFParameters(
            model=request.brdf_model,
            diffuse_fraction=request.diffuse_fraction,
        )

        stray_paths = analyze_stray_light(
            request.system,
            source_angle=request.source_angle,
            brdf_params=brdf_params,
        )

        return {
            "paths": [
                {
                    "path_id": p.path_id,
                    "source_surface": p.source_surface,
                    "scatter_surface": p.scatter_surface,
                    "relative_intensity": p.relative_intensity,
                    "path_type": p.path_type,
                    "description": p.description,
                }
                for p in stray_paths
            ],
            "n_paths": len(stray_paths),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class PSTRequest(BaseModel):
    """Request body for Point Source Transmittance analysis."""

    system: OpticalSystem
    angles: list[float] = [5, 10, 15, 20, 25, 30, 35, 40, 45]
    brdf_model: str = "lambertian"
    diffuse_fraction: float = 0.01


@app.post("/api/analyze/pst")
async def compute_pst_endpoint(request: PSTRequest):
    """
    Compute Point Source Transmittance (PST) vs angle.

    PST measures the stray light rejection capability of a system.

    Args:
        request: Contains the system and angle range.

    Returns:
        PST values in dB for each angle.
    """
    from optics.nonsequential import compute_pst, BRDFParameters

    try:
        brdf_params = BRDFParameters(
            model=request.brdf_model,
            diffuse_fraction=request.diffuse_fraction,
        )

        angles = np.array(request.angles)
        pst_values = compute_pst(request.system, angles, brdf_params)

        return {
            "angles": request.angles,
            "pst_db": pst_values.tolist(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Throughput & Realism Endpoints (roadmap item 11)
# ---------------------------------------------------------------------------
# Unlike the endpoints above, which mostly work from paraxial quantities or
# reflectances, these drive the real-ray throughput and imaging analyses:
# measured vignetting and relative illumination, bidirectional ghost paths,
# and a full image simulation with a detector model.


class IlluminationRequest(BaseModel):
    """Request body for illumination and vignetting analysis."""

    system: OpticalSystem
    num_fields: int = 11
    num_rays: int = 21
    focus_points: int = 21


@app.post("/api/analyze/illumination")
async def analyze_illumination(request: IlluminationRequest):
    """
    Vignetting, relative illumination and MTF across field and focus.

    The vignetting factor is measured by tracing real ray bundles through
    the actual apertures, then combined with the cos^4 obliquity law and
    normalised to 1.0 on axis. The MTF maps use the same equivalent-Gaussian
    blur model as the image simulator, so the two agree by construction.

    Args:
        request: Contains the system and the sampling parameters.

    Returns:
        Dict with vignetting, relative illumination and the MTF field and
        focus maps, plus a text summary.
    """
    from optics.illumination import illumination_summary

    try:
        result = illumination_summary(
            request.system,
            num_fields=request.num_fields,
            num_rays=request.num_rays,
            focus_points=request.focus_points,
        )
        return _make_serializable(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class GhostPathRequest(BaseModel):
    """Request body for real-ray ghost reflection analysis."""

    system: OpticalSystem
    field_fraction: Optional[float] = None
    num_rays: int = 5
    min_relative_irradiance: float = 1e-6
    coating_reflectance: Optional[float] = None
    mirror_reflectance: float = 0.95
    include_blocked: bool = False


@app.post("/api/analyze/ghost-paths")
async def analyze_ghost_paths(request: GhostPathRequest):
    """
    Trace genuine double-reflection ghost paths through the real system.

    Where ``/api/analyze/ghosts`` ranks ghost orders from reflectances alone,
    this propagates actual ray paths: forward to the first reflecting
    surface, back toward the object to the second, then forward again to the
    image plane. That answers where each ghost focuses, how large its spot
    is, and whether its path reaches the image at all.

    Args:
        request: Contains the system and the analysis parameters.
            ``field_fraction`` may be omitted to analyse both the axis and
            the field edge.

    Returns:
        The field-wide summary, or, when ``field_fraction`` is given, the
        ranked ghost list for that single field point.
    """
    from optics.ghost import analyze_ghosts as run_analyze_ghosts
    from optics.ghost import ghost_analysis as run_ghost_analysis

    kwargs = dict(
        num_rays=request.num_rays,
        min_relative_irradiance=request.min_relative_irradiance,
        coating_reflectance=request.coating_reflectance,
        mirror_reflectance=request.mirror_reflectance,
        include_blocked=request.include_blocked,
    )
    try:
        if request.field_fraction is None:
            return _make_serializable(run_ghost_analysis(request.system, **kwargs))
        ghosts = run_analyze_ghosts(
            request.system, field_fraction=request.field_fraction, **kwargs
        )
        return _make_serializable(
            {
                "field_fraction": request.field_fraction,
                "ghosts": [g.as_dict() for g in ghosts],
                "num_ghosts": len(ghosts),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ImagingRequest(BaseModel):
    """Request body for image simulation."""

    system: OpticalSystem
    target_kind: str = "bars"
    resolution: int = 128
    pixel_pitch: float = 5.0e-6
    field_fraction: float = 0.0
    full_field: bool = False
    with_noise: bool = True
    seed: Optional[int] = None
    include_image: bool = False


@app.post("/api/analyze/imaging")
async def analyze_imaging(request: ImagingRequest):
    """
    Simulate the image a test target forms through the real system.

    Applies the aberration and diffraction PSF, the illumination map, radial
    distortion, and the detector model (photon shot noise, dark current, read
    noise, full well and ADC quantisation). The exposure is set by
    normalising the brightest pixel to 80 percent of the full well.

    Args:
        request: Contains the system, the target and the sensor geometry.
            Set ``include_image`` to also return the rendered image.

    Returns:
        Dict with the simulation metadata, the MTF measured from the bar
        chart, image-quality metrics, and optionally ``png_base64``.
    """
    import base64
    from optics.imaging import SensorConfig, encode_png_gray
    from optics.imaging import image_quality_metrics, mtf_from_bar_target
    from optics.imaging import simulate_image as run_simulate

    sensor = SensorConfig(
        resolution=request.resolution, pixel_pitch=request.pixel_pitch
    )
    try:
        simulation = run_simulate(
            request.system,
            sensor=sensor,
            target_kind=request.target_kind,
            field_fraction=request.field_fraction,
            full_field=request.full_field,
            with_noise=request.with_noise,
            seed=request.seed,
        )
        result = {
            "metadata": simulation.metadata,
            "mtf": mtf_from_bar_target(simulation.ideal, simulation.image),
            "quality": image_quality_metrics(simulation.ideal, simulation.image),
        }
        if request.include_image:
            result["png_base64"] = base64.b64encode(
                encode_png_gray(simulation.image)
            ).decode("ascii")
        return _make_serializable(result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/radiometry/brdf")
async def list_brdf_surfaces():
    """
    List the reference BRDF surfaces available for stray-light work.

    Every entry is anchored to a target total integrated scatter, the
    fraction of incident power the surface removes from the specular beam,
    which is the physically meaningful specification for a surface finish.

    Returns:
        Dict with the surface list and their model parameters.
    """
    from optics.radiometry import BRDF_DATABASE, total_integrated_scatter

    surfaces = []
    for name in sorted(BRDF_DATABASE):
        params = BRDF_DATABASE[name]
        surfaces.append(
            {
                "name": name,
                "model": params.model,
                "source": params.source,
                "target_tis": params.target_tis,
                "total_integrated_scatter": total_integrated_scatter(params),
                "A": params.A,
                "B": params.B,
                "g": params.g,
                "diffuse_fraction": params.diffuse_fraction,
            }
        )
    return _make_serializable({"surfaces": surfaces, "count": len(surfaces)})


# ---------------------------------------------------------------------------
# Import/Export Endpoints
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    """Request body for export operations."""

    system: OpticalSystem
    format: str = "zmx"  # "zmx", "seq", "svg", "bom", "sag", "iso10110"


@app.post("/api/export")
async def export_design(request: ExportRequest):
    """
    Export optical design to various formats.

    Supported formats:
    - zmx: Zemax lens data file
    - seq: Code V sequence file
    - svg: 2D lens drawing (SVG)
    - bom: Bill of Materials
    - sag: Sag table
    - iso10110: ISO 10110 optical drawing

    Args:
        request: Contains the system and desired format.

    Returns:
        Exported file content as string.
    """
    from optics.io import export_zmx, export_seq
    from optics.io.drawings import (
        generate_lens_drawing,
        generate_iso10110_drawing,
        generate_sag_table,
    )
    from optics.io.bom import generate_bom

    import tempfile
    import os

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{request.format}", delete=False
        ) as f:
            filepath = f.name

        if request.format == "zmx":
            export_zmx(request.system, filepath)
        elif request.format == "seq":
            export_seq(request.system, filepath)
        elif request.format == "svg":
            generate_lens_drawing(request.system, filepath, format="svg")
        elif request.format == "bom":
            generate_bom(request.system, filepath, format="text")
        elif request.format == "sag":
            generate_sag_table(request.system, filepath)
        elif request.format == "iso10110":
            generate_iso10110_drawing(request.system, filepath)
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported format: {request.format}"
            )

        with open(filepath, "r") as f:
            content = f.read()

        os.unlink(filepath)

        return {
            "format": request.format,
            "content": content,
            "filename": f"design.{request.format}",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# AI Copilot Endpoints
# ---------------------------------------------------------------------------


class ExplainRequest(BaseModel):
    """Request body for explanation."""

    system: OpticalSystem
    question: str  # "Why does MTF drop?", "What are the main aberrations?", etc.


@app.post("/api/ai/explain")
async def ai_explain(request: ExplainRequest):
    """
    Get AI explanation of optical system behavior.

    The AI uses the validated optics engine to answer questions about
    the system. All calculations are cited.

    Args:
        request: Contains the system and question.

    Returns:
        Explanation with citations and confidence level.
    """
    from ai.copilot import explain_mtf_drop, CopilotResponse

    try:
        # Route question to appropriate handler
        question_lower = request.question.lower()

        if (
            "mtf" in question_lower
            or "drop" in question_lower
            or "performance" in question_lower
        ):
            response = explain_mtf_drop(request.system)
        elif "aberration" in question_lower:
            from ai.explanations import diagnose_system

            diagnosis = diagnose_system(request.system)
            response = CopilotResponse(
                answer=" ".join(f["message"] for f in diagnosis["findings"])
                or diagnosis["summary"],
                citations=[f"Finding: {f['message']}" for f in diagnosis["findings"]],
                confidence=1.0,
                suggested_actions=[
                    f"Suggestion: {f['suggestion']}" for f in diagnosis["findings"]
                ],
                verified=True,
            )
        else:
            from ai.explanations import explain_system

            explanation = explain_system(request.system)
            response = CopilotResponse(
                answer=" ".join(explanation["parts"]),
                citations=[
                    f"Metric: {k}={v}"
                    for k, v in explanation.get("metrics", {}).items()
                ],
                confidence=1.0,
                suggested_actions=[
                    "Ask about specific aberrations",
                    "Ask about optimization suggestions",
                ],
                verified=True,
            )

        return {
            "answer": response.answer,
            "citations": response.citations,
            "confidence": response.confidence,
            "suggested_actions": response.suggested_actions,
            "verified": response.verified,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DesignSuggestionRequest(BaseModel):
    """Request body for design suggestions."""

    requirements: dict  # {"magnification": 5, "f_number": 2.8, "field_of_view": 10}


@app.post("/api/ai/suggest")
async def ai_suggest_design(request: DesignSuggestionRequest):
    """
    Get design family suggestions based on requirements.

    Args:
        request: Contains design requirements.

    Returns:
        Design family suggestion with rationale.
    """
    from ai.copilot import suggest_design_family

    try:
        response = suggest_design_family(request.requirements)
        return {
            "answer": response.answer,
            "citations": response.citations,
            "confidence": response.confidence,
            "suggested_actions": response.suggested_actions,
            "verified": response.verified,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class NLToPrescriptionRequest(BaseModel):
    """Request body for natural language to prescription."""

    description: str  # "Design a 5x magnification system at f/2.8"


@app.post("/api/ai/nl-to-prescription")
async def ai_nl_to_prescription(request: NLToPrescriptionRequest):
    """
    Convert natural language description to optical prescription.

    Args:
        request: Natural language description.

    Returns:
        Generated optical system and explanation.
    """
    from ai.copilot import natural_language_to_prescription

    try:
        system, response = natural_language_to_prescription(request.description)
        return {
            "system": system.model_dump() if system else None,
            "answer": response.answer,
            "citations": response.citations,
            "confidence": response.confidence,
            "suggested_actions": response.suggested_actions,
            "verified": response.verified,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class VerifyRequest(BaseModel):
    """Request body for verification."""

    system: OpticalSystem
    claim: str  # "EFL is 100mm"


@app.post("/api/ai/verify")
async def ai_verify(request: VerifyRequest):
    """
    Verify a claim about the optical system.

    Runs actual calculations to verify claims.

    Args:
        request: Contains the system and claim to verify.

    Returns:
        Verification result with citations.
    """
    from ai.copilot import verify_calculation

    try:
        response = verify_calculation(request.system, request.claim)
        return {
            "answer": response.answer,
            "citations": response.citations,
            "confidence": response.confidence,
            "suggested_actions": response.suggested_actions,
            "verified": response.verified,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Non-Sequential Ray Tracing Endpoints
# ---------------------------------------------------------------------------


class NSCSourceRequest(BaseModel):
    """NSC source configuration."""

    name: str = "Source"
    position: list[float] = [0, 0, 0]
    direction: list[float] = [0, 0, 1]
    intensity: float = 1.0
    wavelength: float = 550.0  # nm
    num_rays: int = 1000
    source_type: str = "point"  # point, lambertian, collimated
    half_angle: float = 30.0  # degrees


class NSCObjectRequest(BaseModel):
    """NSC object configuration."""

    name: str = "Object"
    object_type: str = "sphere"  # sphere, cylinder, box, lens, aspheric
    position: list[float] = [0, 0, 0]
    material: Optional[str] = None
    radius: float = 25.0
    length: float = 10.0
    half_width: float = 25.0
    half_height: float = 25.0
    radius1: float = 50.0
    radius2: float = -50.0
    thickness: float = 10.0
    reflectivity: float = 0.0
    transmission: float = 1.0
    absorption: float = 0.0
    aspheric_coeffs: list[float] = []
    conic: float = 0.0


class NSCDetectorRequest(BaseModel):
    """NSC detector configuration."""

    name: str = "Detector"
    position: list[float] = [0, 0, 100]
    normal: list[float] = [0, 0, -1]
    width: float = 25.0
    height: float = 25.0
    pixels_x: int = 100
    pixels_y: int = 100


class NSCTraceRequest(BaseModel):
    """NSC trace request."""

    sources: list[NSCSourceRequest]
    objects: list[NSCObjectRequest]
    detectors: list[NSCDetectorRequest]
    max_order: int = 10
    min_intensity: float = 1e-6


@app.post("/api/nsc/trace")
async def nsc_trace(request: NSCTraceRequest):
    """
    Run non-sequential ray tracing.

    Traces rays through a system of 3D objects with splitting and scattering.

    Args:
        request: NSC system configuration.

    Returns:
        Tracing results including detector data.
    """
    from optics.nsc import (
        NSCSystem,
        Source,
        Detector,
        Object3D,
        Vector3,
        NSCTracer,
        AsphericSurface,
    )

    try:
        system = NSCSystem(
            max_order=request.max_order, min_intensity=request.min_intensity
        )

        # Add sources
        for src_req in request.sources:
            source = Source(
                name=src_req.name,
                position=Vector3(*src_req.position),
                direction=Vector3(*src_req.direction),
                intensity=src_req.intensity,
                wavelength=src_req.wavelength * 1e-9,  # nm to m
                num_rays=src_req.num_rays,
                source_type=src_req.source_type,
                half_angle=src_req.half_angle,
            )
            system.add_source(source)

        # Add objects
        for obj_req in request.objects:
            if obj_req.object_type == "aspheric":
                obj = AsphericSurface(
                    name=obj_req.name,
                    position=Vector3(*obj_req.position),
                    radius=obj_req.radius1,
                    conic=obj_req.conic,
                    aspheric_coeffs=obj_req.aspheric_coeffs,
                    aperture_radius=obj_req.radius,
                    material=obj_req.material,
                )
            else:
                obj = Object3D(
                    name=obj_req.name,
                    object_type=obj_req.object_type,
                    position=Vector3(*obj_req.position),
                    material=obj_req.material,
                    radius=obj_req.radius,
                    length=obj_req.length,
                    half_width=obj_req.half_width,
                    half_height=obj_req.half_height,
                    radius1=obj_req.radius1,
                    radius2=obj_req.radius2,
                    thickness=obj_req.thickness,
                    reflectivity=obj_req.reflectivity,
                    transmission=obj_req.transmission,
                    absorption=obj_req.absorption,
                )
            system.add_object(obj)

        # Add detectors
        for det_req in request.detectors:
            detector = Detector(
                name=det_req.name,
                position=Vector3(*det_req.position),
                normal=Vector3(*det_req.normal),
                width=det_req.width,
                height=det_req.height,
                pixels_x=det_req.pixels_x,
                pixels_y=det_req.pixels_y,
            )
            system.add_detector(detector)

        # Run trace
        tracer = NSCTracer(system)
        results = tracer.trace()

        return _make_serializable(results)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/nsc/examples")
async def nsc_examples():
    """
    Get example NSC systems.

    Returns predefined example configurations for common NSC scenarios.
    """
    return {
        "examples": [
            {
                "name": "Single Lens Focus",
                "description": "Collimated beam focused by a single lens",
                "sources": [
                    {
                        "name": "Collimated",
                        "position": [0, 0, 0],
                        "direction": [0, 0, 1],
                        "source_type": "collimated",
                        "num_rays": 1000,
                    }
                ],
                "objects": [
                    {
                        "name": "Lens",
                        "object_type": "lens",
                        "position": [0, 0, 50],
                        "radius1": 25,
                        "radius2": -25,
                        "thickness": 10,
                        "material": "N-BK7",
                    }
                ],
                "detectors": [
                    {
                        "name": "Focus",
                        "position": [0, 0, 100],
                        "width": 10,
                        "height": 10,
                        "pixels_x": 50,
                        "pixels_y": 50,
                    }
                ],
            },
            {
                "name": "Mirror Reflection",
                "description": "Beam reflected by a spherical mirror",
                "sources": [
                    {
                        "name": "Source",
                        "position": [0, 0, 0],
                        "direction": [0, 0, 1],
                        "source_type": "collimated",
                        "num_rays": 500,
                    }
                ],
                "objects": [
                    {
                        "name": "Mirror",
                        "object_type": "sphere",
                        "position": [0, 0, 50],
                        "radius": 100,
                        "reflectivity": 0.95,
                    }
                ],
                "detectors": [
                    {
                        "name": "Detector",
                        "position": [0, 0, 100],
                        "width": 50,
                        "height": 50,
                    }
                ],
            },
            {
                "name": "Lambertian Source",
                "description": "LED-like source with Lambertian distribution",
                "sources": [
                    {
                        "name": "LED",
                        "position": [0, 0, 0],
                        "direction": [0, 0, 1],
                        "source_type": "lambertian",
                        "half_angle": 30,
                        "num_rays": 10000,
                    }
                ],
                "objects": [],
                "detectors": [
                    {
                        "name": "Detector",
                        "position": [0, 0, 50],
                        "width": 50,
                        "height": 50,
                        "pixels_x": 100,
                        "pixels_y": 100,
                    }
                ],
            },
        ]
    }


# ---------------------------------------------------------------------------
# CAD Import Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/cad/import")
async def cad_import(file: UploadFile = File(...)):
    """
    Import a CAD file.

    Supports STL, OBJ, STEP, and IGES formats.

    Args:
        file: CAD file to upload

    Returns:
        Mesh data and statistics.
    """
    from optics.nsc.cad import import_cad_file
    from pathlib import Path
    import tempfile

    try:
        # Save the upload to a closed temp file (Windows cannot reopen an
        # open NamedTemporaryFile), import it, and always remove it.
        fd, tmp_path = tempfile.mkstemp(suffix=Path(file.filename or "").suffix)
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(await file.read())
            mesh = import_cad_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        return {
            "success": True,
            "filename": file.filename,
            "mesh": {
                "name": Path(file.filename or "mesh").stem,
                "num_triangles": mesh.num_triangles,
                "num_vertices": len(
                    {
                        (v.x, v.y, v.z)
                        for t in mesh.triangles
                        for v in (t.v0, t.v1, t.v2)
                    }
                ),
                "bbox_min": (
                    [mesh.bbox_min.x, mesh.bbox_min.y, mesh.bbox_min.z]
                    if mesh.bbox_min
                    else None
                ),
                "bbox_max": (
                    [mesh.bbox_max.x, mesh.bbox_max.y, mesh.bbox_max.z]
                    if mesh.bbox_max
                    else None
                ),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/cad/formats")
async def cad_formats():
    """
    Get supported CAD formats.

    Returns:
        Dictionary of supported formats and their capabilities.
    """
    from optics.nsc.cad import get_supported_formats

    return get_supported_formats()


# ---------------------------------------------------------------------------
# CAD Export Endpoint
# ---------------------------------------------------------------------------


class CADExportRequest(BaseModel):
    """CAD export of a system's element geometry (millimetres)."""

    system: OpticalSystem
    format: str = "stl"  # stl, obj, ply (STEP/IGES are not implemented)
    binary: bool = True  # For STL format


@app.post("/api/cad/export")
async def cad_export(request: CADExportRequest):
    """
    Export optical system to CAD format.

    Args:
        request: Export parameters

    Returns:
        Exported file content.
    """
    from optics.nsc.cad import export_mesh
    from optics.nsc.cad.lens_mesh import system_meshes, merge_meshes
    import tempfile

    try:
        meshes, skipped = system_meshes(request.system)
        if not meshes:
            raise ValueError(
                "No element has physical geometry to export "
                "(ideal thin lenses are skipped)"
            )
        mesh = merge_meshes(meshes)
        fd, path = tempfile.mkstemp(suffix=f".{request.format}")
        os.close(fd)
        try:
            export_mesh(mesh, path, format=request.format)
            with open(path, "rb") as f:
                content = f.read()
        finally:
            os.unlink(path)

        return {
            "success": True,
            "format": request.format,
            "units": "mm",
            "skipped": [{"id": c, "reason": r} for c, r in skipped],
            "content": content.hex(),  # Hex encode for JSON
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Conversational Design Refinement (multi-turn)
# ---------------------------------------------------------------------------


class ChatTurnModel(BaseModel):
    """One prior exchange, supplied by the client to rebuild session state."""

    user: str
    assistant: str = ""


class ChatRequest(BaseModel):
    """Request body for a conversational refinement turn."""

    system: OpticalSystem
    message: str
    history: Optional[list[ChatTurnModel]] = None
    provider: Optional[str] = None
    model: Optional[str] = None


@app.post("/api/ai/chat")
async def ai_chat(request: ChatRequest):
    """
    Process one turn of a multi-turn optical design conversation.

    The API is stateless, so the client sends the current system plus the
    prior user turns. Those turns are replayed to rebuild session state so
    that anaphora ("make IT faster") and undo behave correctly.

    Recognised refinement intents include: add/remove element, make
    faster/smaller, widen/stop-down aperture, scale by N, refocus,
    optimize, analyze, diagnose, design, and undo.
    """
    from ai.conversation import ConversationSession

    try:
        session = ConversationSession(request.system)
        for turn in request.history or []:
            try:
                session.ask(turn.user)
            except Exception:
                # A stale turn must not break the new one.
                continue

        result = session.ask(request.message)
        return {
            "message": result.assistant_text,
            "intent": result.intent.value,
            "ok": result.ok,
            "referenced": result.referenced,
            "brief_changes": result.brief_changes,
            "brief": session.brief.as_dict(),
            "can_undo": session.can_undo,
            "system": session.system.model_dump(),
            "turn": result.as_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class BriefRequest(BaseModel):
    """Request body for parsing statements into a design brief."""

    statements: list[str]


@app.post("/api/ai/brief")
async def ai_brief(request: BriefRequest):
    """
    Parse requirement statements into a structured design brief.

    Use this to accumulate constraints from terse fragments such as
    "5x magnification", "at f/2.8", "for visible wavelengths".
    """
    from ai.conversation import DesignBrief

    brief = DesignBrief()
    changes = []
    for statement in request.statements:
        changes.extend(brief.update_from_text(statement))
    return {
        "brief": brief.as_dict(),
        "changes": changes,
        "context_note": brief.to_context_note(),
    }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class VerifyClaimsRequest(BaseModel):
    """Request body for verifying stated claims about a system."""

    system: OpticalSystem
    claims: list[str]
    tolerance: Optional[float] = None


@app.post("/api/ai/verify/claims")
async def ai_verify_claims(request: VerifyClaimsRequest):
    """
    Verify numeric claims against the validated optics engine.

    Recognises claims about EFL, magnification, f-number, RMS spot radius
    and the diffraction-limited condition. Every value is re-derived, so
    the AI can never assert an unverified number.
    """
    from ai.verification import verify_claims, CLAIM_TOLERANCE

    try:
        tol = request.tolerance if request.tolerance is not None else CLAIM_TOLERANCE
        results = verify_claims(request.system, request.claims, tol)
        return {
            "results": [r.as_dict() for r in results],
            "all_verified": all(r.verified for r in results),
            "tolerance": tol,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class PrescriptionVerifyRequest(BaseModel):
    """Request body for reference-prescription comparison."""

    system: OpticalSystem
    tolerance: Optional[float] = None


@app.post("/api/ai/verify/prescription")
async def ai_verify_prescription(request: PrescriptionVerifyRequest):
    """
    Compare a design against the classic reference prescriptions.

    Reports the closest reference (Cooke triplet, Double Gauss, Tessar,
    Petzval, telephoto, retrofocus, ...) together with the EFL, f-number
    and element-count deltas.
    """
    from ai.verification import verify_prescription

    try:
        tol = request.tolerance if request.tolerance is not None else 0.25
        comparison = verify_prescription(request.system, tol)
        return comparison.as_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DesignRulesRequest(BaseModel):
    """Request body for manufacturability rule checks."""

    system: OpticalSystem


@app.post("/api/ai/design-rules")
async def ai_design_rules(request: DesignRulesRequest):
    """
    Run manufacturability rule checks on a design.

    Checks catalog glass availability, minimum edge thickness, minimum
    centre thickness, and element diameter/thickness aspect ratio.
    """
    from ai.verification import rule_check_summary

    try:
        return rule_check_summary(request.system)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class FullVerifyRequest(BaseModel):
    """Request body for the combined verification report."""

    system: OpticalSystem
    claims: Optional[list[str]] = None
    tolerance: Optional[float] = None


@app.post("/api/ai/verify/full")
async def ai_verify_full(request: FullVerifyRequest):
    """
    Run rule checks, prescription comparison and claim verification
    in a single call and return the combined report.
    """
    from ai.verification import full_verification

    try:
        return full_verification(request.system, request.claims)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/ai/providers")
async def ai_providers():
    """
    Report which LLM providers are configured and available.

    The application works fully offline; the rule-based interpreter is
    always available, and an LLM provider is optional.
    """
    from ai.providers import ProviderConfig, ProviderChain

    try:
        config = ProviderConfig.from_env()
        chain = ProviderChain.from_config(config)
        available = [p for p in chain.providers if p.is_available()]
        return {
            "configured_provider": config.provider,
            "model": config.model,
            "base_url": config.base_url,
            "enabled": config.enabled,
            "available": [p.name for p in available],
            "active": chain.available_provider(),
            "rule_based_fallback": True,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
