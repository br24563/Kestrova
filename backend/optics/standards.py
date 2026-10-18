"""
Industry Standards and Workflows for Optical Design.

Implements Zemax/Code V-style production workflows:
- Zemax tolerance operand names (TRAD, TCUR, TFRN, TTHI, TCON, TSDX/Y,
  TSTX/Y, TIRR, TEXI, TEDX/Y, TETX/Y, TIND, TABB)
- PartBuilder: lens element from focal length, shape and thickness
  (exact thick-lens solution)
- Lens Data Editor (surface table model)
- Merit Function Editor (ordered operand rows)
- Inverse sensitivity tolerancing (specify performance, solve tolerances)
- Automatic compensator selection
- Multiple unit system support

All length values are in meters unless a unit is explicitly given.
"""

import math
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .models import OpticalSystem, ThinLens, ThickLens, ApertureStop, Ray
from .analysis import analyze_system
from .systems import update_component
from .tolerance import ToleranceSpec, tolerance_analysis, compute_yield
from .units import LENGTH_UNITS, convert

# =============================================================================
# Zemax-style Tolerance Operands
# =============================================================================


class OperandType(str, Enum):
    """Zemax OpticStudio tolerance operand names."""

    TRAD = "TRAD"  # radius
    TCUR = "TCUR"  # curvature
    TFRN = "TFRN"  # radius as power fringes
    TTHI = "TTHI"  # thickness / spacing
    TCON = "TCON"  # conic constant
    TSDX = "TSDX"  # surface decenter x
    TSDY = "TSDY"  # surface decenter y
    TSTX = "TSTX"  # surface tilt about x
    TSTY = "TSTY"  # surface tilt about y
    TIRR = "TIRR"  # surface irregularity
    TEXI = "TEXI"  # surface irregularity (Zernike)
    TEDX = "TEDX"  # element decenter x
    TEDY = "TEDY"  # element decenter y
    TETX = "TETX"  # element tilt about x
    TETY = "TETY"  # element tilt about y
    TIND = "TIND"  # index of refraction
    TABB = "TABB"  # Abbe number


_ANGULAR_OR_DIMENSIONLESS = {
    "TIND",
    "TABB",
    "TCON",
    "TFRN",
    "TIRR",
    "TEXI",
    "TSTX",
    "TSTY",
    "TETX",
    "TETY",
}


@dataclass
class ToleranceOperand:
    """A single Zemax-style tolerance operand."""

    op_type: OperandType
    surface: int = 0  # Surface number (1-based, 0 = all/element)
    value: float = 0.0  # Tolerance value (units depend on op_type)
    unit: str = "mm"  # Unit for the value
    distribution: str = "gaussian"  # gaussian, uniform, truncated
    compensator: bool = False  # Is this a compensator?
    min_val: float = 0.0
    max_val: float = 0.0

    def to_si(self) -> float:
        """Convert the tolerance value to SI base units (meters)."""
        if self.op_type.value in _ANGULAR_OR_DIMENSIONLESS:
            return self.value  # dimensionless, fringes or radians
        if self.unit in LENGTH_UNITS:
            return convert(self.value, self.unit, "m")
        return self.value


# =============================================================================
# PartBuilder: Parametric Lens Element Generator
# =============================================================================

_SHAPE_FACTOR = {
    "biconvex": 0.0,
    "biconcave": 0.0,
    "plano_convex": 1.0,
    "plano_concave": 1.0,
    "meniscus": 2.0,
}


