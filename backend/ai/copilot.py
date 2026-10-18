"""
AI Copilot for Optical Design.

Features:
- Natural language to prescription conversion
- Explainability ("Why does MTF drop here?")
- Design suggestions with cited calculations
- "Verify this answer" workflows
- Design family recommendations

The AI never performs calculations directly - it uses the validated
optics engine and cites all results.
"""

from typing import Optional
from dataclasses import dataclass

from optics.models import OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings
from optics.analysis import analyze_system, effective_focal_length, system_magnification
from optics.systems import add_component, validate_system
from optics.aberration import chromatic_aberration_analysis
from optics.seidel import seidel_analysis
from optics.diffraction import diffraction_limited_check, airy_disk_radius
from optics.optimization import minimize_rms_spot


@dataclass
class CopilotResponse:
    """Response from the AI copilot."""
    answer: str
    citations: list[str]  # References to calculations performed
    # 1.0: every number in the answer was computed by the optics engine;
    # 0.5: rule-of-thumb guidance not checked by calculation;
    # 0.0: the request could not be handled.
    confidence: float
    suggested_actions: list[str]
    verified: bool  # Whether the answer has been verified by calculation


def explain_mtf_drop(system: OpticalSystem, field_point: float = 0.0) -> CopilotResponse:
    """
    Explain why MTF drops at a given field point.
    
    Args:
        system: The optical system
        field_point: Field angle in degrees
    
    Returns:
        CopilotResponse with explanation and citations
    """
    citations = []
    parts = []

    from optics.raytrace import first_order
    import math
    fo = first_order(system)
    if not math.isfinite(fo.image_z):
        mag = ("" if not math.isfinite(fo.efl) else f" (EFL {fo.efl*1000:.2f}mm)")
        return CopilotResponse(
            answer=("The image is at infinity" + mag + ", so the system is afocal in image "
                    "space: an MTF in image-plane cycles/mm, the Airy disk and Seidel image "
                    "aberrations are not defined for it. Its quality is described by the "
                    "angular (wavefront) aberrations of the output beam; add the eye or a "
                    "focusing lens behind it to analyze an image."),
            citations=["First-order trace: paraxial image at infinity"],
            confidence=1.0,
            suggested_actions=["Add an ideal lens after the system to form an image"],
            verified=True,
        )

    # Analyze the system
    analysis = analyze_system(system)
    citations.append(f"Analyzed system: EFL={analysis.effective_focal_length*1000:.2f}mm, f/{analysis.f_number:.1f}")
    
    # Check Seidel aberrations
    seidel = seidel_analysis(system)
    citations.append(f"Seidel analysis: SA={seidel['spherical_aberration']['longitudinal']*1e6:.2f}um")
    
    # Identify dominant aberration
    sa = abs(seidel['spherical_aberration']['longitudinal'])
    coma = abs(seidel['coma'])
    astig = abs(seidel['astigmatism'])
    
    if sa > coma and sa > astig:
        parts.append(f"Spherical aberration is dominant ({sa*1e6:.2f}um).")
        parts.append("This causes rays at different aperture heights to focus at different points.")
        parts.append("Solution: Use an aspheric surface or split the power across multiple elements.")
    elif coma > astig:
        parts.append(f"Coma is dominant ({coma*1e6:.2f}um).")
        parts.append("This causes off-axis points to appear comet-shaped.")
        parts.append("Solution: Add an aperture stop at the correct position or use a symmetric design.")
    else:
        parts.append(f"Astigmatism is dominant ({astig*1e6:.2f}um).")
        parts.append("This causes tangential and sagittal foci to be at different positions.")
        parts.append("Solution: Balance the power distribution or add field-flattening elements.")
    
    # Check diffraction limit
    dl = diffraction_limited_check(system)
    citations.append(f"Diffraction limit check (Marechal, Strehl >= 0.8): Strehl {dl['strehl_ratio']:.3f}, "
                     f"RMS wavefront {dl['rms_wavefront_waves']:.3f} waves; RMS spot "
                     f"{dl['rms_spot_radius']*1e6:.2f}um vs Airy radius {dl['airy_disk_radius']*1e6:.2f}um")
    
    if not dl['is_diffraction_limited']:
        parts.append("The system is NOT diffraction-limited (Strehl below 0.8), so aberrations, "
                     "not the aperture, limit the MTF.")
    
    return CopilotResponse(
        answer="\n".join(parts),
        citations=citations,
        confidence=1.0,
        suggested_actions=[
            "Run optimization to minimize RMS spot",
            "Check individual Seidel coefficients",
            "Consider adding aspheric surfaces",
        ],
        verified=True,
    )


