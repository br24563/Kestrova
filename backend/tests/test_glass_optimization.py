"""
Tests for glass selection (optics.glass_optimization) against independent
references:

- thick lens in air (lensmaker): 1/f = (n-1)(c1 - c2 + (n-1) t c1 c2 / n),
  so df/dt = -f^2 (n-1)^2 c1 c2 / n;
- glass-map searches are checked by brute force over the catalog with the
  documented metric (relative differences in nd and Vd);
- merit operands are checked against the analysis they name.
"""

import math

import pytest

from optics.analysis import analyze_system
from optics.glass_optimization import (
    GlassRegion,
    MeritFunction,
    build_standard_merit_function,
    compute_partial_derivatives,
    evaluate_glass_substitution,
    find_best_glass_substitution,
    find_nearest_glasses,
    get_glasses_in_region,
    glass_expert_optimize,
)
from optics.materials import refractive_index
from optics.materials_expanded import ALL_MATERIALS, get_material_properties
from optics.presets import get_preset_by_id


def lens_system(material="N-BK7"):
    s = get_preset_by_id("thick_lens")["system"]
    lens = s.components[0].model_copy(update={"material": material})
    return s.model_copy(update={"components": [lens]})


def lensmaker(s):
    c = s.components[0]
    n = refractive_index(c.material, s.analysis_settings.wavelength)
    c1, c2, t = 1 / c.radius1, 1 / c.radius2, c.thickness
    return 1 / ((n - 1) * (c1 - c2 + (n - 1) * t * c1 * c2 / n)), n


def efl(s):
    return analyze_system(s).effective_focal_length


class TestGlassMap:

    def test_region_and_limits(self):
        got = get_glasses_in_region(GlassRegion.CROWN, min_nd=1.5, max_nd=1.6, min_vd=55,
                                    max_vd=70)
        expected = {
            k for k, p in ALL_MATERIALS.items()
            if p.nd is not None and p.vd is not None and p.material_type == "crown"
            and 1.5 <= p.nd <= 1.6 and 55 <= p.vd <= 70
        }
        assert {g.name for g in got} == expected and expected
        schott = get_glasses_in_region(manufacturers=["Schott"])
        assert schott and all(g.manufacturer == "Schott" for g in schott)

    def test_nearest_glasses_match_brute_force(self):
        ref = get_material_properties("N-BK7")
        got = find_nearest_glasses("N-BK7", n=6)

        def dist(p):
            return math.hypot((p.nd - ref.nd) / ref.nd, (p.vd - ref.vd) / ref.vd)

        brute = sorted(
            (dist(p), k) for k, p in ALL_MATERIALS.items()
            if p.nd is not None and p.vd is not None and k != "N-BK7"
        )[:6]
        assert [g.name for g in got] == [k for _, k in brute]
        assert [g.distance_from_current for g in got] == pytest.approx([d for d, _ in brute])

    def test_unknown_glass_has_no_neighbours(self):
        assert find_nearest_glasses("NOT-A-GLASS") == []


