"""
Optical system assembly and management.

This module provides functions for creating, modifying, and managing
optical systems. It works with the data models defined in models.py
and the calculations in lenses.py, rays.py, and analysis.py.

The system is represented as an ordered list of optical components
(lenses, surfaces, apertures, etc.) along with an object and image plane.
"""

from typing import Optional
from .models import (
    OpticalSystem, OpticalComponent, ThinLens, SphericalSurface, ThickLens,
    ApertureStop, Object, ImagePlane, AnalysisSettings,
)


# ---------------------------------------------------------------------------
# Default System
# ---------------------------------------------------------------------------

def create_default_system() -> OpticalSystem:
    """
    Create a default two-lens optical system.

    The default system is a simple two-lens relay:
        Object → Lens 1 (50mm) → Lens 2 (50mm) → Image Plane

    Object height: 10 mm
    Lens 1: position 100mm, f=50mm, aperture=25mm
    Lens 2: position 150mm, f=50mm, aperture=25mm
    Image plane: position 175mm (calculated image position)

    Returns:
        A default OpticalSystem.
    """
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1",
                position=0.100,  # 100 mm
                focal_length=0.050,  # 50 mm
                aperture_diameter=0.025,  # 25 mm
                material="N-BK7",
            ),
            ThinLens(
                id="lens_2",
                position=0.150,  # 150 mm
                focal_length=0.050,  # 50 mm
                aperture_diameter=0.025,  # 25 mm
                material="N-BK7",
            ),
        ],
        wavelengths=[550e-9],  # 550 nm (green)
        object=Object(
            position=0.0,  # 0 mm
            height=0.010,  # 10 mm
            orientation=0.0,
        ),
        image_plane=ImagePlane(
            position=0.175,  # 175 mm (calculated image position)
        ),
        analysis_settings=AnalysisSettings(
            num_rays=11,
            ray_types=["chief", "marginal", "fill"],
            aperture_fraction=1.0,
            wavelength=550e-9,
        ),
    )


# ---------------------------------------------------------------------------
# Component Management
# ---------------------------------------------------------------------------

def get_lenses(system: OpticalSystem) -> list[ThinLens]:
    """
    Get all lens components (thin or thick), sorted by position.

    Args:
        system: The optical system.

    Returns:
        List of lens components, sorted by position (left to right).
    """
    return sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda l: l.position,
    )


def get_first_lens(system: OpticalSystem) -> Optional[ThinLens]:
    """
    Get the first (leftmost) thin lens in the system.

    Args:
        system: The optical system.

    Returns:
        The first ThinLens, or None if there are no lenses.
    """
    lenses = get_lenses(system)
    return lenses[0] if lenses else None


def get_last_lens(system: OpticalSystem) -> Optional[ThinLens]:
    """
    Get the last (rightmost) thin lens in the system.

    Args:
        system: The optical system.

    Returns:
        The last ThinLens, or None if there are no lenses.
    """
    lenses = get_lenses(system)
    return lenses[-1] if lenses else None


def get_component_by_id(
    system: OpticalSystem, component_id: str
) -> Optional[OpticalComponent]:
    """
    Find a component by its ID.

    Args:
        system: The optical system.
        component_id: The ID of the component to find.

    Returns:
        The component, or None if not found.
    """
    for comp in system.components:
        if comp.id == component_id:
            return comp
    return None


def add_component(
    system: OpticalSystem, component: OpticalComponent
) -> OpticalSystem:
    """
    Add a component to the system.

    The component is appended to the end of the components list.
    The system is returned as a new object (immutable update).

    Args:
        system: The optical system.
        component: The component to add.

    Returns:
        A new OpticalSystem with the component added.
    """
    new_components = list(system.components) + [component]
    return system.model_copy(update={"components": new_components})