@dataclass
class PartDefinition:
    """
    A lens element defined by focal length, shape, thickness and glass.

    The shape is the Coddington shape factor X = (c1 + c2)/(c1 - c2)
    (biconvex/biconcave 0, plano 1 with the curved side first, meniscus 2
    by default; set ``shape_factor`` to override). The radii are solved
    exactly from the thick-lens power at the reference wavelength.
    """

    part_number: str = "LENS-001"
    shape: str = (
        "biconvex"  # biconvex, biconcave, meniscus, plano_convex, plano_concave
    )
    aperture_diameter: float = 0.025
    edge_thickness: float = 2.0e-3  # informational minimum; checked
    center_thickness: float = 5.0e-3
    focal_length: float = 0.050
    material: str = "N-BK7"
    edge_chamfer: float = 0.2e-3
    shape_factor: Optional[float] = None
    wavelength: float = 587.5618e-9

    def _x(self) -> float:
        if self.shape_factor is not None:
            return self.shape_factor
        if self.shape not in _SHAPE_FACTOR:
            raise ValueError(f"Unknown shape '{self.shape}'")
        return _SHAPE_FACTOR[self.shape]

    def compute_radii(self, n: Optional[float] = None) -> tuple:
        """
        (R1, R2) giving the focal length at this thickness. A flat surface
        is returned as 1e10. Raises ValueError if no real solution exists.
        """
        from .materials import refractive_index

        if n is None:
            n = refractive_index(self.material, self.wavelength)
        f = self.focal_length
        if not math.isfinite(f) or abs(f) < 1e-15:
            raise ValueError("A part needs a finite, non-zero focal length")
        if self.shape in ("biconvex", "plano_convex") and f < 0:
            raise ValueError(f"A {self.shape} element has positive power")
        if self.shape in ("biconcave", "plano_concave") and f > 0:
            raise ValueError(f"A {self.shape} element has negative power")
        X = self._x()
        t = self.center_thickness
        # c1 - c2 = K, c1 = K(X+1)/2, c2 = K(X-1)/2;
        # phi = (n-1)[K - (n-1) t c1 c2 / n]  ->  a K^2 - K + phi/(n-1) = 0
        phi = 1.0 / f
        a = (n - 1.0) * t * (X * X - 1.0) / (4.0 * n)
        b = phi / (n - 1.0)
        if abs(a) < 1e-300:
            K = b
        else:
            disc = 1.0 - 4.0 * a * b
            if disc < 0:
                raise ValueError("No real lens of this shape, thickness and power")
            K = 2.0 * b / (1.0 + math.sqrt(disc))  # root continuous with the thin lens
        c1, c2 = K * (X + 1.0) / 2.0, K * (X - 1.0) / 2.0
        return (1.0 / c1 if c1 else 1e10, 1.0 / c2 if c2 else 1e10)

    def sag_at_edge(self) -> tuple:
        """Sags (front, back) at the clear semi-aperture, signed toward +z."""
        r1, r2 = self.compute_radii()
        h = self.aperture_diameter / 2.0

        def sag(R):
            if abs(R) >= 1e9:
                return 0.0
            if abs(R) < h:
                raise ValueError("Radius smaller than the semi-aperture")
            return R - math.copysign(math.sqrt(R * R - h * h), R)

        return sag(r1), sag(r2)

    def actual_edge_thickness(self) -> float:
        s1, s2 = self.sag_at_edge()
        return self.center_thickness - s1 + s2

    def to_component(self, component_id: str, position: float):
        """ThickLens with the solved radii; raises if the edge is too thin."""
        r1, r2 = self.compute_radii()
        edge = self.actual_edge_thickness()
        if edge < self.edge_thickness:
            raise ValueError(
                f"Edge thickness {edge * 1e3:.3f} mm is below the required "
                f"{self.edge_thickness * 1e3:.3f} mm; increase centre thickness"
            )
        return ThickLens(
            id=component_id,
            position=position,
            radius1=r1,
            radius2=r2,
            thickness=self.center_thickness,
            aperture_diameter=self.aperture_diameter,
            material=self.material,
        )


def build_part_from_spec(spec: dict) -> PartDefinition:
    """Build a PartDefinition from a dictionary specification."""
    return PartDefinition(
        part_number=spec.get("part_number", "LENS-001"),
        shape=spec.get("shape", "biconvex"),
        aperture_diameter=spec.get("aperture_diameter", 0.025),
        edge_thickness=spec.get("edge_thickness", 2.0e-3),
        center_thickness=spec.get("center_thickness", 5.0e-3),
        focal_length=spec.get("focal_length", 0.050),
        material=spec.get("material", "N-BK7"),
        edge_chamfer=spec.get("edge_chamfer", 0.2e-3),
        shape_factor=spec.get("shape_factor"),
    )


# =============================================================================
# Lens Data Editor (surface table model)
# =============================================================================


@dataclass
class SurfaceRow:
    """One row in the Lens Data Editor (surface table)."""

    surface: int
    comment: str = ""
    radius: float = 1e30
    thickness: float = 0.0
    glass: str = "AIR"
    semi_diameter: float = 12.5e-3
    conic: float = 0.0
    surface_type: str = "STANDARD"  # STANDARD, EVENASPH or PARAXIAL
    is_stop: bool = False
    paraxial_focal_length: Optional[float] = None  # PARAXIAL (ideal lens) only
    coating: str = ""
    decenter_x: float = 0.0
    decenter_y: float = 0.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0


