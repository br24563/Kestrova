"""
Tests for the optical system management module.

These tests verify that system creation, component management,
and validation work correctly.
"""

import pytest
from optics.models import (
    OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings,
)
from optics.systems import (
    create_default_system, get_lenses, get_first_lens, get_last_lens,
    get_component_by_id, add_component, remove_component,
    update_component, move_component, sort_components, validate_system,
)


class TestCreateDefaultSystem:
    """Tests for the default system creation."""

    def test_default_system_has_two_lenses(self):
        system = create_default_system()
        lenses = get_lenses(system)
        assert len(lenses) == 2

    def test_default_system_has_object(self):
        system = create_default_system()
        assert system.object is not None
        assert system.object.height == pytest.approx(0.010)

    def test_default_system_has_image_plane(self):
        system = create_default_system()
        assert system.image_plane is not None

    def test_default_system_lenses_sorted(self):
        system = create_default_system()
        lenses = get_lenses(system)
        assert lenses[0].position < lenses[1].position

    def test_default_system_lens_ids(self):
        system = create_default_system()
        lenses = get_lenses(system)
        assert lenses[0].id == "lens_1"
        assert lenses[1].id == "lens_2"


class TestComponentManagement:
    """Tests for adding, removing, and updating components."""

    def test_add_component(self):
        system = create_default_system()
        new_lens = ThinLens(
            id="lens_3",
            position=0.200,
            focal_length=0.050,
            aperture_diameter=0.025,
        )
        new_system = add_component(system, new_lens)
        assert len(new_system.components) == 3
        assert get_component_by_id(new_system, "lens_3") is not None

    def test_remove_component(self):
        system = create_default_system()
        new_system = remove_component(system, "lens_2")
        assert len(new_system.components) == 1
        assert get_component_by_id(new_system, "lens_2") is None

    def test_remove_nonexistent_component(self):
        system = create_default_system()
        with pytest.raises(ValueError, match="not found"):
            remove_component(system, "nonexistent")

    def test_update_component(self):
        system = create_default_system()
        new_system = update_component(system, "lens_1", focal_length=0.075)
        lens = get_component_by_id(new_system, "lens_1")
        assert lens.focal_length == pytest.approx(0.075)

    def test_update_nonexistent_component(self):
        system = create_default_system()
        with pytest.raises(ValueError, match="not found"):
            update_component(system, "nonexistent", focal_length=0.1)

    def test_move_component(self):
        system = create_default_system()
        new_system = move_component(system, "lens_1", 0.150)
        lens = get_component_by_id(new_system, "lens_1")
        assert lens.position == pytest.approx(0.150)

    def test_get_component_by_id(self):
        system = create_default_system()
        lens = get_component_by_id(system, "lens_1")
        assert lens is not None
        assert lens.id == "lens_1"

    def test_get_component_by_id_not_found(self):
        system = create_default_system()
        assert get_component_by_id(system, "nonexistent") is None


class TestSortComponents:
    """Tests for sorting components by position."""

    def test_sort_components(self):
        system = create_default_system()
        # Reverse the order
        reversed_system = OpticalSystem(
            components=list(reversed(system.components)),
            object=system.object,
            image_plane=system.image_plane,
            analysis_settings=system.analysis_settings,
        )
        sorted_system = sort_components(reversed_system)
        lenses = get_lenses(sorted_system)
        assert lenses[0].position < lenses[1].position


class TestValidateSystem:
    """Tests for system validation."""

    def test_valid_system_no_warnings(self):
        system = create_default_system()
        warnings = validate_system(system)
        assert len(warnings) == 0

    def test_overlapping_components(self):
        system = create_default_system()
        # Move lens_2 to the same position as lens_1
        system = move_component(system, "lens_2", 0.100)
        warnings = validate_system(system)
        assert any("overlap" in w for w in warnings)

    def test_object_after_lens(self):
        system = create_default_system()
        # Move object to after the first lens
        system = OpticalSystem(
            components=system.components,
            object=Object(position=0.150, height=0.010),
            image_plane=system.image_plane,
            analysis_settings=system.analysis_settings,
        )
        warnings = validate_system(system)
        assert any("after" in w.lower() for w in warnings)

    def test_zero_focal_length_is_rejected(self):
        # The model refuses the value outright, so no system can carry it.
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            update_component(create_default_system(), "lens_1", focal_length=0.0)

    def test_negative_aperture_is_rejected(self):
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            update_component(create_default_system(), "lens_1", aperture_diameter=-0.01)
