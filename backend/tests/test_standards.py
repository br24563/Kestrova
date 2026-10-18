"""
Tests for industry standards and workflows (item 9).

Covers Zemax-style tolerance operands, PartBuilder, the Lens Data
Editor, the Merit Function Editor, inverse sensitivity tolerancing,
automatic compensator selection, and multiple unit systems.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from optics.standards import (
    OperandType, ToleranceOperand,
    PartDefinition, build_part_from_spec,
    SurfaceRow, LensDataEditor,
    MeritOperandRow, MeritFunctionEditor, MERIT_OPERAND_MAP,
    operand_to_parameter, select_compensators,
    inverse_sensitivity_tolerance, build_tolerance_operands,
    operands_to_tolerance_specs,
    UnitSystem, UNIT_SYSTEMS, convert_unit_system, EXTRA_LENGTH_UNITS,
)
from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings,
)


def create_test_system():
    """Create a simple two-lens system for testing."""
    return OpticalSystem(
        components=[
            ThinLens(id="L1", position=0.100, focal_length=0.050,
                     aperture_diameter=0.025, material="N-BK7"),
            ThinLens(id="L2", position=0.150, focal_length=0.050,
                     aperture_diameter=0.025, material="N-BK7"),
        ],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=0.010, orientation=0.0),
        image_plane=ImagePlane(position=0.200),
        analysis_settings=AnalysisSettings(
            num_rays=11, ray_types=["chief", "marginal", "fill"],
            aperture_fraction=1.0, wavelength=550e-9,
        ),
    )


class TestToleranceOperands:
    """Tests for Zemax-style tolerance operands."""

    def test_operand_types_exist(self):
        assert OperandType.TRAD.value == "TRAD"
        assert OperandType.TTHI.value == "TTHI"
        assert OperandType.TIND.value == "TIND"

    def test_length_operand_to_si(self):
        op = ToleranceOperand(OperandType.TTHI, surface=1, value=0.05, unit="mm")
        assert op.to_si() == pytest.approx(5e-5)

    def test_dimensionless_operand_to_si(self):
        op = ToleranceOperand(OperandType.TIND, surface=1, value=0.001, unit="")
        assert op.to_si() == pytest.approx(0.001)

    def test_operand_to_parameter(self):
        assert operand_to_parameter(OperandType.TTHI, 1) == "surface_1_thickness"
        assert operand_to_parameter(OperandType.TRAD, 2) == "surface_2_radius"

    def test_build_tolerance_operands(self):
        ops = build_tolerance_operands(default_tol_mm=0.1, n_surfaces=2)
        assert len(ops) == 14
        kinds = set(o.op_type for o in ops)
        assert OperandType.TRAD in kinds
        assert OperandType.TTHI in kinds
        assert OperandType.TIND in kinds

    def test_operands_to_tolerance_specs(self):
        ops = [ToleranceOperand(OperandType.TTHI, surface=1, value=0.05, unit="mm")]
        specs = operands_to_tolerance_specs(ops, component_ids=["L1", "L2"])
        assert "L1.thickness" in specs
        assert specs["L1.thickness"] == pytest.approx(5e-5)


class TestPartBuilder:
    """Tests for the parametric PartBuilder."""

    def test_default_part(self):
        part = PartDefinition()
        assert part.shape == "biconvex"
        assert part.material == "N-BK7"

    def test_build_from_spec(self):
        part = build_part_from_spec({
            "shape": "plano_convex",
            "focal_length": 0.075,
            "aperture_diameter": 0.030,
            "part_number": "TEST-42",
        })
        assert part.part_number == "TEST-42"
        assert part.shape == "plano_convex"

    def test_biconvex_radii_are_mirrored(self):
        part = PartDefinition(shape="biconvex", focal_length=0.075)
        r1, r2 = part.compute_radii()
        assert r1 == pytest.approx(-r2)
        assert r1 > 0

    def test_biconcave_radii_are_negative_first(self):
        part = PartDefinition(shape="biconcave", focal_length=-0.075)
        r1, r2 = part.compute_radii()
        assert r1 < 0
        assert r2 > 0

    def test_biconcave_with_positive_power_is_rejected(self):
        with pytest.raises(ValueError):
            PartDefinition(shape="biconcave", focal_length=0.075).compute_radii()

    def test_zero_focal_length_is_rejected(self):
        with pytest.raises(ValueError):
            PartDefinition(shape="biconvex", focal_length=0.0).compute_radii()

    def test_to_component(self):
        part = build_part_from_spec({"focal_length": 0.075, "aperture_diameter": 0.030})
        comp = part.to_component("PB1", 0.05)
        assert isinstance(comp, ThickLens)
        assert comp.id == "PB1"
        assert comp.position == pytest.approx(0.05)
        assert comp.thickness > 0


class TestLensDataEditor:
    """Tests for the Zemax-style Lens Data Editor."""

    def test_row_count(self):
        system = create_test_system()
        lde = LensDataEditor(system)
        # object + 2 lenses + image
        assert len(lde.rows) == 4

    def test_first_and_last_rows(self):
        system = create_test_system()
        lde = LensDataEditor(system)
        assert lde.rows[0].comment == "OBJECT"
        assert lde.rows[-1].comment == "IMAGE"

    def test_ideal_lens_rows_are_paraxial_surfaces(self):
        # Ideal thin lenses are Zemax PARAXIAL surfaces; the glass column is
        # the medium after the surface (air).
        lde = LensDataEditor(create_test_system())
        for row in lde.rows[1:3]:
            assert row.surface_type == "PARAXIAL"
            assert row.paraxial_focal_length == pytest.approx(0.050)
            assert row.glass == "AIR"
        assert sum(r.is_stop for r in lde.rows) == 1

    def test_thick_lens_rows_carry_glass(self):
        system = create_test_system().model_copy(update={"components": [
            ThickLens(id="L1", position=0.1, radius1=0.05, radius2=-0.05, thickness=0.005,
                      aperture_diameter=0.02, material="N-BK7")]})
        lde = LensDataEditor(system)
        assert lde.rows[1].glass == "N-BK7"
        assert lde.rows[2].glass == "AIR"

    def test_to_dicts(self):
        system = create_test_system()
        lde = LensDataEditor(system)
        dicts = lde.to_dicts()
        assert isinstance(dicts, list)
        assert dicts[0]["comment"] == "OBJECT"

    def test_summary_text(self):
        system = create_test_system()
        lde = LensDataEditor(system)
        text = lde.summary_text()
        assert "SURF" in text
        assert "OBJECT" in text
        assert "IMAGE" in text


class TestMeritFunctionEditor:
    """Tests for the Merit Function Editor."""

    def test_add_rows(self):
        mfe = MeritFunctionEditor()
        mfe.add("EFFL", 0.05, 1.0, "efl target")
        mfe.add("RMS", 0.0, 100.0, "spot")
        assert len(mfe.rows) == 2

    def test_evaluate_returns_float(self):
        system = create_test_system()
        mfe = MeritFunctionEditor()
        mfe.add("EFFL", 0.05, 1.0)
        value = mfe.evaluate(system)
        assert isinstance(value, float)
        assert value >= 0.0

    def test_efl_target_on_nominal_is_near_zero(self):
        system = create_test_system()
        from optics.analysis import analyze_system
        efl = analyze_system(system).effective_focal_length
        mfe = MeritFunctionEditor()
        mfe.add("EFFL", efl, 1.0)
        assert mfe.evaluate(system) == pytest.approx(0.0, abs=1e-12)

    def test_unknown_operand_is_rejected(self):
        system = create_test_system()
        mfe = MeritFunctionEditor()
        mfe.add("NOT_A_REAL_OPERAND", 1.0, 1.0)
        with pytest.raises(ValueError):
            mfe.evaluate(system)

    def test_operand_map_contents(self):
        assert MERIT_OPERAND_MAP["RMS"] == "rms_spot_radius"
        assert MERIT_OPERAND_MAP["EFFL"] == "effective_focal_length"


class TestCompensatorSelection:
    """Tests for automatic compensator selection."""

    def test_returns_ranked_list(self):
        system = create_test_system()
        comps = select_compensators(system, max_compensators=2)
        assert len(comps) == 2

    def test_improvement_is_sorted_descending(self):
        system = create_test_system()
        comps = select_compensators(system, max_compensators=3)
        improvements = [c["improvement"] for c in comps]
        assert improvements == sorted(improvements, reverse=True)

    def test_entries_have_expected_keys(self):
        system = create_test_system()
        comps = select_compensators(system, max_compensators=1)
        assert set(comps[0].keys()) == {"name", "field", "current", "best", "improvement"}

    def test_focus_is_a_candidate(self):
        system = create_test_system()
        comps = select_compensators(system, max_compensators=5)
        names = [c["name"] for c in comps]
        assert any("focus" in n or "air_space" in n for n in names)


class TestInverseSensitivity:
    """Tests for inverse sensitivity tolerancing."""

    def test_solved_tolerance_within_bounds(self):
        system = create_test_system()
        result = inverse_sensitivity_tolerance(
            system,
            ToleranceOperand(OperandType.TTHI, surface=1),
            target_degradation=0.10,
            parameter="L1.position",
            tol_min=1e-6,
            tol_max=1e-3,
        )
        assert result["solved_tolerance"] >= 1e-6
        assert result["solved_tolerance"] <= 1e-3

    def test_result_keys(self):
        system = create_test_system()
        result = inverse_sensitivity_tolerance(
            system,
            ToleranceOperand(OperandType.TRAD, surface=1),
            target_degradation=0.5,
            parameter="L1.position",
        )
        for key in ("operand", "surface", "solved_tolerance", "nominal_metric",
                    "budget_metric", "perturbed_metric", "within_budget",
                    "target_degradation"):
            assert key in result

    def test_larger_budget_allows_larger_tolerance(self):
        system = create_test_system()
        tight = inverse_sensitivity_tolerance(
            system, ToleranceOperand(OperandType.TTHI, surface=1),
            target_degradation=0.01, parameter="L1.position")
        loose = inverse_sensitivity_tolerance(
            system, ToleranceOperand(OperandType.TTHI, surface=1),
            target_degradation=1.0, parameter="L1.position")
        assert loose["solved_tolerance"] >= tight["solved_tolerance"]


class TestUnitSystems:
    """Tests for multiple unit system support."""

    def test_all_systems_build(self):
        for name in UNIT_SYSTEMS:
            us = UnitSystem.from_name(name)
            assert us.name == name

    def test_unknown_system_falls_back_to_metric(self):
        us = UnitSystem.from_name("does_not_exist")
        assert us.length == "mm"

    def test_metric_mm(self):
        us = UnitSystem.from_name("metric")
        assert us.to_display_length(0.050) == pytest.approx(50.0)

    def test_english_inches(self):
        us = UnitSystem.from_name("english")
        assert us.to_display_length(0.0254) == pytest.approx(1.0)

    def test_round_trip_lengths(self):
        system = UnitSystem.from_name("english")
        assert system.from_display_length(1.0) == pytest.approx(0.0254)

    def test_convert_unit_system_inches_to_mm(self):
        assert convert_unit_system(1.0, "in", "mm") == pytest.approx(25.4)

    def test_convert_unit_system_mil(self):
        assert convert_unit_system(1000.0, "mil", "in") == pytest.approx(1.0)

    def test_extra_units_table(self):
        assert "in" in EXTRA_LENGTH_UNITS
        assert "mil" in EXTRA_LENGTH_UNITS

    def test_wavelength_display(self):
        us = UnitSystem.from_name("metric")
        assert us.to_display_wavelength(550e-9) == pytest.approx(550.0)

    def test_angle_display(self):
        import math
        us = UnitSystem.from_name("metric")
        assert us.to_display_angle(math.pi / 2) == pytest.approx(90.0)