class LensDataEditor:
    """Zemax-style Lens Data Editor backed by an optical system."""

    def __init__(self, system: Optional[OpticalSystem] = None):
        self.rows: list = []
        if system is not None:
            self.build_from_system(system)

    def build_from_system(self, system: OpticalSystem):
        """Populate the editor with the system's sequential surface table."""
        from .io.prescription import system_to_rows

        rows, obj_dist, fo = system_to_rows(system)
        self.rows = [
            SurfaceRow(
                surface=0,
                comment="OBJECT",
                thickness=obj_dist if not fo.object_infinite else 1e30,
                semi_diameter=abs(system.object.height),
            )
        ]
        for k, r in enumerate(rows, start=1):
            stype = (
                "PARAXIAL"
                if r.paraxial_focal_length is not None
                else ("EVENASPH" if r.asphere else "STANDARD")
            )
            self.rows.append(
                SurfaceRow(
                    surface=k,
                    comment=r.label,
                    radius=r.radius if r.radius else 1e30,
                    thickness=r.thickness,
                    glass=r.glass or "AIR",
                    semi_diameter=(
                        r.semi_aperture if r.semi_aperture is not None else 0.0
                    ),
                    conic=r.conic,
                    surface_type=stype,
                    is_stop=r.stop,
                    paraxial_focal_length=r.paraxial_focal_length,
                )
            )
        self.rows.append(
            SurfaceRow(
                surface=len(self.rows),
                comment="IMAGE",
                semi_diameter=(
                    abs(fo.image_height) if math.isfinite(fo.image_height) else 0.0
                ),
            )
        )
        return self.rows

    def to_dicts(self) -> list:
        """Return rows as plain dictionaries (for API/UI serialization)."""
        return [row.__dict__ for row in self.rows]

    def summary_text(self) -> str:
        """Render the editor as an ASCII table."""
        header = "{:>4} {:>14} {:>12} {:>10} {:>12} {:>10} {}".format(
            "SURF", "RADIUS", "THICKNESS", "GLASS", "SEMI-DIA", "TYPE", "COMMENT"
        )
        lines = [header, "-" * len(header)]
        for r in self.rows:
            radius_str = "Inf" if abs(r.radius) > 1e20 else "{:.6g}".format(r.radius)
            lines.append(
                "{:>4} {:>14} {:>12} {:>10} {:>12} {:>10} {}".format(
                    "STO" if r.is_stop else r.surface,
                    radius_str,
                    "{:.6g}".format(r.thickness),
                    r.glass,
                    "{:.6g}".format(r.semi_diameter),
                    r.surface_type,
                    r.comment,
                )
            )
        return "\n".join(lines)


# =============================================================================
# Merit Function Editor
# =============================================================================


@dataclass
class MeritOperandRow:
    """One row in the Merit Function Editor."""

    row: int
    operand: str = "RMS"  # e.g. RMS, EFFL, DIST, MTFT
    target: float = 0.0
    weight: float = 1.0
    value: float = 0.0
    contribution: float = 0.0
    comment: str = ""


# Operand name -> analysis field mapping
MERIT_OPERAND_MAP = {
    "RMS": "rms_spot_radius",
    "EFFL": "effective_focal_length",
    "BFL": "back_focal_length",
    "IMGD": "image_distance",
    "MAGN": "magnification",
    "FNum": "f_number",
    "NA": "numerical_aperture",
    "APER": "aperture_diameter",
    "WD": "working_distance",
}


