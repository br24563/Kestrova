"""
Tests for the AI abstraction layer.

These tests verify that structured AI commands are correctly validated
and applied to the optics engine, and that the rule-based parser
converts natural-language prompts into valid commands.
"""

import pytest
from optics.models import (
    OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings,
)
from optics.systems import create_default_system, get_component_by_id
from ai.commands import (
    ModifyComponentCommand, AddComponentCommand, RemoveComponentCommand,
    SetObjectCommand, SetImagePlaneCommand, AnalyzeCommand, OptimizeCommand,
)
from ai.engine import apply_command, execute_command
from ai.local_provider import RuleBasedParser, LocalLLMProvider


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_single_lens_system() -> OpticalSystem:
    """Create a simple single-lens system for testing."""
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1",
                position=0.100,
                focal_length=0.050,
                aperture_diameter=0.025,
            ),
        ],
        object=Object(position=0.0, height=0.010),
        image_plane=ImagePlane(position=0.200),
        analysis_settings=AnalysisSettings(num_rays=11),
    )


# ---------------------------------------------------------------------------
# apply_command Tests
# ---------------------------------------------------------------------------

def test_apply_modify_component():
    """ModifyComponentCommand should update a component field."""
    system = make_single_lens_system()
    cmd = ModifyComponentCommand(component_id="lens_1", field="focal_length", value=0.075)
    updated = apply_command(system, cmd)
    lens = get_component_by_id(updated, "lens_1")
    assert lens.focal_length == 0.075


def test_apply_modify_component_not_found():
    """Modifying a nonexistent component should raise ValueError."""
    system = make_single_lens_system()
    cmd = ModifyComponentCommand(component_id="bogus", field="focal_length", value=0.075)
    with pytest.raises(ValueError):
        apply_command(system, cmd)


def test_apply_add_component():
    """AddComponentCommand should add a component."""
    system = make_single_lens_system()
    new_lens = ThinLens(
        id="lens_2", position=0.200, focal_length=0.050, aperture_diameter=0.025
    )
    cmd = AddComponentCommand(component=new_lens)
    updated = apply_command(system, cmd)
    assert len(updated.components) == 2
    assert get_component_by_id(updated, "lens_2") is not None


def test_apply_remove_component():
    """RemoveComponentCommand should remove a component."""
    system = make_single_lens_system()
    cmd = RemoveComponentCommand(component_id="lens_1")
    updated = apply_command(system, cmd)
    assert len(updated.components) == 0


def test_apply_remove_component_not_found():
    """Removing a nonexistent component should raise ValueError."""
    system = make_single_lens_system()
    cmd = RemoveComponentCommand(component_id="bogus")
    with pytest.raises(ValueError):
        apply_command(system, cmd)


def test_apply_set_object_position():
    """SetObjectCommand should update the object position."""
    system = make_single_lens_system()
    cmd = SetObjectCommand(position=-0.05)
    updated = apply_command(system, cmd)
    assert updated.object.position == -0.05


def test_apply_set_object_height():
    """SetObjectCommand should update the object height."""
    system = make_single_lens_system()
    cmd = SetObjectCommand(height=0.005)
    updated = apply_command(system, cmd)
    assert updated.object.height == 0.005


def test_apply_set_object_empty():
    """SetObjectCommand with no fields should raise ValueError."""
    system = make_single_lens_system()
    cmd = SetObjectCommand()
    with pytest.raises(ValueError):
        apply_command(system, cmd)


def test_apply_set_image_plane():
    """SetImagePlaneCommand should update the image plane position."""
    system = make_single_lens_system()
    cmd = SetImagePlaneCommand(position=0.250)
    updated = apply_command(system, cmd)
    assert updated.image_plane.position == 0.250


# ---------------------------------------------------------------------------
# execute_command Tests
# ---------------------------------------------------------------------------

def test_execute_analyze():
    """AnalyzeCommand should return an analysis result."""
    system = make_single_lens_system()
    cmd = AnalyzeCommand()
    result = execute_command(system, cmd)
    assert result["result"] is not None
    assert result["result"].effective_focal_length == pytest.approx(0.050, abs=1e-9)
    assert "Analysis complete" in result["message"]
    assert "Effective focal length" in result["message"]


def test_execute_modify_sorts_components():
    """execute_command should sort components by position."""
    system = make_single_lens_system()
    # Add a component at a position before the existing lens
    new_lens = ThinLens(
        id="lens_0", position=0.050, focal_length=0.050, aperture_diameter=0.025
    )
    cmd = AddComponentCommand(component=new_lens)
    result = execute_command(system, cmd)
    positions = [c.position for c in result["system"].components]
    assert positions == sorted(positions)


