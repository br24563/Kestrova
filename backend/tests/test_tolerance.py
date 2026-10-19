"""
Tests for tolerance analysis (optics.tolerance) against independent
references:

- a power error of N fringes at lambda over diameter D changes the edge sag
  by N lambda / 2; the radius error must reproduce that with the exact
  sphere sag;
- sample statistics of the error distributions (Gaussian sigma, uniform
  bounds and mean (a + b) / 2, a Gaussian truncated at 3 sigma has standard
  deviation 0.98658 sigma);
- a thin lens decentered by d moves the image of an on-axis object by
  d (1 - m), m the lateral magnification;
- Monte Carlo, tornado, compensator and yield results on metrics whose
  answer is known exactly (linear and quadratic functions of parameters);
- Cpk = min(USL - mean, mean - LSL) / (3 sigma).
"""

import math
import random

import numpy as np
import pytest

from optics import raytrace as rt
from optics.analysis import analyze_system
from optics.materials import refractive_index
from optics.models import ThickLens
from optics.presets import get_preset_by_id
from optics.tolerance import (
    Compensator,
    ManufacturingErrors,
    ToleranceSpec,
    _draw_from_distribution,
    compute_yield,
    get_parameter,
    manufacturing_tolerances,
    perturb,
    sensitivity_analysis,
    set_parameter,
    tolerance_analysis,
    tolerance_with_compensators,
)


def single():
    return get_preset_by_id("single_lens")["system"]  # thin lens f = 0.1, m = -1


def thick():
    return get_preset_by_id("thick_lens")["system"]


def sphere_sag(R, h):
    return R - math.copysign(math.sqrt(R * R - h * h), R)


class TestManufacturingTolerances:

    def test_radius_error_gives_the_fringe_sag_change(self):
        s = thick()
        e = ManufacturingErrors(radius_error_fringes=2.0)
        tol = manufacturing_tolerances(s, e)
        lens = s.components[0]
        h = lens.aperture_diameter / 2
        for field in ("radius1", "radius2"):
            R = getattr(lens, field)
            dR = tol[f"TL1.{field}"]
            dsag = abs(sphere_sag(R + dR, h) - sphere_sag(R, h))
            assert dsag == pytest.approx(2.0 * e.test_wavelength / 2, rel=0.02)
        assert tol["TL1.thickness"] == pytest.approx(0.05e-3)
        assert tol["TL1.tilt_x"] == pytest.approx(math.radians(1 / 60))
        assert tol["TL1.decenter_y"] == pytest.approx(5e-6)

    def test_thin_lens_gets_alignment_tolerances_only(self):
        tol = manufacturing_tolerances(single())
        assert set(tol) == {"L1.position", "L1.decenter_y", "L1.tilt_x"}


class TestDistributions:

    N = 40000

    def draw(self, spec):
        rng = random.Random(1)
        return np.array([_draw_from_distribution(spec, rng) for _ in range(self.N)])

    def test_gaussian(self):
        v = self.draw(ToleranceSpec("p", 0.0, sigma=2e-6))
        assert v.std() == pytest.approx(2e-6, rel=0.02)
        assert abs(v.mean()) < 4 * 2e-6 / math.sqrt(self.N)

    def test_uniform(self):
        v = self.draw(ToleranceSpec("p", 0.0, "uniform", lower=-1.0, upper=3.0))
        assert v.min() >= -1.0 and v.max() <= 3.0
        assert v.mean() == pytest.approx(1.0, abs=0.03)
        assert v.std() == pytest.approx(4.0 / math.sqrt(12), rel=0.02)

    def test_truncated_gaussian(self):
        v = self.draw(ToleranceSpec("p", 0.0, "truncated_gaussian", sigma=1.0))
        assert np.max(np.abs(v)) <= 3.0
        assert v.std() == pytest.approx(0.98658, rel=0.02)
        assert _draw_from_distribution(
            ToleranceSpec("p", 0.0, "truncated_gaussian", sigma=0.0), random.Random(0)
        ) == 0.0

    def test_unknown_distribution(self):
        with pytest.raises(ValueError):
            _draw_from_distribution(ToleranceSpec("p", 0.0, "cauchy", sigma=1.0),
                                    random.Random(0))


