"""Glass Optimization for Professional Optical Design.

Implements glass selection and optimization capabilities.
"""

import random
from typing import Callable, Optional
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .models import OpticalSystem, ThinLens, ThickLens
from .materials_expanded import (
    ALL_MATERIALS,
    MaterialProperties,
    get_material_properties,
)
from .materials import refractive_index
from .analysis import analyze_system, effective_focal_length
from .systems import update_component


class GlassRegion(str, Enum):
    """Glass regions on the glass map (nd vs Vd)."""

    CROWN = "crown"
    FLINT = "flint"
    LANTHANUM = "lanthanum"
    ALL = "all"


@dataclass
class GlassCandidate:
    """A candidate glass for substitution."""

    name: str
    nd: float
    vd: float
    manufacturer: str
    material_type: str
    relative_price: Optional[float] = None  # vendor price index (reference glass = 1)
    distance_from_current: float = 0.0


@dataclass
class GlassSubstitutionResult:
    """Result of a glass substitution analysis."""

    original_glass: str
    candidate_glass: str
    system: OpticalSystem
    objective_change: float
    nd_change: float
    vd_change: float
    is_better: bool


@dataclass
class GlassExpertResult:
    """Result of glass expert optimization."""

    original_system: OpticalSystem
    optimized_system: OpticalSystem
    substitutions_made: list
    objective_before: float
    objective_after: float
    n_iterations: int
    success: bool


def get_glasses_in_region(
    region: GlassRegion = GlassRegion.ALL,
    min_nd: Optional[float] = None,
    max_nd: Optional[float] = None,
    min_vd: Optional[float] = None,
    max_vd: Optional[float] = None,
    manufacturers: Optional[list[str]] = None,
) -> list[GlassCandidate]:
    """Get glasses from catalog within specified region of glass map."""
    candidates = []
    for name, props in ALL_MATERIALS.items():
        if props.nd is None or props.vd is None:
            continue
        if region != GlassRegion.ALL and props.material_type != region.value:
            continue
        if min_nd is not None and props.nd < min_nd:
            continue
        if max_nd is not None and props.nd > max_nd:
            continue
        if min_vd is not None and props.vd < min_vd:
            continue
        if max_vd is not None and props.vd > max_vd:
            continue
        if manufacturers and props.manufacturer not in manufacturers:
            continue
        candidates.append(
            GlassCandidate(
                name=name,
                nd=props.nd,
                vd=props.vd,
                manufacturer=props.manufacturer,
                material_type=props.material_type,
                relative_price=props.relative_price,
            )
        )
    return candidates


def find_nearest_glasses(
    glass_name: str,
    n: int = 5,
    region: GlassRegion = GlassRegion.ALL,
) -> list[GlassCandidate]:
    """Find the n nearest glasses on the glass map to the given glass."""
    props = get_material_properties(glass_name)
    if props is None or props.nd is None or props.vd is None:
        return []
    candidates = get_glasses_in_region(region)
    for c in candidates:
        if c.name == glass_name:
            c.distance_from_current = float("inf")
        else:
            nd_diff = (c.nd - props.nd) / props.nd
            vd_diff = (c.vd - props.vd) / props.vd
            c.distance_from_current = (nd_diff**2 + vd_diff**2) ** 0.5
    candidates.sort(key=lambda c: c.distance_from_current)
    return [c for c in candidates if c.distance_from_current < float("inf")][:n]


def substitute_glass(system, component_id, new_glass):
    """Substitute a component glass with a new material."""
    return update_component(system, component_id, material=new_glass)


def evaluate_glass_substitution(system, component_id, new_glass, objective_fn):
    """Evaluate the effect of a glass substitution."""
    old_comp = next((c for c in system.components if c.id == component_id), None)
    if old_comp is None:
        raise ValueError(f"Component not found: {component_id}")
    original_glass = getattr(old_comp, "material", "unknown")
    old_obj = objective_fn(system)
    new_system = substitute_glass(system, component_id, new_glass)
    new_obj = objective_fn(new_system)
    old_props = get_material_properties(original_glass)
    new_props = get_material_properties(new_glass)
    nd_change = new_props.nd - old_props.nd if old_props and new_props else 0
    vd_change = new_props.vd - old_props.vd if old_props and new_props else 0
    return GlassSubstitutionResult(
        original_glass=original_glass,
        candidate_glass=new_glass,
        system=new_system,
        objective_change=new_obj - old_obj,
        nd_change=nd_change,
        vd_change=vd_change,
        is_better=new_obj < old_obj,
    )