class MeritFunctionEditor:
    """Zemax-style Merit Function Editor with ordered operand rows."""

    def __init__(self):
        self.rows: list = []

    def add(
        self, operand: str, target: float, weight: float = 1.0, comment: str = ""
    ) -> MeritOperandRow:
        """Append an operand row."""
        row = MeritOperandRow(
            row=len(self.rows),
            operand=operand,
            target=target,
            weight=weight,
            comment=comment,
        )
        self.rows.append(row)
        return row

    def evaluate(self, system: OpticalSystem) -> float:
        """Weighted sum of squared deviations; unknown operands raise."""
        from .analysis import back_focal_length

        analysis = analyze_system(system)
        total = 0.0
        for row in self.rows:
            field = MERIT_OPERAND_MAP.get(row.operand)
            if field is None:
                raise ValueError(
                    f"Unknown merit operand '{row.operand}'. "
                    f"Supported: {sorted(MERIT_OPERAND_MAP)}"
                )
            if field == "back_focal_length":
                row.value = float(back_focal_length(system))
            else:
                row.value = float(getattr(analysis, field))
            diff = row.value - row.target
            row.contribution = row.weight * diff * diff
            total += row.contribution
        return total

    def to_dicts(self) -> list:
        """Return rows as plain dictionaries."""
        return [row.__dict__ for row in self.rows]

    def summary_text(self, system: Optional[OpticalSystem] = None) -> str:
        """Render the editor as an ASCII table, optionally evaluated."""
        if system is not None:
            self.evaluate(system)
        header = "{:>4} {:>8} {:>16} {:>10} {:>16} {:>16} {}".format(
            "ROW", "TYPE", "TARGET", "WEIGHT", "VALUE", "CONTRIB", "COMMENT"
        )
        lines = [header, "-" * len(header)]
        for r in self.rows:
            lines.append(
                "{:>4} {:>8} {:>16.6g} {:>10.3g} {:>16.6g} {:>16.6g} {}".format(
                    r.row,
                    r.operand,
                    r.target,
                    r.weight,
                    r.value,
                    r.contribution,
                    r.comment,
                )
            )
        return "\n".join(lines)


# =============================================================================
# Sensitivity Analysis with Automatic Compensator Selection
# =============================================================================


def operand_to_parameter(op_type: OperandType, surface: int) -> Optional[str]:
    """Map a tolerance operand to a system parameter field."""
    if op_type == OperandType.TTHI:
        return "surface_{}_thickness".format(surface)
    if op_type in (OperandType.TRAD, OperandType.TCUR):
        return "surface_{}_radius".format(surface)
    if op_type == OperandType.TCON:
        return "surface_{}_conic".format(surface)
    if op_type == OperandType.TIND:
        return "surface_{}_index".format(surface)
    return None


def select_compensators(
    system: OpticalSystem,
    metric=None,
    max_compensators: int = 2,
) -> list:
    """
    Automatically select the most effective compensators.

    A compensator is a degree of freedom that can be adjusted at
    assembly time to recover performance (e.g. image-plane focus,
    an air gap). This ranks candidate compensators by how much
    they reduce the RMS spot radius.

    Args:
        system: The optical system.
        metric: Metric to minimize (default: RMS spot radius).
        max_compensators: Maximum number of compensators to return.

    Returns:
        List of dicts with keys: name, field, current, best,
        improvement.
    """
    if metric is None:
        metric = lambda s: analyze_system(s).rms_spot_radius

    base = metric(system)
    candidates = []

    # Candidate 1: image-plane focus shift
    candidates.append(("focus", "image_plane.position", system.image_plane.position))

    # Candidate 2: each lens position (air-space adjustment)
    for comp in system.components:
        if isinstance(comp, (ThinLens, ThickLens)):
            candidates.append(
                ("air_space_" + comp.id, comp.id + ".position", comp.position)
            )

    results = []
    for name, field, current in candidates:
        best_val = current
        best_metric = base
        # Scan +-2 mm around current value
        span = 2e-3
        for k in range(41):
            trial = current + span * (k / 40.0 - 0.5)
            try:
                if field == "image_plane.position":
                    cand = system.model_copy(
                        update={
                            "image_plane": system.image_plane.model_copy(
                                update={"position": trial}
                            )
                        }
                    )
                else:
                    comp_id, attr = field.split(".")
                    cand = update_component(system, comp_id, **{attr: trial})
                val = metric(cand)
            except Exception:
                continue
            if val < best_metric:
                best_metric = val
                best_val = trial
        improvement = (base - best_metric) / base if base > 0 else 0.0
        results.append(
            {
                "name": name,
                "field": field,
                "current": current,
                "best": best_val,
                "improvement": improvement,
            }
        )

    results.sort(key=lambda r: r["improvement"], reverse=True)
    return results[:max_compensators]


# =============================================================================
# Inverse Sensitivity Tolerancing
# =============================================================================