class TestParameters:

    def test_get_and_set(self):
        s = single()
        assert get_parameter(s, "image_plane.position") == 0.4
        assert get_parameter(s, "object.position") == 0.0
        assert get_parameter(s, "L1.decenter_y") == 0.0
        s2 = set_parameter(s, "image_plane.position", 0.41)
        s2 = set_parameter(s2, "object.height", 0.02)
        s2 = perturb(s2, "L1.focal_length", 0.01)
        assert s2.image_plane.position == 0.41
        assert s2.object.height == 0.02
        assert s2.components[0].focal_length == pytest.approx(0.11)
        assert set_parameter(s, "L1.tilt_x", 0.0) is s

    @pytest.mark.parametrize("name", ["L9.position", "L1.radius7"])
    def test_unknown_parameters(self, name):
        with pytest.raises(ValueError):
            get_parameter(single(), name)
        with pytest.raises(ValueError):
            set_parameter(single(), name, 1.0)

    @pytest.mark.parametrize("d", [1e-4, -3e-4])
    def test_decentered_thin_lens_moves_the_image_by_d_times_1_minus_m(self, d):
        s = single()
        m = rt.first_order(s).magnification
        px, py = rt.pupil_grid(9)
        nominal, _, _ = rt.trace_field_rays(s, 0.0, 0.0, px, py)
        moved, _, _ = rt.trace_field_rays(perturb(s, "L1.decenter_y", d), 0.0, 0.0, px, py)
        y0 = nominal.image[nominal.valid, 1].mean()
        y1 = moved.image[moved.valid, 1].mean()
        assert y1 - y0 == pytest.approx(d * (1 - m), rel=1e-6)

    @pytest.mark.parametrize("deg", [2.0, -5.0])
    def test_tilted_plate_shifts_the_axial_ray_laterally(self, deg):
        # plane-parallel plate in the converging beam; the axis is restored
        # after it, so the axial ray exits displaced by
        # t sin(th) (1 - cos(th) / sqrt(n^2 - sin^2 th))
        t, th = 0.01, math.radians(deg)
        s = single()
        plate = ThickLens(id="P", position=0.3, radius1=1e12, radius2=1e12, thickness=t,
                          aperture_diameter=0.03, material="N-BK7")
        s = s.model_copy(update={"components": [*s.components, plate]})
        n = refractive_index("N-BK7", s.analysis_settings.wavelength)
        tilted = perturb(s, "P.tilt_x", th)
        assert [c.id for c in tilted.components][1:] == ["P__cb_in_tilt_x", "P",
                                                        "P__cb_out_tilt_x"]
        ray, _, _ = rt.trace_field_rays(tilted, 0.0, 0.0, np.zeros(1), np.zeros(1))
        shift = t * math.sin(th) * (1 - math.cos(th) / math.sqrt(n * n - math.sin(th) ** 2))
        assert abs(ray.image[0, 1]) == pytest.approx(abs(shift), rel=1e-9)


def lens_position(s):
    return get_parameter(s, "L1.position")


class TestMonteCarlo:

    def test_statistics_of_a_linear_metric(self):
        out = tolerance_analysis(single(), metric=lens_position,
                                 tolerances={"L1.position": 1e-4}, trials=3000, seed=5)
        assert out["nominal"] == 0.2
        assert out["mean"] == pytest.approx(0.2, abs=1e-5)
        assert out["std"] == pytest.approx(1e-4, rel=0.05)
        assert out["p95"] == pytest.approx(0.2 + 1.645e-4, abs=2e-5)
        assert out["worst"].components[0].position == out["max"]
        assert out["failed_trials"] == 0

    def test_failed_trials_are_counted(self):
        def metric(s):
            x = lens_position(s)
            if x > 0.2001:
                raise ValueError("vignetted")
            return math.inf if x < 0.1999 else x

        out = tolerance_analysis(single(), metric=metric,
                                 tolerances={"L1.position": 1e-4}, trials=2000, seed=2)
        # P(|z| > 1) = 0.3173 of trials fail
        assert out["failed_trials"] / 2000 == pytest.approx(0.3173, abs=0.03)
        assert out["trials"] + out["failed_trials"] == 2000

    def test_all_trials_failing_gives_nan(self):
        def metric(s):
            if s is not base:
                raise ValueError
            return 1.0

        base = single()
        out = tolerance_analysis(base, metric=metric, tolerances={"L1.position": 1e-4},
                                 trials=5)
        assert out["trials"] == 0 and math.isnan(out["mean"])

    def test_default_metric_and_tolerances(self):
        s = single()
        out = tolerance_analysis(s, trials=3)
        assert out["nominal"] == pytest.approx(analyze_system(s).rms_spot_radius)
        assert out["trials"] == 3