def find_best_glass_substitution(
    system, component_id, objective_fn, candidates=None, region=GlassRegion.ALL
):
    """Find the best glass substitution for a component."""
    if candidates is None:
        comp = next((c for c in system.components if c.id == component_id), None)
        if comp is None:
            return None
        current_glass = getattr(comp, "material", "N-BK7")
        nearby = find_nearest_glasses(current_glass, n=20, region=region)
        candidates = [c.name for c in nearby]
    best = None
    for glass_name in candidates:
        try:
            result = evaluate_glass_substitution(
                system, component_id, glass_name, objective_fn
            )
            if result.is_better and (
                best is None or result.objective_change < best.objective_change
            ):
                best = result
        except Exception:
            continue
    return best


def glass_expert_optimize(
    system,
    objective_fn,
    max_iterations=20,
    n_candidates=10,
    region=GlassRegion.ALL,
    seed=None,
):
    """Glass expert: systematically perturb glass choices."""
    rng = random.Random(seed) if seed is not None else random.Random()
    current_system = system
    original_obj = objective_fn(system)
    current_obj = original_obj
    substitutions = []
    lenses = [c for c in system.components if isinstance(c, (ThinLens, ThickLens))]
    iteration = -1
    for iteration in range(max_iterations):
        improved = False
        shuffled = lenses[:]
        rng.shuffle(shuffled)
        for lens in shuffled:
            best = find_best_glass_substitution(
                current_system, lens.id, objective_fn, region=region
            )
            if best is not None and best.is_better:
                substitutions.append(
                    {
                        "component_id": lens.id,
                        "old_glass": best.original_glass,
                        "new_glass": best.candidate_glass,
                        "improvement": -best.objective_change,
                    }
                )
                current_system = best.system
                current_obj += best.objective_change
                improved = True
        if not improved:
            break
    return GlassExpertResult(
        original_system=system,
        optimized_system=current_system,
        substitutions_made=substitutions,
        objective_before=original_obj,
        objective_after=current_obj,
        n_iterations=iteration + 1,
        success=current_obj < original_obj,
    )


def compute_partial_derivatives(system, objective_fn, param_specs, h=1e-6):
    """Compute partial derivatives using central finite differences."""
    derivatives = {}
    for spec in param_specs:
        comp_id = spec.get("component_id", "")
        field = spec.get("field", "")
        key = f"{comp_id}.{field}" if comp_id else field
        val = _get_param(system, spec)
        plus = update_component(system, comp_id, **{field: val + h})
        minus = update_component(system, comp_id, **{field: val - h})
        derivatives[key] = (objective_fn(plus) - objective_fn(minus)) / (2.0 * h)
    return derivatives


def _get_param(system, spec):
    comp_id = spec.get("component_id")
    field = spec.get("field", "")
    if comp_id:
        comp = next((c for c in system.components if c.id == comp_id), None)
        if comp and hasattr(comp, field):
            return float(getattr(comp, field))
    return 0.0


@dataclass
class Operand:
    """A single merit function operand."""

    name: str
    target: float
    weight: float = 1.0
    value: float = 0.0
    contribution: float = 0.0


@dataclass
class MeritFunction:
    """Merit function for optimization."""

    operands: list = field(default_factory=list)
    value: float = 0.0

    def add_operand(self, name, target, weight=1.0):
        self.operands.append(Operand(name=name, target=target, weight=weight))

    def evaluate(self, system):
        total = 0.0
        for op in self.operands:
            op.value = _evaluate_operand(system, op.name)
            diff = op.value - op.target
            op.contribution = op.weight * diff * diff
            total += op.contribution
        self.value = total
        return total


def _evaluate_operand(system, name):
    from .analysis import back_focal_length

    analysis = analyze_system(system)
    operand_map = {
        "rms_spot": lambda: analysis.rms_spot_radius,
        "efl": lambda: analysis.effective_focal_length,
        "bfl": lambda: back_focal_length(system),
        "image_distance": lambda: analysis.image_distance,
        "magnification": lambda: analysis.magnification,
        "f_number": lambda: analysis.f_number,
        "na": lambda: analysis.numerical_aperture,
    }
    if name not in operand_map:
        raise ValueError(
            f"Unknown merit operand '{name}'. Supported: {sorted(operand_map)}"
        )
    return operand_map[name]()


def build_standard_merit_function(
    target_efl=None, target_magnification=None, min_spot_size=True, weights=None
):
    """Build a standard merit function for optical optimization."""
    mf = MeritFunction()
    w = weights or {}
    if target_efl is not None:
        mf.add_operand("efl", target_efl, w.get("efl", 1.0))
    if target_magnification is not None:
        mf.add_operand(
            "magnification", target_magnification, w.get("magnification", 1.0)
        )
    if min_spot_size:
        mf.add_operand("rms_spot", 0.0, w.get("rms_spot", 10.0))
    return mf