def inverse_sensitivity_tolerance(
    system: OpticalSystem,
    operand: ToleranceOperand,
    target_degradation: float,
    parameter: Optional[str] = None,
    metric=None,
    tol_min: float = 1e-6,
    tol_max: float = 1e-3,
    iterations: int = 20,
) -> dict:
    """
    Solve for the maximum tolerance that meets a performance budget.

    Given a target performance degradation (e.g. RMS spot may grow by
    10%), this bisects on the tolerance value to find the largest
    tolerance that stays within budget. This is the inverse of the
    traditional forward tolerancing workflow.

    Args:
        system: The optical system.
        operand: The tolerance operand to solve for.
        target_degradation: Allowed fractional degradation (e.g. 0.1 = 10%).
        parameter: Parameter to perturb, e.g. "L1.position" (see
            optics.tolerance). Both signs of the error are checked.
        metric: Performance metric (default: RMS spot radius).
        tol_min: Minimum search bound.
        tol_max: Maximum search bound.
        iterations: Number of bisection steps.

    Returns:
        Dict with solved tolerance, nominal/perturbed metrics, and status.
    """
    if metric is None:
        metric = lambda s: analyze_system(s).rms_spot_radius

    base = metric(system)
    budget = base * (1.0 + target_degradation)

    if parameter is None:
        raise ValueError("inverse_sensitivity_tolerance needs the parameter to perturb")
    from .tolerance import perturb

    def apply_tol(tol):
        # worst of the two signs of the error
        return [perturb(system, parameter, tol), perturb(system, parameter, -tol)]

    def worst(tol):
        vals = []
        for cand in apply_tol(tol):
            try:
                vals.append(metric(cand))
            except ValueError:
                vals.append(float("inf"))
        return max(vals)

    lo = tol_min
    hi = tol_max
    solved = tol_min

    if worst(tol_min) > budget:
        solved = 0.0
    else:
        for _ in range(iterations):
            mid = 0.5 * (lo + hi)
            if worst(mid) <= budget:
                solved = mid
                lo = mid
            else:
                hi = mid
    final_metric = worst(solved) if solved > 0 else base

    return {
        "operand": operand.op_type.value,
        "surface": operand.surface,
        "solved_tolerance": solved,
        "nominal_metric": base,
        "budget_metric": budget,
        "perturbed_metric": final_metric,
        "within_budget": final_metric <= budget,
        "target_degradation": target_degradation,
        "hit_search_limit": solved >= tol_max * (1 - 1e-6),
    }


def build_tolerance_operands(
    default_tol_mm: float = 0.1,
    n_surfaces: int = 0,
    include_decenter: bool = True,
    include_tilt: bool = True,
    include_index: bool = True,
) -> list:
    """
    Build a standard set of tolerance operands for a system.

    Returns a list of ToleranceOperand covering radius, thickness,
    and (optionally) decenter, tilt, and index tolerances for each
    surface.
    """
    ops = []
    for s in range(1, n_surfaces + 1):
        ops.append(
            ToleranceOperand(
                OperandType.TRAD, surface=s, value=default_tol_mm, unit="mm"
            )
        )
        ops.append(
            ToleranceOperand(
                OperandType.TTHI, surface=s, value=default_tol_mm, unit="mm"
            )
        )
        if include_index:
            ops.append(
                ToleranceOperand(OperandType.TIND, surface=s, value=0.001, unit="")
            )
        if include_decenter:
            ops.append(
                ToleranceOperand(
                    OperandType.TEDX, surface=s, value=default_tol_mm, unit="mm"
                )
            )
            ops.append(
                ToleranceOperand(
                    OperandType.TEDY, surface=s, value=default_tol_mm, unit="mm"
                )
            )
        if include_tilt:
            ops.append(
                ToleranceOperand(OperandType.TETX, surface=s, value=0.001, unit="rad")
            )
            ops.append(
                ToleranceOperand(OperandType.TETY, surface=s, value=0.001, unit="rad")
            )
    return ops