class TestSensitivity:

    def test_linear_metric_ranks_by_slope(self):
        def metric(s):
            return 1.0 + 2.0 * get_parameter(s, "L1.position") + 5.0 * get_parameter(
                s, "image_plane.position")

        out = sensitivity_analysis(single(), {"L1.position": 1e-3,
                                              "image_plane.position": ToleranceSpec(
                                                  "image_plane.position", 0.4, sigma=1e-3)},
                                   metric=metric)
        rows = {r["parameter"]: r for r in out["sensitivities"]}
        assert out["ranking"] == ["image_plane.position", "L1.position"]
        assert rows["L1.position"]["sensitivity"] == pytest.approx(2e-3)
        assert rows["image_plane.position"]["sensitivity"] == pytest.approx(5e-3)
        base = 1.0 + 0.4 + 2.0
        assert out["base_value"] == pytest.approx(base)
        assert rows["L1.position"]["relative_sensitivity"] == pytest.approx(2e-3 / base)

    def test_failing_side_is_nan(self):
        def metric(s):
            x = lens_position(s)
            if x < 0.2:
                raise ValueError
            return x

        row = sensitivity_analysis(single(), {"L1.position": 1e-3}, metric=metric)[
            "sensitivities"][0]
        assert math.isnan(row["value_minus"])
        assert row["sensitivity"] == pytest.approx(1e-3)


class TestCompensators:

    def test_refocus_recovers_a_quadratic_metric(self):
        def metric(s):
            return (get_parameter(s, "image_plane.position") - lens_position(s) - 0.2) ** 2

        comp = Compensator("focus", "image_plane.position", -1e-3, 1e-3)
        out = tolerance_with_compensators(single(), {"L1.position": 1e-4}, [comp],
                                          metric=metric, trials=40, seed=3)
        assert out["max"] < 1e-16
        stats = out["compensator_stats"]["focus"]
        # the focus moves with the lens: adjustments have the lens's sigma
        assert stats["std_adjustment"] == pytest.approx(1e-4, rel=0.3)
        assert stats["max_adjustment"] <= 1e-3

    def test_compensator_with_no_benefit_stays_put(self):
        out = tolerance_with_compensators(
            single(), {"L1.position": 1e-4},
            [Compensator("obj", "object.height", -1e-3, 1e-3)],
            metric=lens_position, trials=5,
        )
        assert out["compensator_stats"]["obj"]["max_adjustment"] == 0.0

    def test_all_failing(self):
        def metric(s):
            raise ValueError

        out = tolerance_with_compensators(single(), {"L1.position": 1e-4}, [],
                                          metric=metric, trials=3)
        assert out["trials"] == 0 and out["failed_trials"] == 3
        assert math.isnan(out["mean"])


class TestYield:

    def test_one_and_two_sided(self):
        samples = [1.0, 2.0, 3.0, 4.0, 5.0]
        mean, std = 3.0, math.sqrt(2.0)
        one = compute_yield(samples, upper_limit=4.0)
        assert one["yield"] == 0.8 and one["n_pass"] == 4
        assert one["cpk"] == pytest.approx((4.0 - mean) / (3 * std))
        two = compute_yield(samples, upper_limit=6.0, lower_limit=2.5)
        assert two["yield"] == 0.6
        assert two["cpk"] == pytest.approx((mean - 2.5) / (3 * std))

    def test_degenerate_samples(self):
        assert compute_yield([], 1.0)["n_total"] == 0
        assert compute_yield([0.5, 0.5], 1.0)["cpk"] == math.inf
        assert compute_yield([2.0, 2.0], 1.0)["cpk"] == 0.0
