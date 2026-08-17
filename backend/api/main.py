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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add the backend directory to the Python path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from optics.models import (
    OpticalSystem, RayTraceResult, AnalysisResult,
)
from optics.systems import create_default_system, validate_system
from optics.rays import trace_system
from optics.analysis import analyze_system
from optics.aberration import chromatic_aberration_analysis
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

app = FastAPI(
    title="AI Optical Design Engineer API",
    description="A local-first optical design and ray-tracing engine.",
    version="0.1.0",
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for local development)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            "POST /api/validate": "Validate an optical system",
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
        provider = LocalLLMProvider()
        commands = provider.interpret(request.prompt)
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
            result=result["result"],
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
