"""
Structured commands for the AI abstraction layer.

These Pydantic models define the structured commands that an LLM (or
any AI provider) can emit. The AI never performs optical calculations
directly; it only emits these commands, which are validated and applied
by the optics engine (see engine.py).

All length values are in meters (SI base unit).
"""

from typing import Literal, Optional, Union, Annotated

from pydantic import BaseModel, Field

from optics.models import OpticalComponent


# ---------------------------------------------------------------------------
# Component Commands
# ---------------------------------------------------------------------------

class ModifyComponentCommand(BaseModel):
    """
    Modify a property of an existing component.

    Example: change the focal length of lens_1 to 75mm.
    """

    action: Literal["modify_component"] = "modify_component"
    component_id: str = Field(..., description="ID of the component to modify")
    field: str = Field(..., description="Field to modify (e.g. 'position', 'focal_length')")
    value: float = Field(..., description="New value (meters for lengths)")


class AddComponentCommand(BaseModel):
    """
    Add a new component to the system.

    The component is a full OpticalComponent model (ThinLens,
    SphericalSurface, ApertureStop, or Mirror).
    """

    action: Literal["add_component"] = "add_component"
    component: OpticalComponent = Field(..., description="The component to add")


class RemoveComponentCommand(BaseModel):
    """
    Remove a component from the system by ID.
    """

    action: Literal["remove_component"] = "remove_component"
    component_id: str = Field(..., description="ID of the component to remove")


# ---------------------------------------------------------------------------
# Object and Image Plane Commands
# ---------------------------------------------------------------------------

class SetObjectCommand(BaseModel):
    """
    Set the object position and/or height.

    Example: move the object to 50mm with a height of 5mm.
    """

    action: Literal["set_object"] = "set_object"
    position: Optional[float] = Field(None, description="Object position (meters)")
    height: Optional[float] = Field(None, description="Object height (meters)")


class SetImagePlaneCommand(BaseModel):
    """
    Set the image plane position.

    Example: move the image plane to 200mm.
    """

    action: Literal["set_image_plane"] = "set_image_plane"
    position: float = Field(..., description="Image plane position (meters)")


# ---------------------------------------------------------------------------
# Analysis and Optimization Commands
# ---------------------------------------------------------------------------

class AnalyzeCommand(BaseModel):
    """
    Analyze the current system.

    Returns the full AnalysisResult from the optics engine.
    """

    action: Literal["analyze"] = "analyze"


class OptimizeCommand(BaseModel):
    """
    Optimize a set of system parameters.

    Uses the optics engine's optimization module (SciPy-based) to find
    parameter values that minimize an objective.

    Example: optimize lens_1's focal length to achieve a magnification of -2.
    """

    action: Literal["optimize"] = "optimize"
    objective: Literal["rms_spot", "magnification", "efl"] = Field(
        ..., description="Objective to minimize"
    )
    target: Optional[float] = Field(
        None, description="Target value for 'magnification' or 'efl' objectives"
    )
    params: list[dict] = Field(
        ..., description="List of parameter specs (see optimization._set_parameter)"
    )
    bounds: list[list[float]] = Field(
        ..., description="List of [min, max] bounds, one per parameter (meters)"
    )


# ---------------------------------------------------------------------------
# Explanation and Troubleshooting Commands
# ---------------------------------------------------------------------------

class ExplainCommand(BaseModel):
    """
    Produce a rich natural-language explanation of the current system.

    The AI itself does not perform any optical calculations. The engine
    computes all metrics from the validated optics modules and builds an
    educational explanation of what the numbers mean.
    """

    action: Literal["explain"] = "explain"


class DiagnoseCommand(BaseModel):
    """
    Troubleshoot the current optical system.

    The engine inspects the validated system for common issues (ignoring
    the LLM entirely) and returns a list of findings with concrete,
    actionable suggestions.
    """

    action: Literal["diagnose"] = "diagnose"


# ---------------------------------------------------------------------------
# Discriminated Union
# ---------------------------------------------------------------------------

AICommand = Annotated[
    Union[
        ModifyComponentCommand,
        AddComponentCommand,
        RemoveComponentCommand,
        SetObjectCommand,
        SetImagePlaneCommand,
        AnalyzeCommand,
        OptimizeCommand,
        ExplainCommand,
        DiagnoseCommand,
    ],
    Field(discriminator="action"),
]