def remove_component(
    system: OpticalSystem, component_id: str
) -> OpticalSystem:
    """
    Remove a component from the system by ID.

    Args:
        system: The optical system.
        component_id: The ID of the component to remove.

    Returns:
        A new OpticalSystem with the component removed.

    Raises:
        ValueError: If the component is not found.
    """
    new_components = [c for c in system.components if c.id != component_id]
    if len(new_components) == len(system.components):
        raise ValueError(f"Component with id '{component_id}' not found.")
    return system.model_copy(update={"components": new_components})


def update_component(
    system: OpticalSystem,
    component_id: str,
    **kwargs,
) -> OpticalSystem:
    """
    Update a component's properties.

    Args:
        system: The optical system.
        component_id: The ID of the component to update.
        **kwargs: Field names and new values to update.

    Returns:
        A new OpticalSystem with the updated component.

    Raises:
        ValueError: If the component is not found.
    """
    new_components = []
    found = False
    for comp in system.components:
        if comp.id == component_id:
            found = True
            # re-validate so invalid values (e.g. zero focal length) are rejected
            updated = type(comp).model_validate({**comp.model_dump(), **kwargs})
            new_components.append(updated)
        else:
            new_components.append(comp)

    if not found:
        raise ValueError(f"Component with id '{component_id}' not found.")

    return system.model_copy(update={"components": new_components})


def move_component(
    system: OpticalSystem, component_id: str, new_position: float
) -> OpticalSystem:
    """
    Move a component to a new position along the optical axis.

    Args:
        system: The optical system.
        component_id: The ID of the component to move.
        new_position: The new position (meters).

    Returns:
        A new OpticalSystem with the component moved.
    """
    return update_component(system, component_id, position=new_position)


def sort_components(system: OpticalSystem) -> OpticalSystem:
    """
    Sort the components by position (left to right).

    Args:
        system: The optical system.

    Returns:
        A new OpticalSystem with sorted components.
    """
    sorted_comps = sorted(system.components, key=lambda c: c.position)
    return system.model_copy(update={"components": sorted_comps})


# ---------------------------------------------------------------------------
# System Validation
# ---------------------------------------------------------------------------

def validate_system(system: OpticalSystem) -> list[str]:
    """
    Validate the optical system and return a list of warnings.

    Checks for:
        - Components at the same position
        - Object after the first lens
        - Image plane before the last lens
        - Negative aperture diameters
        - Zero focal lengths

    Args:
        system: The optical system.

    Returns:
        List of warning messages. Empty list if no issues.
    """
    warnings: list[str] = []

    # Check for components at the same position
    positions = [c.position for c in system.components]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            if abs(positions[i] - positions[j]) < 1e-9:
                warnings.append(
                    f"Components at position {positions[i]:.6f}m overlap."
                )

    # Check object position
    lenses = get_lenses(system)
    if lenses:
        first_lens = lenses[0]
        if system.object.position >= first_lens.position:
            warnings.append(
                "Object is at or after the first lens; "
                "image may be virtual."
            )

    # Check image plane position
    if lenses:
        last_lens = lenses[-1]
        if system.image_plane.position <= last_lens.position:
            warnings.append(
                "Image plane is at or before the last lens; "
                "image may not form."
            )

    # Check for negative apertures
    for comp in system.components:
        if isinstance(comp, (ThinLens, ThickLens)):
            if comp.aperture_diameter <= 0:
                warnings.append(
                    f"Lens '{comp.id}' has non-positive aperture diameter."
                )
        elif isinstance(comp, ApertureStop):
            if comp.diameter <= 0:
                warnings.append(
                    f"Aperture '{comp.id}' has non-positive diameter."
                )

    # Check for zero focal lengths
    for comp in system.components:
        if isinstance(comp, ThinLens):
            if abs(comp.focal_length) < 1e-15:
                warnings.append(
                    f"Lens '{comp.id}' has zero focal length."
                )
        elif isinstance(comp, ThickLens):
            if abs(comp.radius1) < 1e-15 and abs(comp.radius2) < 1e-15:
                warnings.append(
                    f"Lens '{comp.id}' has both radii zero (slab)."
                )

    return warnings