def test_execute_optimize_efl():
    """OptimizeCommand should optimize the EFL."""
    system = make_single_lens_system()
    cmd = OptimizeCommand(
        objective="efl",
        target=0.075,
        params=[{"component_id": "lens_1", "field": "focal_length"}],
        bounds=[[0.01, 0.20]],
    )
    result = execute_command(system, cmd)
    assert result["result"] is not None
    assert result["result"]["success"] is True
    # The optimized focal length should be close to the target
    assert abs(result["result"]["params"][0] - 0.075) < 1e-3


def test_execute_optimize_magnification_requires_target():
    """OptimizeCommand with magnification objective requires a target."""
    system = make_single_lens_system()
    cmd = OptimizeCommand(
        objective="magnification",
        params=[{"component_id": "lens_1", "field": "focal_length"}],
        bounds=[[0.01, 0.20]],
    )
    with pytest.raises(ValueError):
        execute_command(system, cmd)


# ---------------------------------------------------------------------------
# Rule-based Parser Tests
# ---------------------------------------------------------------------------

def test_parse_analyze():
    """'analyze' should produce an AnalyzeCommand."""
    parser = RuleBasedParser()
    commands = parser.parse("analyze the system")
    assert len(commands) == 1
    assert isinstance(commands[0], AnalyzeCommand)


def test_parse_move_component():
    """'move lens_1 to 150mm' should produce a ModifyComponentCommand."""
    parser = RuleBasedParser()
    commands = parser.parse("move lens_1 to 150mm")
    assert len(commands) == 1
    assert isinstance(commands[0], ModifyComponentCommand)
    assert commands[0].component_id == "lens_1"
    assert commands[0].field == "position"
    assert commands[0].value == pytest.approx(0.150)


def test_parse_set_focal_length():
    """'set lens_1 focal length to 75mm' should produce a ModifyComponentCommand."""
    parser = RuleBasedParser()
    commands = parser.parse("set lens_1 focal length to 75mm")
    assert len(commands) == 1
    assert isinstance(commands[0], ModifyComponentCommand)
    assert commands[0].component_id == "lens_1"
    assert commands[0].field == "focal_length"
    assert commands[0].value == pytest.approx(0.075)


def test_parse_remove_component():
    """'remove lens_1' should produce a RemoveComponentCommand."""
    parser = RuleBasedParser()
    commands = parser.parse("remove lens_1")
    assert len(commands) == 1
    assert isinstance(commands[0], RemoveComponentCommand)
    assert commands[0].component_id == "lens_1"


def test_parse_set_object_position():
    """'set object position to 50mm' should produce a SetObjectCommand."""
    parser = RuleBasedParser()
    commands = parser.parse("set object position to 50mm")
    assert len(commands) == 1
    assert isinstance(commands[0], SetObjectCommand)
    assert commands[0].position == pytest.approx(0.050)


def test_parse_set_object_height():
    """'set object height to 5mm' should produce a SetObjectCommand."""
    parser = RuleBasedParser()
    commands = parser.parse("set object height to 5mm")
    assert len(commands) == 1
    assert isinstance(commands[0], SetObjectCommand)
    assert commands[0].height == pytest.approx(0.005)


def test_parse_set_image_plane():
    """'set image plane to 200mm' should produce a SetImagePlaneCommand."""
    parser = RuleBasedParser()
    commands = parser.parse("set image plane to 200mm")
    assert len(commands) == 1
    assert isinstance(commands[0], SetImagePlaneCommand)
    assert commands[0].position == pytest.approx(0.200)


def test_parse_unknown_prompt():
    """An unparseable prompt should raise ValueError."""
    parser = RuleBasedParser()
    with pytest.raises(ValueError):
        parser.parse("do something completely random")


# ---------------------------------------------------------------------------
# LocalLLMProvider Tests
# ---------------------------------------------------------------------------

def test_provider_uses_rule_based_parser():
    """The provider should use the rule-based parser by default."""
    provider = LocalLLMProvider()
    commands = provider.interpret("analyze the system")
    assert len(commands) == 1
    assert isinstance(commands[0], AnalyzeCommand)


def test_provider_raises_on_unknown():
    """The provider should raise ValueError for unparseable prompts."""
    provider = LocalLLMProvider()
    with pytest.raises(ValueError):
        provider.interpret("do something completely random")