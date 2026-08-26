"""
Command engine for the AI abstraction layer.

This module validates and applies structured AI commands to the optics
engine. It is the ONLY place where AI commands are translated into
optics-engine operations. The AI never performs optical calculations
directly; it only emits structured commands that are validated here.

All length values are in meters (SI base unit).
"""

from typing import Union

from optics.models import OpticalSystem, AnalysisResult
from optics.systems import (
    add_component, remove_component, update_component,
    sort_components, validate_system,
)
from optics.analysis import analyze_system
from optics.optimization import (
    optimize_system as run_optimization,
    minimize_rms_spot, target_magnification, target_efl,
)

from .commands import (
    AICommand, ModifyComponentCommand, AddComponentCommand,
    RemoveComponentCommand, SetObjectCommand, SetImagePlaneCommand,
    AnalyzeCommand, OptimizeCommand, ExplainCommand, DiagnoseCommand,
)
from .explanations import explain_system, diagnose_system


# ---------------------------------------------------------------------------
# Command Application
# ---------------------------------------------------------------------------

def apply_command(system: OpticalSystem, command: AICommand) -> OpticalSystem:
    """
    Apply a single command to the system and return the updated system.

    This function only modifies the system; it does not run analysis.
    For commands that produce results (analyze, optimize), use
    execute_command instead.

    Args:
        system: The optical system.
        command: The structured AI command to apply.

    Returns:
        The updated OpticalSystem.

    Raises:
        ValueError: If the command is invalid (e.g. component not found).
    """
    if isinstance(command, ModifyComponentCommand):
        return update_component(system, command.component_id, **{command.field: command.value})

    if isinstance(command, AddComponentCommand):
        return add_component(system, command.component)

    if isinstance(command, RemoveComponentCommand):
        return remove_component(system, command.component_id)

    if isinstance(command, SetObjectCommand):
        updates = {}
        if command.position is not None:
            updates["position"] = command.position
        if command.height is not None:
            updates["height"] = command.height
        if not updates:
            raise ValueError("set_object requires at least one of position or height.")
        return system.model_copy(
            update={"object": system.object.model_copy(update=updates)}
        )

    if isinstance(command, SetImagePlaneCommand):
        return system.model_copy(
            update={"image_plane": system.image_plane.model_copy(update={"position": command.position})}
        )

    if isinstance(command, AnalyzeCommand):
        # Analyze does not modify the system
        return system

    if isinstance(command, OptimizeCommand):
        # Optimize returns a new system; handled in execute_command
        return system

    if isinstance(command, (ExplainCommand, DiagnoseCommand)):
        # Explanation / diagnosis do not modify the system
        return system

    raise ValueError(f"Unknown command type: {type(command).__name__}")


def execute_command(
    system: OpticalSystem, command: AICommand
) -> dict:
    """
    Execute a command and return a result dict.

    For system-modifying commands, returns the updated system plus
    validation warnings. For analyze/optimize commands, returns the
    analysis result or optimization result.

    Args:
        system: The optical system.
        command: The structured AI command to execute.

    Returns:
        Dict with keys:
            - "system": the (possibly updated) OpticalSystem
            - "warnings": list of validation warnings
            - "result": optional result (AnalysisResult or optimization dict)
            - "message": human-readable summary of what was done

    Raises:
        ValueError: If the command is invalid.
    """
    if isinstance(command, AnalyzeCommand):
        result = analyze_system(system)
        warnings = validate_system(system)

        # Build a natural-language explanation of the analysis result
        efl_mm = result.effective_focal_length * 1000
        mag = result.magnification
        f_num = result.f_number
        rms_um = result.rms_spot_radius * 1e6
        real = "real" if result.is_image_real else "virtual"
        inverted = "inverted" if result.is_image_inverted else "upright"

        message = (
            f"Analysis complete. Effective focal length: {efl_mm:.1f} mm. "
            f"Magnification: {mag:.2f} ({inverted}). "
            f"F-number: {f_num:.1f}. "
            f"RMS spot radius: {rms_um:.2f} um. "
            f"Image is {real}."
        )
        return {
            "system": system,
            "warnings": warnings,
            "result": result,
            "message": message,
        }

    if isinstance(command, OptimizeCommand):
        # Build the objective function
        if command.objective == "rms_spot":
            objective = minimize_rms_spot
        elif command.objective == "magnification":
            if command.target is None:
                raise ValueError("OptimizeCommand with objective='magnification' requires a target.")
            objective = lambda s: target_magnification(s, command.target)
        elif command.objective == "efl":
            if command.target is None:
                raise ValueError("OptimizeCommand with objective='efl' requires a target.")
            objective = lambda s: target_efl(s, command.target)
        else:
            raise ValueError(f"Unknown objective: {command.objective}")

        # Convert bounds from list[list[float]] to list[tuple[float, float]]
        bounds = [(b[0], b[1]) for b in command.bounds]

        opt_result = run_optimization(
            system,
            objective,
            params=command.params,
            bounds=bounds,
        )
        optimized = opt_result["system"]
        warnings = validate_system(optimized)
        return {
            "system": optimized,
            "warnings": warnings,
            "result": opt_result,
            "message": (
                f"Optimization complete. Objective: {opt_result['objective']:.6g}. "
                f"Params: {[f'{p:.6g}' for p in opt_result['params']]}"
            ),
        }

    if isinstance(command, ExplainCommand):
        explanation = explain_system(system)
        message = " ".join(explanation["parts"])
        return {
            "system": system,
            "warnings": [],  # detailed warnings live in the explanation
            "result": explanation,
            "message": message,
        }

    if isinstance(command, DiagnoseCommand):
        diagnosis = diagnose_system(system)
        # Summarize findings into a single message
        parts = []
        for f in diagnosis["findings"]:
            parts.append(f"[{f['level']}] {f['message']} -> {f['suggestion']}")
        message = " ".join(parts) or diagnosis["summary"]
        return {
            "system": system,
            "warnings": diagnosis["findings"],
            "result": diagnosis,
            "message": message,
        }

    # System-modifying command
    updated = apply_command(system, command)
    # Sort components by position for consistency
    updated = sort_components(updated)
    warnings = validate_system(updated)

    # Build a human-readable message
    if isinstance(command, ModifyComponentCommand):
        message = f"Modified {command.component_id}.{command.field} = {command.value:.6g}."
    elif isinstance(command, AddComponentCommand):
        message = f"Added component '{command.component.id}'."
    elif isinstance(command, RemoveComponentCommand):
        message = f"Removed component '{command.component_id}'."
    elif isinstance(command, SetObjectCommand):
        message = "Set object."
    elif isinstance(command, SetImagePlaneCommand):
        message = f"Set image plane to {command.position:.6g}."
    else:
        message = "Command applied."

    return {
        "system": updated,
        "warnings": warnings,
        "result": None,
        "message": message,
    }