"""
Natural-language explanations and troubleshooting for optical systems.

This module builds educational explanations of an optical system from
the *validated optics engine* output. The AI (LLM or rule-based parser)
never performs optical calculations; all numbers come from the optics
modules, and this file only explains what they mean.

Two entry points are provided:

    - ``explain_system(system)`` -> dict with a multi-part message
    - ``diagnose_system(system)`` -> dict with a list of findings

All values are in SI base units (meters, radians).
"""

from typing import Optional

from optics.models import OpticalSystem
from optics.systems import validate_system
from optics.analysis import analyze_system
from optics.aberration import chromatic_aberration_analysis
from optics.seidel import seidel_analysis
from optics.diffraction import diffraction_limited_check

_MM = 1e-3
_UM = 1e-6


def _fmt_mm(value: float) -> str:
    """Format a length in meters as a string in mm."""
    return f"{value / _MM:.1f} mm"


def _fmt_um(value: float) -> str:
    """Format a length in meters as a string in um."""
    return f"{value / _UM:.2f} um"


# ---------------------------------------------------------------------------
# Explanation of the system
# ---------------------------------------------------------------------------


def explain_system(system: OpticalSystem) -> dict:
    """
    Build a rich, educational explanation of the current optical system.

    Args:
        system: The optical system.

    Returns:
        Dict with:
            - "summary": a one-line overview
            - "parts": list of plain-text explanatory sentences
            - "warnings": list of validation warnings
            - "metrics": dict of key numeric values (for UI display)
    """
    analysis = analyze_system(system)
    warnings = validate_system(system)

    efl_mm = analysis.effective_focal_length * 1000.0
    mag = analysis.magnification
    f_num = analysis.f_number
    na = analysis.numerical_aperture
    image_real = analysis.is_image_real
    image_inverted = analysis.is_image_inverted

    # Diffraction-limited check
    is_dl: Optional[bool] = None
    airy_um: Optional[float] = None
    strehl: Optional[float] = None
    try:
        dl = diffraction_limited_check(system)
        airy_um = dl["airy_disk_radius"] * 1e6
        is_dl = dl["is_diffraction_limited"]
        strehl = dl["strehl_ratio"]
    except Exception:
        pass

    # Chromatic aberration
    lca_mm: Optional[float] = None
    try:
        chroma = chromatic_aberration_analysis(system)
        lca_mm = chroma["lca"] * 1000.0
    except Exception:
        pass

    parts: list[str] = []

    if image_real:
        parts.append(
            f"This system forms a real image (it can be projected onto a "
            f"screen), located {_fmt_mm(analysis.image_distance)} beyond "
            f"the last surface."
        )
    else:
        parts.append(
            f"This system forms a virtual image (it cannot be projected "
            f"directly), located {_fmt_mm(abs(analysis.image_distance))} "
            f"before the last surface."
        )

    if image_inverted:
        parts.append(
            f"The image is inverted relative to the object "
            f"(magnification is {mag:.2f})."
        )
    else:
        parts.append(
            f"The image is upright relative to the object "
            f"(magnification is {mag:.2f})."
        )

    parts.append(
        f"The effective focal length is {_fmt_mm(analysis.effective_focal_length)} "
        f"and the working distance is {_fmt_mm(analysis.working_distance)}."
    )

    parts.append(
        f"The optical speed is f/{f_num:.1f} with a numerical aperture of "
        f"{na:.3f}. Smaller f-numbers admit more light (faster) but tend "
        f"to have more aberrations."
    )

    parts.append(
        f"The RMS spot radius at the image plane is {_fmt_um(analysis.rms_spot_radius)}."
    )

    if is_dl is not None:
        if is_dl:
            parts.append(
                f"The system is diffraction-limited on axis: its Strehl ratio "
                f"is {strehl:.3f}, at least 0.8 (the Marechal criterion), so "
                f"diffraction rather than aberration limits the image. The "
                f"Airy disk radius is {_fmt_um(airy_um or 0.0)}."
            )
        else:
            parts.append(
                f"The system is not diffraction-limited on axis: its Strehl "
                f"ratio is {strehl:.3f}, below the Marechal value 0.8, so "
                f"aberrations degrade the image beyond the diffraction limit "
                f"(Airy disk radius {_fmt_um(airy_um or 0.0)})."
            )

    if lca_mm is not None and abs(lca_mm) > 0.05:
        parts.append(
            f"There is noticeable longitudinal chromatic aberration "
            f"({_fmt_mm(lca_mm)}), so different colors focus at different "
            f"distances."
        )

    summary = f"EFL {efl_mm:.1f} mm, magnification {mag:.2f}, F/{f_num:.1f}"

    return {
        "summary": summary,
        "parts": parts,
        "warnings": warnings,
        "metrics": {
            "effective_focal_length_mm": efl_mm,
            "magnification": mag,
            "f_number": f_num,
            "numerical_aperture": na,
            "rms_spot_um": analysis.rms_spot_radius * 1e6,
            "is_image_real": image_real,
            "is_image_inverted": image_inverted,
            "airy_disk_um": airy_um,
            "strehl_ratio": strehl,
            "lca_mm": lca_mm,
        },
    }