def suggest_design_family(
    requirements: dict,
) -> CopilotResponse:
    """
    Suggest a design family based on requirements.
    
    Args:
        requirements: Dict with keys like 'magnification', 'f_number', 'field_of_view', 'wavelength'
    
    Returns:
        CopilotResponse with design suggestions
    """
    citations = []
    parts = []
    
    magnification = requirements.get('magnification', 1.0)
    f_number = requirements.get('f_number', 2.8)
    fov = requirements.get('field_of_view', 10.0)
    
    # Rule-based design family selection
    if magnification > 10:
        parts.append("For high magnification (>10x), consider a microscope objective design.")
        parts.append("Recommended: Two-element or three-element infinity-corrected objective.")
        citations.append("Based on magnification requirement: >10x")
    elif magnification < 0.1:
        parts.append("For high reduction (<0.1x), consider a telecentric lens design.")
        parts.append("Recommended: Multi-element telecentric objective.")
        citations.append("Based on magnification requirement: <0.1x")
    elif fov > 30:
        parts.append("For wide field of view (>30°), consider a retrofocus or Distagon design.")
        parts.append("Recommended: 6-element double-Gauss or retrofocus wide-angle.")
        citations.append("Based on FOV requirement: >30 degrees")
    elif f_number < 1.4:
        parts.append("For fast aperture (f/1.4 or faster), consider a Double-Gauss or Planar design.")
        parts.append("Recommended: 6-7 element Double-Gauss type.")
        citations.append("Based on f-number requirement: f/1.4 or faster")
    else:
        parts.append("For moderate requirements, consider a Doublet or Triplet design.")
        parts.append("Recommended: Achromatic doublet or Cooke triplet.")
        citations.append("Based on moderate requirements")
    
    return CopilotResponse(
        answer="\n".join(parts),
        citations=citations,
        confidence=0.5,
        suggested_actions=[
            "Load a preset design as starting point",
            "Set up merit function with appropriate operands",
            "Run hybrid optimization",
        ],
        verified=False,
    )