def operands_to_tolerance_specs(
    operands: list,
    component_ids: Optional[list] = None,
    system: Optional[OpticalSystem] = None,
) -> dict:
    """
    Convert tolerance operands into a tolerance_analysis spec dict.

    With a ``system``, operand surface numbers are sequential surface
    numbers of its prescription (1 = first surface): TRAD maps to the
    ThickLens radius1/radius2 of that surface and TTHI to the thickness (lens
    centre thickness, or the spacing to the next element via its position).
    Without a system, ``component_ids`` gives one component per operand
    surface number (element-level operands). Element decenters and tilts
    map to the element misalignments of optics.tolerance. Operand types the
    engine cannot perturb raise ValueError.
    """
    specs = {}
    rows = None
    if system is not None:
        from .io.prescription import system_to_rows

        rows, _, _ = system_to_rows(system)
    for op in operands:
        si = op.to_si()
        t = op.op_type
        if rows is not None:
            if not 1 <= op.surface <= len(rows):
                raise ValueError(f"Operand surface {op.surface} out of range")
            label = rows[op.surface - 1].label
            comp_id, _, part = label.partition(".")
        else:
            if not component_ids:
                raise ValueError("Give a system or component_ids")
            comp_id, part = (
                component_ids[min(op.surface - 1, len(component_ids) - 1)],
                "",
            )
        if t == OperandType.TRAD:
            if part not in ("front", "back"):
                raise ValueError(
                    f"TRAD on surface {op.surface} needs a ThickLens surface"
                )
            specs[f"{comp_id}.radius1" if part == "front" else f"{comp_id}.radius2"] = (
                si
            )
        elif t == OperandType.TTHI:
            specs[f"{comp_id}.thickness"] = si
        elif t == OperandType.TEDX:
            specs[f"{comp_id}.decenter_x"] = si
        elif t == OperandType.TEDY:
            specs[f"{comp_id}.decenter_y"] = si
        elif t == OperandType.TETX:
            specs[f"{comp_id}.tilt_x"] = si
        elif t == OperandType.TETY:
            specs[f"{comp_id}.tilt_y"] = si
        else:
            raise ValueError(f"Operand {t.value} cannot be perturbed by this engine")
    return specs


# =============================================================================
# Multiple Unit System Support
# =============================================================================

# Unit systems used by professional optical design software.
# Each entry maps a system name to its preferred unit for each quantity.
UNIT_SYSTEMS = {
    "metric": {"length": "mm", "wavelength": "nm", "angle": "deg"},
    "si": {"length": "m", "wavelength": "nm", "angle": "rad"},
    "english": {"length": "in", "wavelength": "um", "angle": "deg"},
    "micron": {"length": "um", "wavelength": "nm", "angle": "deg"},
}

# Additional length units used by professional tools
EXTRA_LENGTH_UNITS = {
    "in": 0.0254,
    "mil": 2.54e-5,
    "ft": 0.3048,
}


@dataclass
class UnitSystem:
    """A named unit system for display and input."""

    name: str = "metric"
    length: str = "mm"
    wavelength: str = "nm"
    angle: str = "deg"

    @classmethod
    def from_name(cls, name: str) -> "UnitSystem":
        """Build a UnitSystem from a known system name."""
        spec = UNIT_SYSTEMS.get(name, UNIT_SYSTEMS["metric"])
        return cls(
            name=name,
            length=spec["length"],
            wavelength=spec["wavelength"],
            angle=spec["angle"],
        )

    def to_display_length(self, value_m: float) -> float:
        """Convert a value in meters into this system's length unit."""
        if self.length in EXTRA_LENGTH_UNITS:
            return value_m / EXTRA_LENGTH_UNITS[self.length]
        return convert(value_m, "m", self.length)

    def from_display_length(self, value: float) -> float:
        """Convert a value in this system's length unit into meters."""
        if self.length in EXTRA_LENGTH_UNITS:
            return value * EXTRA_LENGTH_UNITS[self.length]
        return convert(value, self.length, "m")

    def to_display_wavelength(self, value_m: float) -> float:
        """Convert a wavelength in meters into this system's unit."""
        return convert(value_m, "m", self.wavelength)

    def to_display_angle(self, value_rad: float) -> float:
        """Convert an angle in radians into this system's unit."""
        return convert(value_rad, "rad", self.angle)


def convert_unit_system(value: float, from_unit: str, to_unit: str) -> float:
    """
    Convert a value between any supported length units.

    Extends the core units module with English/mil units used by
    professional optical design tools.
    """
    if from_unit in EXTRA_LENGTH_UNITS:
        value_m = value * EXTRA_LENGTH_UNITS[from_unit]
    else:
        value_m = convert(value, from_unit, "m")
    if to_unit in EXTRA_LENGTH_UNITS:
        return value_m / EXTRA_LENGTH_UNITS[to_unit]
    return convert(value_m, "m", to_unit)