# ---------------------------------------------------------------------------
# Troubleshooting
# ---------------------------------------------------------------------------


def diagnose_system(system: OpticalSystem) -> dict:
    """
    Troubleshoot the current system and produce actionable findings.

    All numbers come from the validated optics engine; this function
    only interprets them and suggests fixes.

    Args:
        system: The optical system.

    Returns:
        Dict with:
            - "findings": list of dicts with "level", "message", "suggestion"
            - "summary": one-line summary
    """
    findings: list[dict] = []

    # 1. Validation warnings
    warnings = validate_system(system)
    for w in warnings:
        findings.append(
            {
                "level": "warning",
                "message": f"Validation: {w}",
                "suggestion": "Review the component positions and parameters.",
            }
        )

    analysis = analyze_system(system)

    # 2. Image plane misalignment
    try:
        from optics.rays import calculate_paraxial_image_position

        paraxial_pos = calculate_paraxial_image_position(system)
        plane_pos = system.image_plane.position
        offset = paraxial_pos - plane_pos
        if abs(offset) > 1.0e-3:
            findings.append(
                {
                    "level": "recommendation",
                    "message": (
                        f"The image plane is {_fmt_mm(abs(offset))} away from "
                        f"the paraxial focus."
                    ),
                    "suggestion": (
                        f"Move the image plane to {paraxial_pos * 1000.0:.1f} mm "
                        f"for the sharpest image."
                    ),
                }
            )
    except Exception:
        pass

    # 3. RMS spot vs diffraction limit
    try:
        dl = diffraction_limited_check(system)
        if not dl["is_diffraction_limited"]:
            findings.append(
                {
                    "level": "recommendation",
                    "message": (
                        f"Strehl ratio {dl['strehl_ratio']:.3f} is below 0.8 "
                        f"(Marechal criterion); aberrations limit image quality."
                    ),
                    "suggestion": (
                        "Try a smaller aperture, optimize the lens positions, or "
                        "reduce the field height."
                    ),
                }
            )
    except Exception:
        pass

    # 4. Chromatic aberration
    try:
        chroma = chromatic_aberration_analysis(system)
        if abs(chroma["lca"]) > 1.0e-3:
            findings.append(
                {
                    "level": "recommendation",
                    "message": (
                        f"Longitudinal chromatic aberration of "
                        f"{_fmt_mm(chroma['lca'])} is noticeable."
                    ),
                    "suggestion": (
                        "Consider an achromatic doublet or a lower-dispersion "
                        "material."
                    ),
                }
            )
    except Exception:
        pass

    # 5. Spherical aberration (Seidel)
    try:
        seidel = seidel_analysis(system)
        sa_long = seidel["spherical_aberration"]["longitudinal"]
        if abs(sa_long) > 1.0e-3:
            findings.append(
                {
                    "level": "recommendation",
                    "message": (
                        f"Longitudinal spherical aberration of "
                        f"{_fmt_mm(sa_long)} is present."
                    ),
                    "suggestion": (
                        "Use an aspheric surface, shift the stop, or reduce the "
                        "aperture."
                    ),
                }
            )
    except Exception:
        pass

    if not findings:
        findings.append(
            {
                "level": "ok",
                "message": "No obvious problems found.",
                "suggestion": "The system looks well-formed.",
            }
        )

    return {"findings": findings, "summary": f"Found {len(findings)} finding(s)."}
