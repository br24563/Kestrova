"""
Prescription verification and design-rule checking.

Two independent jobs live here:

1. ``verify_claim`` - the copilot may state numbers ("EFL is 100 mm",
   "f/2.8", "diffraction limited").  Every such claim is re-derived from
   the validated optics engine and either confirmed or contradicted with
   the actual computed value.  Nothing is ever asserted from memory.

2. ``verify_prescription`` - classify a design against the defining
   properties of classic lens types (element count, sequence of element
   powers, afocality, telephoto and retrofocus ratios) and run
   manufacturability rules (edge thickness, element aspect ratio, catalog
   glass availability). The design classes carry no numeric "reference"
   prescriptions: their focal lengths and speeds vary widely in practice.

Safety invariant: this module only reads from the optics engine.  It
never mutates a system and never fabricates a number.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from optics.models import OpticalSystem, ThinLens, ThickLens, ApertureStop
from optics.analysis import analyze_system
from optics.diffraction import diffraction_limited_check
from optics.seidel import seidel_analysis
from optics.materials_expanded import ALL_MATERIALS, get_material_properties
from .conversation import extract_numbers, number_before, number_after


# =============================================================================
# Reference design library
# =============================================================================

@dataclass
class ReferenceDesign:
    """
    A classic lens type, defined by structural properties (see
    R. Kingslake, *A History of the Photographic Lens*, 1989; W. J. Smith,
    *Modern Lens Design*, 2nd ed., 2005).
    """
    name: str
    n_elements: int
    power_signs: Optional[str] = None   # element power signs, front to back
    afocal: bool = False
    property: str = ""                  # extra defining condition, see _matches
    description: str = ""
    typical_use: str = ""


REFERENCE_DESIGNS = (
    ReferenceDesign("Singlet", 1, "+", description="Single positive element; "
                    "spherical aberration and colour uncorrected.",
                    typical_use="Condensers, laser focusing"),
    ReferenceDesign("Achromatic doublet", 2, "+-", property="achromat",
                    description="Crown and flint pair of opposite power correcting "
                                "primary axial colour.",
                    typical_use="General purpose imaging"),
    ReferenceDesign("Keplerian telescope", 2, "++", afocal=True,
                    description="Two positive groups separated by the sum of their "
                                "focal lengths; inverted image.",
                    typical_use="Astronomy, beam expansion"),
    ReferenceDesign("Galilean telescope", 2, "+-", afocal=True,
                    description="Positive objective with negative eyepiece; erect image.",
                    typical_use="Opera glasses, laser expanders"),
    ReferenceDesign("Cooke triplet", 3, "+-+",
                    description="Positive, negative, positive separated elements; "
                                "the classic three-element anastigmat.",
                    typical_use="General photography"),
    ReferenceDesign("Tessar", 4, "+-" + "-+", property="",
                    description="Triplet form with the rear element a cemented doublet.",
                    typical_use="Compact cameras, enlarging"),
    ReferenceDesign("Petzval lens", 4, property="two_groups",
                    description="Two separated positive groups; fast with strong "
                                "field curvature.",
                    typical_use="Portrait and projection lenses"),
    ReferenceDesign("Double Gauss", 6, property="",
                    description="Two near-symmetric Gauss groups about the stop.",
                    typical_use="Fast standard lenses"),
    ReferenceDesign("Telephoto", 2, property="telephoto",
                    description="Positive front group and negative rear group; total "
                                "length shorter than the focal length.",
                    typical_use="Long-focus photography"),
    ReferenceDesign("Retrofocus", 2, property="retrofocus",
                    description="Negative front group and positive rear group; back "
                                "focal distance longer than the focal length.",
                    typical_use="Wide-angle lenses with clearance behind the lens"),
)


# =============================================================================
# Claim verification
# =============================================================================

# Default tolerance for numeric claims (relative).
CLAIM_TOLERANCE = 0.01  # 1 percent


@dataclass
class ClaimResult:
    """Outcome of verifying a single stated claim."""
    claim: str
    kind: str
    verified: bool
    stated: Optional[float] = None
    actual: Optional[float] = None
    unit: str = ""
    error_pct: Optional[float] = None
    message: str = ""

    def as_dict(self) -> dict:
        """Return the result as a JSON-friendly dict."""
        return {
            "claim": self.claim,
            "kind": self.kind,
            "verified": self.verified,
            "stated": self.stated,
            "actual": self.actual,
            "unit": self.unit,
            "error_pct": self.error_pct,
            "message": self.message,
        }


def _rel_error(actual: float, stated: float) -> float:
    """Relative error between an actual and a stated value."""
    if stated == 0.0:
        return 0.0 if actual == 0.0 else float("inf")
    return abs(actual - stated) / abs(stated)


def _numeric_verdict(claim: str, kind: str, stated: float, actual: float,
                     unit: str, tolerance: float) -> ClaimResult:
    """Build a ClaimResult for a numeric claim."""
    err = _rel_error(actual, stated)
    ok = err <= tolerance
    if ok:
        msg = ("VERIFIED: " + kind + " is " + str(round(actual, 6)) + " " + unit
               + " (stated " + str(stated) + ", error " + str(round(err * 100.0, 4)) + "%).")
    else:
        msg = ("MISMATCH: stated " + kind + " = " + str(stated) + " " + unit
               + " but the engine computes " + str(round(actual, 6)) + " " + unit
               + " (error " + str(round(err * 100.0, 4)) + "%).")
    return ClaimResult(claim=claim, kind=kind, verified=ok, stated=stated,
                       actual=actual, unit=unit, error_pct=err * 100.0,
                       message=msg)


def verify_claim(system: OpticalSystem, claim: str,
                 tolerance: float = CLAIM_TOLERANCE) -> ClaimResult:
    """
    Verify a statement about the system against computed values.

    Recognises claims about effective focal length (mm), magnification,
    f-number, RMS spot radius (um), and the diffraction-limited condition.
    Every number is re-derived by the optics engine.
    """
    low = (claim or "").lower()
    result = analyze_system(system)

    # --- diffraction limited (boolean) ---
    if "diffraction limited" in low or "diffraction-limited" in low:
        dl = diffraction_limited_check(system)
        actual = bool(dl.get("is_diffraction_limited"))
        claims_negative = (("not " in low) or ("isn" + chr(39) + "t" in low)
                           or ("n" + chr(39) + "t " in low) or ("non-" in low))
        claimed = not claims_negative
        ok = (claimed == actual)
        if ok:
            msg = ("VERIFIED: the engine reports the system is "
                   + ("" if actual else "NOT ") + "diffraction limited (Strehl/RMS check).")
        else:
            msg = ("MISMATCH: the engine reports the system is "
                   + ("" if actual else "NOT ") + "diffraction limited.")
        return ClaimResult(claim=claim, kind="diffraction_limited", verified=ok,
                           message=msg)

    # --- effective focal length ---
    if "efl" in low or "focal length" in low:
        if "mm" in low:
            stated = number_before(low, "mm")
        elif " m" in low or low.rstrip().endswith("m"):
            stated = number_before(low, " m")
        else:
            nums = extract_numbers(low)
            stated = nums[0] if nums else None
        if stated is not None:
            if "mm" in low:
                actual = result.effective_focal_length * 1000.0
                unit = "mm"
            else:
                actual = result.effective_focal_length
                unit = "m"
            return _numeric_verdict(claim, "EFL", stated, actual, unit, tolerance)

    # --- magnification ---
    if "magnification" in low or low.rstrip().endswith("x") or "x " in low:
        stated = None
        for idx, ch in enumerate(low):
            if ch == "x" and idx > 0:
                prior = extract_numbers(low[max(0, idx - 10):idx])
                if prior:
                    stated = prior[-1]
                    break
        if stated is None:
            nums = extract_numbers(low)
            stated = nums[0] if nums else None
        if stated is not None:
            err = _rel_error(abs(result.magnification), abs(stated))
            if err <= tolerance and result.magnification * stated < 0:
                msg = ("VERIFIED with note: |magnification| is "
                       + str(round(abs(result.magnification), 6))
                       + " (stated " + str(abs(stated)) + "). The image is "
                       + ("inverted" if result.magnification < 0 else "erect")
                       + ", so the signed magnification is "
                       + str(round(result.magnification, 6)) + ".")
                return ClaimResult(claim=claim, kind="magnification", verified=True,
                                   stated=stated, actual=result.magnification,
                                   error_pct=err * 100.0, message=msg)
            return _numeric_verdict(claim, "magnification", stated,
                                    result.magnification, "", tolerance)

    # --- f-number ---
    if "f/" in low or "f-number" in low or "f number" in low or "fno" in low:
        if "f/" in low:
            stated = number_after(low, "f/")
        else:
            nums = extract_numbers(low)
            stated = nums[0] if nums else None
        if stated is not None:
            return _numeric_verdict(claim, "f-number", stated,
                                    result.f_number, "", tolerance)

    # --- RMS spot radius ---
    if "rms" in low or "spot" in low:
        if "um" in low or "micron" in low:
            stated = number_before(low, "um")
            actual = result.rms_spot_radius * 1e6
            unit = "um"
        else:
            nums = extract_numbers(low)
            stated = nums[0] if nums else None
            actual = result.rms_spot_radius * 1e6
            unit = "um"
        if stated is not None:
            return _numeric_verdict(claim, "RMS spot radius", stated, actual,
                                    unit, tolerance)

    return ClaimResult(
        claim=claim, kind="unknown", verified=False,
        message=("Could not parse a verifiable quantity from that claim. "
                 "Try: 'EFL is 100 mm', 'f/2.8', 'magnification is -1x', "
                 "'RMS spot is 10 um', 'the system is diffraction limited'."),
    )


def verify_claims(system: OpticalSystem, claims: list,
                  tolerance: float = CLAIM_TOLERANCE) -> list:
    """Verify several claims and return the list of ClaimResult objects."""
    return [verify_claim(system, c, tolerance) for c in claims]


# =============================================================================
# Design-rule checking (manufacturability)
# =============================================================================

@dataclass
class Finding:
    """A single design-rule finding."""
    rule: str
    level: str          # info | warning | error
    message: str
    surface: Optional[int] = None
    value: Optional[float] = None
    limit: Optional[float] = None

    def as_dict(self) -> dict:
        """Return the finding as a JSON-friendly dict."""
        return {
            "rule": self.rule, "level": self.level, "message": self.message,
            "surface": self.surface, "value": self.value, "limit": self.limit,
        }


# Manufacturability defaults used by the rule checks.
MIN_EDGE_THICKNESS_M = 1.0e-3     # 1.0 mm minimum edge
MAX_ASPECT_RATIO = 10.0           # diameter / centre thickness
MIN_CENTER_THICKNESS_M = 1.0e-3   # 1.0 mm minimum centre


def _element_geometry(comp):
    """(semi_aperture, centre thickness, r1, r2, material) of a ThickLens.
    Ideal thin lenses have no geometry and return None."""
    if isinstance(comp, ThickLens):
        return comp.aperture_diameter / 2.0, comp.thickness, comp.radius1, comp.radius2, comp.material
    return None


def _sag(radius: float, semi_aperture: float) -> float:
    """Signed sag (toward +z) of a sphere at the semi-aperture; ValueError if
    the semi-aperture exceeds the radius (the surface cannot exist there)."""
    if radius is None or abs(radius) > 1e9 or abs(radius) < 1e-12:
        return 0.0
    if semi_aperture >= abs(radius):
        raise ValueError("semi-aperture exceeds the surface radius")
    return radius - math.copysign(math.sqrt(radius * radius - semi_aperture * semi_aperture), radius)


def check_edge_thickness(system: OpticalSystem,
                         minimum: float = MIN_EDGE_THICKNESS_M) -> list:
    """Flag elements whose edge thickness is below the manufacturing floor."""
    findings = []
    surface = 0
    for comp in sorted(system.components, key=lambda c: c.position):
        geo = _element_geometry(comp)
        if geo is None:
            continue
        semi, thickness, r1, r2, material = geo
        surface += 1
        try:
            edge = thickness - _sag(r1, semi) + _sag(r2, semi)
        except ValueError:
            findings.append(Finding(
                rule="edge_thickness", level="error",
                message="Element " + comp.id + ": the clear aperture is larger than a "
                        "surface radius, so the lens cannot be made.",
                surface=surface))
            continue
        if edge < minimum:
            findings.append(Finding(
                rule="edge_thickness",
                level="error" if edge <= 0 else "warning",
                message=("Element " + comp.id + " edge thickness "
                         + str(round(edge * 1000.0, 3)) + " mm is below the "
                         + str(round(minimum * 1000.0, 3)) + " mm floor."),
                surface=surface, value=edge, limit=minimum,
            ))
    if not findings:
        findings.append(Finding(
            rule="edge_thickness", level="info",
            message="All element edge thicknesses meet the "
                    + str(round(minimum * 1000.0, 3)) + " mm floor.",
        ))
    return findings


def check_center_thickness(system: OpticalSystem,
                           minimum: float = MIN_CENTER_THICKNESS_M) -> list:
    """Flag elements thinner at the centre than the manufacturing floor."""
    findings = []
    for comp in sorted(system.components, key=lambda c: c.position):
        geo = _element_geometry(comp)
        if geo is None:
            continue
        thickness = geo[1]
        if thickness < minimum:
            findings.append(Finding(
                rule="center_thickness", level="warning",
                message=("Element " + comp.id + " centre thickness "
                         + str(round(thickness * 1000.0, 3)) + " mm is below the "
                         + str(round(minimum * 1000.0, 3)) + " mm floor."),
                value=thickness, limit=minimum,
            ))
    return findings


def check_element_aspect_ratio(system: OpticalSystem,
                                maximum: float = MAX_ASPECT_RATIO) -> list:
    """Flag elements that are too thin relative to their diameter."""
    findings = []
    for comp in sorted(system.components, key=lambda c: c.position):
        geo = _element_geometry(comp)
        if geo is None:
            continue
        semi, thickness, r1, r2, material = geo
        if thickness <= 0:
            continue
        ratio = (2.0 * semi) / thickness
        if ratio > maximum:
            findings.append(Finding(
                rule="aspect_ratio", level="warning",
                message=("Element " + comp.id + " diameter/thickness ratio "
                         + str(round(ratio, 2)) + " exceeds " + str(maximum) + "."),
                value=ratio, limit=maximum,
            ))
    return findings


def check_glass_availability(system: OpticalSystem) -> list:
    """Flag elements whose glass is not present in the catalog."""
    findings = []
    for comp in sorted(system.components, key=lambda c: c.position):
        material = getattr(comp, "material", None)
        if material is None:
            continue
        if material.lower() == "air":
            continue
        if get_material_properties(material) is None:
            findings.append(Finding(
                rule="glass_availability", level="error",
                message=("Element " + comp.id + " uses glass '" + str(material)
                         + "' which is not in the catalog.")
            ))
    if not findings:
        findings.append(Finding(
            rule="glass_availability", level="info",
            message="All element glasses are present in the catalog."
        ))
    return findings


def run_design_rule_checks(system: OpticalSystem) -> list:
    """Run every manufacturability rule check and return all findings."""
    findings = []
    findings.extend(check_glass_availability(system))
    findings.extend(check_edge_thickness(system))
    findings.extend(check_center_thickness(system))
    findings.extend(check_element_aspect_ratio(system))
    return findings


def rule_check_summary(system: OpticalSystem) -> dict:
    """Summarise design-rule findings by severity."""
    findings = run_design_rule_checks(system)
    counts = {"info": 0, "warning": 0, "error": 0}
    for f in findings:
        counts[f.level] = counts.get(f.level, 0) + 1
    return {
        "findings": [f.as_dict() for f in findings],
        "counts": counts,
        "passed": counts["error"] == 0 and counts["warning"] == 0,
    }


# =============================================================================
# Prescription comparison against reference designs
# =============================================================================

@dataclass
class PrescriptionComparison:
    """Result of comparing a design against the reference library."""
    closest: Optional[ReferenceDesign] = None
    score: float = float("inf")
    deltas: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    within_tolerance: bool = False
    summary: str = ""

    def as_dict(self) -> dict:
        """Return the comparison as a JSON-friendly dict."""
        return {
            "closest": self.closest.name if self.closest else None,
            "score": self.score,
            "deltas": dict(self.deltas),
            "notes": list(self.notes),
            "within_tolerance": self.within_tolerance,
            "summary": self.summary,
        }


def count_elements(system: OpticalSystem) -> int:
    """Number of refracting elements (thin or thick lenses)."""
    return len([c for c in system.components if isinstance(c, (ThinLens, ThickLens))])


def _element_powers(system: OpticalSystem) -> list:
    from optics import raytrace as rt
    wl = system.analysis_settings.wavelength
    out = []
    for c in sorted(system.components, key=lambda c: c.position):
        if isinstance(c, ThinLens):
            out.append((c, 1.0 / c.focal_length))
        elif isinstance(c, ThickLens):
            single = system.model_copy(update={"components": [c]})
            try:
                out.append((c, rt.first_order(single, wl).power))
            except ValueError:
                out.append((c, 0.0))
    return out


def _system_traits(system: OpticalSystem) -> dict:
    from optics import raytrace as rt
    seq = rt.build_sequence(system)
    fo = rt.first_order(system, seq=seq)
    powers = _element_powers(system)
    signs = "".join("+" if p > 0 else "-" for _, p in powers)
    first_z, last_z = seq.surfaces[0].z, seq.surfaces[-1].z
    efl = fo.efl
    total_power = sum(abs(p) for _, p in powers) or 1.0
    afocal = (not math.isfinite(efl)) or abs(fo.power) < 1e-3 * total_power
    traits = {"signs": signs, "afocal": bool(afocal), "efl": efl}
    if not afocal:
        rear_focal = fo.rear_focal_z
        traits["telephoto_ratio"] = abs(rear_focal - first_z) / abs(efl)
        traits["bfl_over_efl"] = abs(fo.bfl) / abs(efl)
    mats = [getattr(c, "material", None) for c, _ in powers]
    traits["materials"] = mats
    return traits


def _matches(ref: ReferenceDesign, n_elem: int, t: dict) -> tuple:
    """(matched, reasons) for one design class."""
    reasons = []
    if ref.afocal != t["afocal"]:
        return False, []
    if ref.property in ("telephoto", "retrofocus"):
        if t["afocal"] or n_elem < 2:
            return False, []
        if ref.property == "telephoto":
            ok = t["telephoto_ratio"] < 1.0 and t["signs"][0] == "+" and t["signs"][-1] == "-"
            reasons.append(f"telephoto ratio {t['telephoto_ratio']:.2f} < 1")
        else:
            ok = t["bfl_over_efl"] > 1.0 and t["signs"][0] == "-" and t["signs"][-1] == "+"
            reasons.append(f"back focus / EFL {t['bfl_over_efl']:.2f} > 1")
        return ok, reasons
    if n_elem != ref.n_elements:
        return False, []
    reasons.append(f"{n_elem} element(s)")
    if ref.power_signs is not None:
        if t["signs"] != ref.power_signs:
            return False, []
        reasons.append("power sequence " + t["signs"])
    if ref.property == "achromat":
        from optics.materials import abbe_number
        try:
            v = [abbe_number(m) for m in t["materials"]]
        except ValueError:
            return False, []
        if None in v or v[0] == v[1]:
            return False, []
        reasons.append("two glasses of different dispersion")
    if ref.property == "two_groups":
        if t["signs"].count("+") < 2:
            return False, []
    if ref.afocal:
        reasons.append("afocal")
    return True, reasons


def verify_prescription(system: OpticalSystem, tolerance: float = 0.25) -> PrescriptionComparison:
    """
    Identify which classic design classes the system belongs to from its
    structure (element count, power signs, afocality, telephoto/retrofocus
    ratios). ``tolerance`` is unused and kept for compatibility.
    """
    n_elem = count_elements(system)
    comparison = PrescriptionComparison()
    if n_elem == 0:
        comparison.summary = "No lens elements."
        return comparison
    t = _system_traits(system)
    matches = []
    for ref in REFERENCE_DESIGNS:
        ok, reasons = _matches(ref, n_elem, t)
        if ok:
            matches.append((ref, reasons))
    deltas = {"elements": n_elem, "power_signs": t["signs"], "afocal": t["afocal"]}
    if not t["afocal"]:
        deltas["efl_mm"] = t["efl"] * 1000.0
        deltas["telephoto_ratio"] = t["telephoto_ratio"]
        deltas["bfl_over_efl"] = t["bfl_over_efl"]
    comparison.deltas = deltas
    if not matches:
        comparison.score = float("inf")
        comparison.summary = ("No classic design class matches this structure "
                              f"({n_elem} elements, powers {t['signs']}"
                              + (", afocal" if t["afocal"] else "") + ").")
        return comparison
    best, reasons = matches[0]
    comparison.closest = best
    comparison.score = 0.0
    comparison.within_tolerance = True
    comparison.notes = (["Matches " + best.name + ": " + ", ".join(reasons) + "."]
                        + ["Also matches " + m.name + "." for m, _ in matches[1:]]
                        + ["Characteristic behaviour: " + best.description])
    comparison.summary = " ".join(comparison.notes)
    return comparison


def full_verification(system: OpticalSystem, claims: Optional[list] = None) -> dict:
    """Run claim verification, prescription comparison and rule checks."""
    out = {
        "rules": rule_check_summary(system),
        "prescription": verify_prescription(system).as_dict(),
    }
    if claims:
        out["claims"] = [c.as_dict() for c in verify_claims(system, claims)]
    return out
