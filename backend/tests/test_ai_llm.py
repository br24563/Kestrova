"""
Tests for the AI/LLM integration layer (item 10).

Covers the multi-provider abstraction and its schema-constrained JSON
robustness chain, multi-turn conversational refinement, and
prescription/claim verification.

No network access is required: every test uses the deterministic
MockProvider.
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai.providers import (
    LLMResponse, ProviderConfig, MockProvider, ProviderChain,
    StructuredGenerator, StructuredResult,
    extract_json_array, repair_json, salvage_objects, COMMAND_ACTIONS,
)
from ai.conversation import (
    Intent, classify_intent, extract_numbers, number_before, number_after,
    DesignBrief, ConversationSession, ConversationTurn,
)
from ai.verification import (
    REFERENCE_DESIGNS, verify_claim, verify_claims,
    check_edge_thickness, check_glass_availability, check_element_aspect_ratio,
    run_design_rule_checks, rule_check_summary,
    verify_prescription, count_elements, full_verification,
)
from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings,
)
from optics.analysis import analyze_system


def make_system():
    """A simple two-lens system used throughout these tests."""
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


# =============================================================================
# Providers
# =============================================================================

class TestJsonExtraction:
    """Tests for robust JSON recovery from model prose."""

    def test_bare_array(self):
        assert extract_json_array('[{"a": 1}]') == '[{"a": 1}]'

    def test_array_with_prose(self):
        assert extract_json_array('Sure! [{"a": 1}] done') == '[{"a": 1}]'

    def test_markdown_fence(self):
        text = 'here you go\n```json\n[{"a": 1}]\n```\n'
        assert extract_json_array(text) == '[{"a": 1}]'

    def test_nested_brackets(self):
        assert extract_json_array('[{"x": [1, 2]}]') == '[{"x": [1, 2]}]'

    def test_no_array_returns_none(self):
        assert extract_json_array("no json here") is None

    def test_empty_returns_none(self):
        assert extract_json_array("") is None

    def test_respects_strings_containing_brackets(self):
        text = '[{"a": "not ] this"}]'
        assert extract_json_array(text) == text


class TestJsonRepair:
    """Tests for the JSON repair pass."""

    def test_trailing_comma(self):
        assert json.loads(repair_json('[{"a": 1,},]')) == [{"a": 1}]

    def test_single_quoted_key_and_value(self):
        repaired = repair_json("[{'action': 'analyze'}]")
        assert json.loads(repaired) == [{"action": "analyze"}]

    def test_python_literals(self):
        repaired = repair_json('[{"a": True, "b": False, "c": None}]')
        assert json.loads(repaired) == [{"a": True, "b": False, "c": None}]

    def test_smart_quotes(self):
        text = "[{" + chr(8220) + "action" + chr(8221) + ": 1}]"
        assert json.loads(repair_json(text)) == [{"action": 1}]

    def test_inner_double_quote_is_escaped(self):
        repaired = repair_json("[{'a': 'say \"hi\"'}]")
        assert json.loads(repaired) == [{"a": 'say "hi"'}]

    def test_empty_input(self):
        assert repair_json("") == ""


class TestSalvageObjects:
    """Tests for the last-resort object salvage."""

    def test_multiple_objects(self):
        blobs = salvage_objects('{"a": 1} junk {"b": 2}')
        assert blobs == ['{"a": 1}', '{"b": 2}']

    def test_no_objects(self):
        assert salvage_objects("nothing") == []


class TestMockProvider:
    """Tests for the deterministic test provider."""

    def test_queue_and_generate(self):
        mock = MockProvider()
        mock.queue('[{"action": "analyze"}]')
        resp = mock.generate("hi")
        assert resp.ok
        assert resp.provider == "mock"

    def test_empty_when_nothing_queued(self):
        mock = MockProvider()
        assert not mock.generate("hi").ok

    def test_records_prompts(self):
        mock = MockProvider()
        mock.generate("hello", "system text")
        assert mock.prompts[0][1] == "hello"


class TestProviderChain:
    """Tests for the provider fallback chain."""

    def test_first_success_wins(self):
        first = MockProvider()
        second = MockProvider()
        first.queue('[{"action": "analyze"}]')
        second.queue('[{"action": "diagnose"}]')
        chain = ProviderChain([first, second])
        assert "analyze" in chain.generate("x").text

    def test_falls_through_to_second(self):
        first = MockProvider()
        second = MockProvider()
        second.queue('[{"action": "diagnose"}]')
        chain = ProviderChain([first, second])
        assert "diagnose" in chain.generate("x").text

    def test_from_config_mock(self):
        chain = ProviderChain.from_config(ProviderConfig(provider="mock"))
        assert chain.available_provider() == "mock"


class TestStructuredGenerator:
    """Tests for schema-constrained generation."""

    def _generator_with(self, text):
        mock = MockProvider()
        mock.queue(text)
        return StructuredGenerator(ProviderChain([mock]))

    def test_valid_json(self):
        gen = StructuredGenerator(ProviderChain([MockProvider()]))
        for p in gen.chain.providers:
            if isinstance(p, MockProvider):
                p.queue('[{"action": "analyze"}, {"action": "diagnose"}]')
        res = gen.generate_commands("do both")
        assert res.ok
        assert len(res.objects) == 2
        assert res.attempts == 1

    def test_repair_path(self):
        gen = StructuredGenerator(ProviderChain([MockProvider()]))
        for p in gen.chain.providers:
            if isinstance(p, MockProvider):
                p.queue("Sure thing! [{'action': 'analyze',},]")
        res = gen.generate_commands("analyze")
        assert res.ok
        assert res.objects[0]["action"] == "analyze"

    def test_total_failure_is_reported(self):
        gen = StructuredGenerator(ProviderChain([MockProvider()]))
        res = gen.generate_commands("nonsense")
        assert not res.ok
        assert res.errors

    def test_validator_rejects_bad_actions(self):
        def validator(raw):
            if raw.get("action") not in COMMAND_ACTIONS:
                raise ValueError("bad action")
            return raw

        gen = StructuredGenerator(ProviderChain([MockProvider()]))
        for p in gen.chain.providers:
            if isinstance(p, MockProvider):
                p.queue('[{"action": "not_real"}]')
        res = gen.generate_commands("x", validator=validator)
        assert not res.ok

    def test_array_missing_but_objects_present(self):
        gen = StructuredGenerator(ProviderChain([MockProvider()]))
        for p in gen.chain.providers:
            if isinstance(p, MockProvider):
                p.queue('{"action": "analyze"}')
        res = gen.generate_commands("x")
        assert res.ok
        assert res.objects[0]["action"] == "analyze"


# =============================================================================
# Conversation
# =============================================================================

class TestIntentClassification:
    """Tests for refinement intent classification."""

    def test_make_smaller(self):
        assert classify_intent("make it smaller") == Intent.MAKE_SMALLER

    def test_widen_aperture(self):
        assert classify_intent("widen the aperture") == Intent.WIDEN_APERTURE

    def test_narrow_aperture(self):
        assert classify_intent("stop down") == Intent.NARROW_APERTURE

    def test_add_element(self):
        assert classify_intent("add another element") == Intent.ADD_ELEMENT

    def test_remove_element(self):
        assert classify_intent("remove the last lens") == Intent.REMOVE_ELEMENT

    def test_optimize(self):
        assert classify_intent("optimize it") == Intent.OPTIMIZE

    def test_undo(self):
        assert classify_intent("undo that") == Intent.UNDO

    def test_unknown(self):
        assert classify_intent("the weather is nice") == Intent.UNKNOWN

    def test_undo_wins_over_other_keywords(self):
        # "undo" must take precedence even if other words appear
        assert classify_intent("undo the last change") == Intent.UNDO


class TestNumericHelpers:
    """Tests for the regex-free numeric parsing helpers."""

    def test_extract_numbers(self):
        assert extract_numbers("5x at f/2.8 and 50mm") == [5.0, 2.8, 50.0]

    def test_extract_numbers_empty(self):
        assert extract_numbers("no digits") == []

    def test_number_before(self):
        assert number_before("efl of 50mm", "mm") == 50.0

    def test_number_before_missing(self):
        assert number_before("mm", "mm") is None

    def test_number_after(self):
        assert number_after("lens at f/2.8", "f/") == 2.8

    def test_number_after_missing(self):
        assert number_after("nothing", "f/") is None


class TestDesignBrief:
    """Tests for accumulated design requirements."""

    def test_magnification(self):
        brief = DesignBrief()
        brief.update_from_text("design a 5x magnification system")
        assert brief.magnification == 5.0

    def test_f_number(self):
        brief = DesignBrief()
        brief.update_from_text("at f/2.8 please")
        assert brief.f_number == 2.8

    def test_focal_length_mm(self):
        brief = DesignBrief()
        brief.update_from_text("an EFL of 100mm")
        assert brief.efl == pytest.approx(0.1)

    def test_wavelength_band(self):
        brief = DesignBrief()
        brief.update_from_text("for visible wavelengths")
        assert brief.wavelength_min == pytest.approx(400e-9)
        assert brief.wavelength_max == pytest.approx(700e-9)

    def test_element_budget(self):
        brief = DesignBrief()
        brief.update_from_text("a three element design")
        assert brief.element_budget == 3

    def test_material(self):
        brief = DesignBrief()
        brief.update_from_text("using N-BK7")
        assert "n-bk7" in brief.materials

    def test_no_constraints(self):
        brief = DesignBrief()
        assert brief.update_from_text("hello there") == []

    def test_context_note_mentions_values(self):
        brief = DesignBrief()
        brief.update_from_text("5x at f/2.8")
        note = brief.to_context_note()
        assert "magnification" in note
        assert "f/2.8" in note

    def test_as_dict_roundtrip(self):
        brief = DesignBrief()
        brief.update_from_text("5x at f/2.8")
        d = brief.as_dict()
        assert d["magnification"] == 5.0
        assert d["f_number"] == 2.8


class TestConversationSession:
    """Tests for multi-turn design refinement."""

    def test_resolve_explicit_id(self):
        s = ConversationSession(make_system())
        assert s.resolve_component("change L1 please") == "L1"

    def test_resolve_last(self):
        s = ConversationSession(make_system())
        assert s.resolve_component("the last lens") == "L2"

    def test_resolve_first(self):
        s = ConversationSession(make_system())
        assert s.resolve_component("the first element") == "L1"

    def test_resolve_ordinal_number(self):
        s = ConversationSession(make_system())
        assert s.resolve_component("element 2") == "L2"

    def test_resolve_none_when_no_lenses(self):
        system = make_system()
        system = system.model_copy(update={"components": []})
        s = ConversationSession(system)
        assert s.resolve_component("the last lens") is None

    def test_ask_records_turn(self):
        s = ConversationSession(make_system())
        turn = s.ask("analyze the system")
        assert isinstance(turn, ConversationTurn)
        assert turn.intent == Intent.ANALYZE
        assert len(s.history) == 1

    def test_analyze_does_not_mutate(self):
        s = ConversationSession(make_system())
        before = len(s.system.components)
        s.ask("analyze the system")
        assert len(s.system.components) == before

    def test_add_element_increases_count(self):
        s = ConversationSession(make_system())
        before = count_elements(s.system)
        turn = s.ask("add another element")
        assert turn.ok
        assert count_elements(s.system) == before + 1

    def test_remove_element_decreases_count(self):
        s = ConversationSession(make_system())
        before = count_elements(s.system)
        turn = s.ask("remove the last lens")
        assert turn.ok
        assert count_elements(s.system) == before - 1

    def test_widen_aperture(self):
        s = ConversationSession(make_system())
        before = s.system.components[0].aperture_diameter
        turn = s.ask("widen the aperture")
        assert turn.ok
        assert s.system.components[0].aperture_diameter > before

    def test_stop_down_aperture(self):
        s = ConversationSession(make_system())
        before = s.system.components[0].aperture_diameter
        turn = s.ask("stop down the aperture")
        assert turn.ok
        assert s.system.components[0].aperture_diameter < before

    def test_make_smaller_scales(self):
        s = ConversationSession(make_system())
        before = s.system.components[-1].position
        turn = s.ask("make it smaller")
        assert turn.ok
        assert s.system.components[-1].position < before

    def test_undo_restores_previous_state(self):
        s = ConversationSession(make_system())
        before = count_elements(s.system)
        s.ask("add another element")
        assert count_elements(s.system) == before + 1
        assert s.can_undo
        s.ask("undo")
        assert count_elements(s.system) == before

    def test_undo_with_empty_stack(self):
        s = ConversationSession(make_system())
        assert not s.can_undo
        turn = s.ask("undo")
        assert not turn.ok

    def test_brief_accumulates_across_turns(self):
        s = ConversationSession(make_system())
        s.ask("design a 5x magnification system")
        s.ask("at f/2.8")
        assert s.brief.magnification == 5.0
        assert s.brief.f_number == 2.8

    def test_unknown_intent_is_recorded(self):
        s = ConversationSession(make_system())
        turn = s.ask("the weather is nice")
        assert turn.intent == Intent.UNKNOWN
        assert turn.ok
        assert len(s.history) == 1

    def test_transcript_contains_both_sides(self):
        s = ConversationSession(make_system())
        s.ask("analyze the system")
        text = s.transcript()
        assert "USER" in text
        assert "ASSISTANT" in text

    def test_to_dicts(self):
        s = ConversationSession(make_system())
        s.ask("analyze the system")
        dicts = s.to_dicts()
        assert dicts[0]["intent"] == "analyze"

    def test_scale_system(self):
        s = ConversationSession(make_system())
        before = s.system.components[0].focal_length
        turn = s.ask("scale by 2")
        assert turn.ok
        assert s.system.components[0].focal_length == pytest.approx(before * 2.0)

    def test_scale_by_missing_factor(self):
        s = ConversationSession(make_system())
        turn = s.ask("scale by")
        assert turn.ok
        assert "scale factor" in turn.assistant_text

    def test_history_is_capped(self):
        s = ConversationSession(make_system(), max_history=3)
        for _ in range(6):
            s.ask("analyze the system")
        assert len(s.history) <= 3


# =============================================================================
# Verification
# =============================================================================

class TestClaimVerification:
    """Tests for numeric claim verification."""

    def test_true_efl_claim(self):
        system = make_system()
        efl_mm = analyze_system(system).effective_focal_length * 1000.0
        result = verify_claim(system, "EFL is " + str(round(efl_mm, 3)) + "mm")
        assert result.verified
        assert result.kind == "EFL"

    def test_false_efl_claim(self):
        system = make_system()
        result = verify_claim(system, "EFL is 999 mm")
        assert not result.verified
        assert result.stated == 999.0

    def test_true_f_number_claim(self):
        system = make_system()
        fno = analyze_system(system).f_number
        result = verify_claim(system, "f/" + str(round(fno, 3)))
        assert result.verified
        assert result.kind == "f-number"

    def test_magnification_magnitude_matches_with_sign_note(self):
        system = make_system()
        mag = analyze_system(system).magnification
        result = verify_claim(system, "magnification is " + str(round(abs(mag), 3)) + "x")
        assert result.verified
        assert "inverted" in result.message or "erect" in result.message

    def test_true_rms_spot_claim(self):
        system = make_system()
        rms_um = analyze_system(system).rms_spot_radius * 1e6
        result = verify_claim(system, "RMS spot is " + str(round(rms_um, 2)) + " um")
        assert result.verified

    def test_diffraction_limited_claim_mismatch(self):
        system = make_system()
        result = verify_claim(system, "the system is diffraction limited")
        # This two-lens system is not diffraction limited, so the claim fails.
        assert not result.verified
        assert "NOT" in result.message

    def test_diffraction_limited_negated_claim_matches(self):
        system = make_system()
        result = verify_claim(system, "the system is not diffraction limited")
        assert result.verified

    def test_unparseable_claim(self):
        result = verify_claim(make_system(), "banana")
        assert not result.verified
        assert result.kind == "unknown"

    def test_verify_claims_batch(self):
        results = verify_claims(make_system(), ["EFL is 50 mm", "f/2.0", "banana"])
        assert len(results) == 3

    def test_result_as_dict(self):
        result = verify_claim(make_system(), "EFL is 50 mm")
        d = result.as_dict()
        assert d["kind"] == "EFL"
        assert "verified" in d


class TestDesignRuleChecks:
    """Tests for manufacturability rule checks."""

    def test_glass_availability_passes(self):
        findings = check_glass_availability(make_system())
        assert all(f.level == "info" for f in findings)

    def test_unknown_glass_is_an_error(self):
        system = make_system()
        system = system.model_copy(update={
            "components": [
                ThinLens(id="L1", position=0.1, focal_length=0.05,
                         aperture_diameter=0.025, material="NOT-A-GLASS"),
            ]
        })
        findings = check_glass_availability(system)
        assert any(f.level == "error" for f in findings)

    def test_edge_thickness_passes_for_sane_lens(self):
        findings = check_edge_thickness(make_system())
        assert all(f.level == "info" for f in findings)

    def test_aspect_ratio_flags_very_thin_lens(self):
        system = make_system()
        system = system.model_copy(update={
            "components": [
                ThickLens(id="T1", position=0.1, radius1=0.05, radius2=-0.05,
                          thickness=1e-4, aperture_diameter=0.050,
                          material="N-BK7"),
            ]
        })
        findings = check_element_aspect_ratio(system)
        assert any(f.rule == "aspect_ratio" for f in findings)

    def test_rule_check_summary_shape(self):
        summary = rule_check_summary(make_system())
        assert "findings" in summary
        assert "counts" in summary
        assert "passed" in summary

    def test_run_design_rule_checks_returns_list(self):
        findings = run_design_rule_checks(make_system())
        assert isinstance(findings, list)
        assert all(hasattr(f, "as_dict") for f in findings)


class TestPrescriptionVerification:
    """Tests for reference-prescription comparison."""

    def test_reference_library_is_populated(self):
        assert len(REFERENCE_DESIGNS) >= 8

    def test_count_elements(self):
        assert count_elements(make_system()) == 2

    def test_relay_matches_no_classic_class(self):
        # Two separated positive lenses that are neither afocal nor a
        # four-element Petzval form: no class should be claimed.
        cmp = verify_prescription(make_system())
        assert cmp.closest is None
        assert cmp.deltas["elements"] == 2
        assert cmp.deltas["power_signs"] == "++"
        assert cmp.summary

    @pytest.mark.parametrize("preset, expected", [
        ("achromat", "Achromatic doublet"),
        ("keplerian_telescope", "Keplerian telescope"),
        ("galilean_telescope", "Galilean telescope"),
        ("single_lens", "Singlet"),
    ])
    def test_known_systems_are_classified(self, preset, expected):
        from optics.presets import get_preset_by_id
        cmp = verify_prescription(get_preset_by_id(preset)["system"])
        assert cmp.closest is not None
        assert cmp.closest.name == expected
        assert cmp.notes

    def test_telephoto_ratio(self):
        # f1 = 100 mm, f2 = -50 mm, 60 mm apart: EFL = 500 mm, back focus
        # 200 mm, so length / EFL = (60 + 200) / 500 = 0.52.
        far = 1.0e5
        system = make_system().model_copy(update={
            "components": [
                ThinLens(id="L1", position=far, focal_length=0.1, aperture_diameter=0.02),
                ThinLens(id="L2", position=far + 0.06, focal_length=-0.05, aperture_diameter=0.01),
            ],
            "object": Object(position=0.0, height=100.0),
            "image_plane": ImagePlane(position=far + 0.26),
        })
        cmp = verify_prescription(system)
        assert cmp.closest.name == "Telephoto"
        assert cmp.deltas["efl_mm"] == pytest.approx(500.0, rel=1e-6)
        assert cmp.deltas["telephoto_ratio"] == pytest.approx(0.52, rel=1e-6)

    def test_as_dict(self):
        d = verify_prescription(make_system()).as_dict()
        assert "closest" in d
        assert "within_tolerance" in d

    def test_full_verification_shape(self):
        out = full_verification(make_system(), claims=["EFL is 50 mm"])
        assert "rules" in out
        assert "prescription" in out
        assert "claims" in out
        assert out["claims"][0]["kind"] == "EFL"

    def test_full_verification_without_claims(self):
        out = full_verification(make_system())
        assert "claims" not in out