def natural_language_to_prescription(
    description: str,
) -> tuple[Optional[OpticalSystem], CopilotResponse]:
    """
    Convert natural language description to an optical prescription.
    
    Args:
        description: Natural language description of the desired system
    
    Returns:
        Tuple of (OpticalSystem or None, CopilotResponse with explanation)
    """
    import re
    
    citations = []
    parts = []
    
    # Parse common patterns
    magnification = None
    f_number = None
    focal_length = None
    n_elements = 2
    
    # Extract magnification
    mag_match = re.search(r'(\d+)\s*x\s*mag', description, re.IGNORECASE)
    if mag_match:
        magnification = float(mag_match.group(1))
        citations.append(f"Parsed magnification: {magnification}x")
    
    # Extract f-number
    fn_match = re.search(r'f[/\\](\d+\.?\d*)', description, re.IGNORECASE)
    if fn_match:
        f_number = float(fn_match.group(1))
        citations.append(f"Parsed f-number: f/{f_number}")
    
    # Extract focal length
    fl_match = re.search(r'(\d+)\s*mm\s*focal', description, re.IGNORECASE)
    if fl_match:
        focal_length = float(fl_match.group(1)) * 1e-3
        citations.append(f"Parsed focal length: {fl_match.group(1)}mm")
    
    # Extract number of elements
    elem_match = re.search(r'(\d+)\s*element', description, re.IGNORECASE)
    if elem_match:
        n_elements = int(elem_match.group(1))
        citations.append(f"Parsed element count: {n_elements}")
    
    # Build a first-order starting system from the parsed parameters
    # (ideal thin lenses, so it shows first-order behaviour only).
    if n_elements == 2 and (magnification is not None or focal_length is not None):
        wl = 550e-9
        if magnification is not None:
            # Telecentric 4f relay: object at the front focus of L1, image at
            # the back focus of L2, lenses separated by f1 + f2; m = -f2/f1.
            f1 = focal_length if focal_length is not None else 0.1
            f2 = magnification * f1
            d1 = f1
            components = [
                ThinLens(id="L1", position=d1, focal_length=f1,
                         aperture_diameter=(f1 / f_number) if f_number else 0.025, material="N-BK7"),
                ThinLens(id="L2", position=d1 + f1 + f2, focal_length=f2,
                         aperture_diameter=max(0.025, 2 * 0.005 * magnification), material="N-BK7"),
            ]
            image_z = d1 + f1 + 2 * f2
            object_height = 0.005
            parts.append(f"Created a 4f relay: f1={f1*1000:.1f}mm, f2={f2*1000:.1f}mm, "
                         f"magnification -f2/f1 = {-f2/f1:.3g}")
        else:
            # Two equal thin lenses of focal length 2f in contact have EFL f.
            f1 = f2 = 2.0 * focal_length
            far = 1.0e3
            d = (focal_length / f_number) if f_number else 0.025
            components = [
                ThinLens(id="L1", position=far, focal_length=f1, aperture_diameter=d, material="N-BK7"),
                ThinLens(id="L2", position=far + 1e-6, focal_length=f2, aperture_diameter=d, material="N-BK7"),
            ]
            image_z = far + focal_length
            object_height = 0.0
            parts.append(f"Created two thin lenses of f={f1*1000:.1f}mm in contact (EFL "
                         f"{focal_length*1000:.1f}mm) with the object effectively at infinity")
        system = OpticalSystem(
            components=components,
            wavelengths=[wl],
            object=Object(position=0.0, height=object_height, orientation=0.0),
            image_plane=ImagePlane(position=image_z),
            analysis_settings=AnalysisSettings(
                num_rays=11, ray_types=['chief', 'marginal', 'fill'],
                aperture_fraction=1.0, wavelength=wl),
        )
        try:
            from optics.raytrace import first_order
            fo = first_order(system)
            if abs(fo.image_z) < 1e9:
                system = system.model_copy(update={"image_plane": ImagePlane(position=fo.image_z)})
            citations.append(f"First-order trace: image at z={fo.image_z*1000:.2f}mm")
        except ValueError as exc:
            parts.append(f"First-order trace failed: {exc}")
        parts.append("Ideal thin lenses: this is a first-order starting point, not a corrected design.")

        return system, CopilotResponse(
            answer="\n".join(parts),
            citations=citations,
            confidence=1.0,
            suggested_actions=["Replace thin lenses with real elements", "Run optimization", "Analyze performance"],
            verified=False,
        )

    return None, CopilotResponse(
        answer=("Could not build a system: give a two-element request with a magnification "
                "('5x magnification') or a focal length ('50mm focal').") if n_elements == 2 else
               f"Only two-element starting systems are generated (requested {n_elements}).",
        citations=[],
        confidence=0.0,
        suggested_actions=["Try: 'Design a 5x magnification system at f/2.8'"],
        verified=False,
    )


def verify_calculation(
    system: OpticalSystem,
    claim: str,
) -> CopilotResponse:
    """
    Verify a claim about the optical system by running calculations.
    
    Args:
        system: The optical system
        claim: The claim to verify (e.g., "EFL is 100mm")
    
    Returns:
        CopilotResponse with verification result
    """
    import re
    
    citations = []
    
    # Parse claim
    efl_match = re.search(r'(?:EFL|focal\s*length)\s*(?:is|=)\s*(\d+\.?\d*)\s*mm', claim, re.IGNORECASE)
    if efl_match:
        claimed_efl = float(efl_match.group(1)) * 1e-3
        analysis = analyze_system(system)
        actual_efl = analysis.effective_focal_length
        
        citations.append(f"Claimed EFL: {claimed_efl*1000:.4f}mm")
        citations.append(f"Calculated EFL: {actual_efl*1000:.4f}mm")
        
        error = abs(actual_efl - claimed_efl) / claimed_efl * 100
        
        if error < 1.0:
            return CopilotResponse(
                answer=f"VERIFIED: EFL is {actual_efl*1000:.4f}mm (within {error:.2f}% of claim)",
                citations=citations,
                confidence=1.0,
                suggested_actions=[],
                verified=True,
            )
        else:
            return CopilotResponse(
                answer=f"MISMATCH: Claimed {claimed_efl*1000:.4f}mm but calculated {actual_efl*1000:.4f}mm ({error:.2f}% error)",
                citations=citations,
                confidence=1.0,
                suggested_actions=["Check system parameters", "Verify input values"],
                verified=True,
            )
    
    return CopilotResponse(
        answer="Could not parse the claim. Try: 'EFL is 100mm' or 'Magnification is -1x'",
        citations=[],
        confidence=0.0,
        suggested_actions=["Use format: 'EFL is XXmm'"],
        verified=False,
    )