class TestSubstitution:

    def test_efl_change_matches_lensmaker(self):
        s = lens_system("N-BK7")
        res = evaluate_glass_substitution(s, "TL1", "N-SF11", efl)
        f_old, _ = lensmaker(s)
        f_new, _ = lensmaker(res.system)
        assert res.objective_change == pytest.approx(f_new - f_old, rel=1e-9)
        assert res.is_better == (f_new < f_old)
        assert res.nd_change == pytest.approx(ALL_MATERIALS["N-SF11"].nd
                                              - ALL_MATERIALS["N-BK7"].nd)
        assert res.vd_change == pytest.approx(ALL_MATERIALS["N-SF11"].vd
                                              - ALL_MATERIALS["N-BK7"].vd)

    def test_missing_component(self):
        with pytest.raises(ValueError):
            evaluate_glass_substitution(lens_system(), "nope", "N-SF11", efl)
        assert find_best_glass_substitution(lens_system(), "nope", efl) is None

    def test_best_candidate_is_closest_to_target_efl(self):
        s = lens_system("N-BK7")
        target = 0.08  # N-BK7 gives 0.098

        def objective(sys):
            return abs(efl(sys) - target)

        candidates = ["N-SK16", "N-SF11", "N-LAK22", "N-F2", "NOT-A-GLASS"]
        best = find_best_glass_substitution(s, "TL1", objective, candidates=candidates)

        def lensmaker_error(glass):
            return abs(lensmaker(lens_system(glass))[0] - target)

        expected = min(candidates[:-1], key=lensmaker_error)
        assert best.candidate_glass == expected
        assert best.objective_change == pytest.approx(
            lensmaker_error(expected) - lensmaker_error("N-BK7"), rel=1e-6)

    def test_no_better_candidate_gives_none(self):
        # every candidate overshoots a 0.097 m target from N-BK7's 0.098 m
        def objective(sys):
            return abs(efl(sys) - 0.097)

        assert find_best_glass_substitution(lens_system(), "TL1", objective,
                                            candidates=["N-SF11", "N-LAK22"]) is None

    def test_expert_walks_toward_a_target_index(self):
        s = lens_system("N-BK7")
        wl = s.analysis_settings.wavelength

        def objective(sys):
            return abs(refractive_index(sys.components[0].material, wl) - 1.56)

        res = glass_expert_optimize(s, objective, max_iterations=5, seed=1)
        assert res.success and res.substitutions_made
        assert res.objective_after < res.objective_before
        # the bookkeeping matches a fresh evaluation of the final system
        assert res.objective_after == pytest.approx(objective(res.optimized_system),
                                                    abs=1e-12)
        assert res.substitutions_made[0]["old_glass"] == "N-BK7"
        assert 1 <= res.n_iterations <= 5


class TestDerivativesAndMerit:

    def test_efl_thickness_derivative_is_analytic(self):
        s = lens_system()
        f, n = lensmaker(s)
        c = s.components[0]
        expected = -f * f * (n - 1) ** 2 / (c.radius1 * c.radius2 * n)
        d = compute_partial_derivatives(
            s, efl, [{"component_id": "TL1", "field": "thickness"},
                     {"component_id": "TL1", "field": "radius1"}])
        assert d["TL1.thickness"] == pytest.approx(expected, rel=1e-5)
        # df/dR1 = df/dc1 * (-1/R1^2), df/dc1 = -f^2 (n-1)(1 + (n-1) t c2 / n)
        dfdc1 = -f * f * (n - 1) * (1 + (n - 1) * c.thickness / (c.radius2 * n))
        assert d["TL1.radius1"] == pytest.approx(dfdc1 * -1 / c.radius1**2, rel=1e-5)

    def test_merit_function_sums_weighted_squares(self):
        s = lens_system()
        a = analyze_system(s)
        mf = MeritFunction()
        mf.add_operand("efl", 0.1, weight=2.0)
        mf.add_operand("magnification", -1.0)
        value = mf.evaluate(s)
        expected = 2.0 * (a.effective_focal_length - 0.1) ** 2 + (a.magnification + 1.0) ** 2
        assert value == pytest.approx(expected) and mf.value == value
        assert mf.operands[0].value == pytest.approx(a.effective_focal_length)

    @pytest.mark.parametrize("name", ["rms_spot", "bfl", "image_distance", "f_number", "na"])
    def test_every_operand_evaluates(self, name):
        mf = MeritFunction()
        mf.add_operand(name, 0.0)
        assert math.isfinite(mf.evaluate(lens_system()))

    def test_unknown_operand(self):
        mf = MeritFunction()
        mf.add_operand("strehl", 1.0)
        with pytest.raises(ValueError, match="Unknown merit operand"):
            mf.evaluate(lens_system())

    def test_standard_merit_function(self):
        mf = build_standard_merit_function(target_efl=0.1, target_magnification=-1.0,
                                           weights={"rms_spot": 3.0})
        assert [(o.name, o.target, o.weight) for o in mf.operands] == [
            ("efl", 0.1, 1.0), ("magnification", -1.0, 1.0), ("rms_spot", 0.0, 3.0)]
        assert build_standard_merit_function(min_spot_size=False).operands == []
