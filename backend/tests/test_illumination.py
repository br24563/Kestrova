"""
Tests for illumination analysis (roadmap item 11).

Covers vignetting, relative illumination (cos^4 combined with measured
vignetting), the MTF field map and the MTF focus map.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from optics.illumination import (
    VignettingResult, cos4_falloff, chief_ray_image_angle,
    vignetting_at_field, vignetting_analysis,
    relative_illumination, mtf_field_map, mtf_focus_map,
    illumination_summary,
)
from optics.models import (
    OpticalSystem, ThinLens, ApertureStop, Object, ImagePlane, AnalysisSettings,
)


# Paraxial image of the relay below: L1 at 100 mm and L2 at 150 mm, both
# f = 50 mm, object at 0 with the image landing at 175 mm.
PARAXIAL_IMAGE_Z = 0.175


def create_focused_system(image_z=PARAXIAL_IMAGE_Z):
    """Two-lens relay with the image plane at the paraxial focus."""
    return OpticalSystem(
        components=[
            ThinLens(id="L1", position=0.100, focal_length=0.050,
                     aperture_diameter=0.025, material="N-BK7"),
            ThinLens(id="L2", position=0.150, focal_length=0.050,
                     aperture_diameter=0.025, material="N-BK7"),
        ],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=0.010, orientation=0.0),
        image_plane=ImagePlane(position=image_z),
        analysis_settings=AnalysisSettings(
            num_rays=11, ray_types=["chief", "marginal", "fill"],
            aperture_fraction=1.0, wavelength=550e-9,
        ),
    )


def create_stopped_system():
    """
    Relay with a 15 mm stop midway. The axial marginal ray then reaches
    L1 at 10 mm (< its 12.5 mm semi-aperture), so the stop limits the axial
    beam; at the field edge the oblique beam is clipped by L1's rim.
    """
    system = create_focused_system()
    system.components.append(
        ApertureStop(id="STO", position=0.125, diameter=0.015))
    return system


def create_wide_angle_lens(field_deg=30.0, f=0.1, diameter=0.01):
    """Ideal lens, stop at the lens, object effectively at infinity."""
    far = 1.0e6
    return OpticalSystem(
        components=[ThinLens(id="L1", position=far, focal_length=f,
                             aperture_diameter=diameter, material="N-BK7")],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=far * math.tan(math.radians(field_deg))),
        image_plane=ImagePlane(position=far + f),
        analysis_settings=AnalysisSettings(
            num_rays=11, ray_types=["chief"], aperture_fraction=1.0, wavelength=550e-9),
    )


def disk_irradiance(z, h, a):
    """Exact irradiance (up to a constant) at a point a distance z behind a
    uniformly bright disk of radius a, displaced h off its axis
    (the off-axis disk form factor)."""
    return math.pi / 2 * (1 - (z * z + h * h - a * a)
                          / math.sqrt((z * z + h * h + a * a) ** 2 - 4 * h * h * a * a))


class TestCos4Falloff:
    """The cos^4 obliquity law."""

    def test_zero_angle_is_unity(self):
        assert cos4_falloff(0.0) == pytest.approx(1.0)

    def test_thirty_degrees(self):
        expected = math.cos(math.radians(30)) ** 4
        assert cos4_falloff(math.radians(30)) == pytest.approx(expected)
        assert cos4_falloff(math.radians(30)) == pytest.approx(0.5625, rel=1e-9)

    def test_monotonic_decrease(self):
        values = [cos4_falloff(math.radians(a))
                  for a in range(0, 90, 10)]
        assert all(b <= a for a, b in zip(values, values[1:]))

    def test_ninety_degrees_is_zero(self):
        assert cos4_falloff(math.pi / 2) == pytest.approx(0.0, abs=1e-12)


class TestChiefRayImageAngle:
    """Chief-ray obliquity used by the cos^4 law."""

    def test_axial_is_zero(self):
        assert chief_ray_image_angle(create_focused_system(), 0.0) == pytest.approx(0.0, abs=1e-9)

    def test_increases_with_field(self):
        system = create_focused_system()
        angles = [chief_ray_image_angle(system, f) for f in (0.0, 0.5, 1.0)]
        assert angles[0] <= angles[1] <= angles[2]

    def test_non_negative(self):
        assert chief_ray_image_angle(create_focused_system(), 1.0) >= 0.0


class TestVignettingAtField:
    """Vignetting measurement at a single field point."""

    def test_returns_result_type(self):
        result = vignetting_at_field(create_focused_system(), 0.0)
        assert isinstance(result, VignettingResult)

    def test_axial_is_not_vignetted(self):
        result = vignetting_at_field(create_focused_system(), 0.0, num_rays=21)
        assert result.throughput == pytest.approx(1.0)
        assert result.is_vignetted is False
        assert result.loss_percent == pytest.approx(0.0)

    def test_wide_open_relay_passes_all_fields(self):
        system = create_focused_system()
        for field in (0.0, 0.5, 1.0):
            assert vignetting_at_field(system, field, num_rays=21).throughput == pytest.approx(1.0)

    def test_lens_rim_vignettes_off_axis(self):
        # Rays are aimed to fill the stop, so the stop itself never clips;
        # the oblique beam loses light at L1's rim.
        system = create_stopped_system()
        edge = vignetting_at_field(system, 1.0, num_rays=21)
        assert edge.throughput < 1.0
        assert edge.is_vignetted is True
        assert "L1" in edge.clipped_by
        assert "STO" not in edge.clipped_by

    def test_stop_leaves_axis_clear(self):
        system = create_stopped_system()
        axis = vignetting_at_field(system, 0.0, num_rays=21)
        assert axis.throughput == pytest.approx(1.0)
        assert axis.clipped_by == {}

    def test_counts_are_consistent(self):
        result = vignetting_at_field(create_stopped_system(), 1.0, num_rays=21)
        g = [-1 + 2 * k / 20 for k in range(21)]
        inside = sum(1 for x in g for y in g if x * x + y * y <= 1 + 1e-12)
        assert result.pupil_samples == inside
        assert result.passing_samples <= result.pupil_samples
        assert result.throughput == pytest.approx(
            result.passing_samples / result.pupil_samples)

    def test_as_dict_keys(self):
        d = vignetting_at_field(create_focused_system(), 0.0).as_dict()
        for key in ("field_fraction", "field_angle_rad", "field_angle_deg",
                    "throughput", "loss_percent", "is_vignetted",
                    "pupil_samples", "passing_samples", "clipped_by"):
            assert key in d

    def test_system_without_lenses_is_rejected(self):
        system = create_focused_system()
        system.components = []
        with pytest.raises(ValueError):
            vignetting_at_field(system, 1.0)


class TestVignettingAnalysis:
    """Vignetting across the field."""

    def test_keys(self):
        result = vignetting_analysis(create_focused_system(), num_fields=5, num_rays=11)
        for key in ("fields", "throughput", "worst_field", "worst_throughput",
                    "worst_loss_percent", "is_vignetted", "fields"):
            assert key in result

    def test_throughput_length_matches_field_count(self):
        result = vignetting_analysis(create_focused_system(), num_fields=7, num_rays=11)
        assert len(result["throughput"]) == 7
        assert len(result["fields"]) == 7

    def test_open_system_reports_unit_throughput(self):
        result = vignetting_analysis(create_focused_system(), num_fields=5, num_rays=21)
        assert max(result["throughput"]) == pytest.approx(1.0)
        assert result["is_vignetted"] is False

    def test_stopped_system_reports_loss(self):
        result = vignetting_analysis(create_stopped_system(), num_fields=5, num_rays=21)
        assert result["is_vignetted"] is True
        assert result["worst_loss_percent"] > 0.0
        assert min(result["throughput"]) < 1.0

    def test_worst_throughput_is_the_minimum(self):
        result = vignetting_analysis(create_stopped_system(), num_fields=5, num_rays=21)
        assert result["worst_throughput"] == pytest.approx(min(result["throughput"]))

class TestRelativeIllumination:
    """cos^4 obliquity combined with measured vignetting."""

    def test_keys(self):
        result = relative_illumination(create_focused_system(), num_fields=5, num_rays=11)
        for key in ("points", "field_fractions", "relative_illumination",
                    "cos4", "vignetting", "edge_relative_illumination",
                    "edge_loss_percent"):
            assert key in result

    def test_axis_is_normalised_to_one(self):
        result = relative_illumination(create_focused_system(), num_fields=5, num_rays=11)
        assert result["relative_illumination"][0] == pytest.approx(1.0)

    def test_never_exceeds_unity(self):
        result = relative_illumination(create_stopped_system(), num_fields=7, num_rays=21)
        assert max(result["relative_illumination"]) <= 1.0 + 1e-12

    def test_stopped_system_loses_light_off_axis(self):
        result = relative_illumination(create_stopped_system(), num_fields=7, num_rays=21)
        assert result["edge_relative_illumination"] < 1.0
        assert result["edge_loss_percent"] > 0.0

    def test_matches_exact_off_axis_disk_irradiance(self):
        # Stop at an ideal lens, object at infinity: the image is lit by a
        # uniform disk (the pupil) at distance f; its exact off-axis
        # irradiance differs from cos^4 at finite aperture (F/10 here).
        f, a = 0.1, 0.005
        result = relative_illumination(create_wide_angle_lens(30.0, f, 2 * a),
                                       num_fields=4, num_rays=21)
        for frac, ri in zip(result["field_fractions"], result["relative_illumination"]):
            h = f * math.tan(math.radians(30.0)) * frac
            expected = disk_irradiance(f, h, a) / disk_irradiance(f, 0.0, a)
            assert ri == pytest.approx(expected, abs=1e-5)

    def test_axial_projected_solid_angle_is_pi_sin2u(self):
        from optics.illumination import projected_solid_angle
        f, a = 0.1, 0.005
        omega = projected_solid_angle(create_wide_angle_lens(30.0, f, 2 * a), 0.0, 21)
        assert omega == pytest.approx(math.pi * math.sin(math.atan(a / f)) ** 2, rel=1e-6)

    def test_telecentric_relay_is_uniform(self):
        # The unstopped relay is telecentric in image space: no obliquity.
        result = relative_illumination(create_focused_system(), num_fields=5, num_rays=21)
        for ri in result["relative_illumination"]:
            assert ri == pytest.approx(1.0, abs=1e-9)


class TestMtfFieldMap:
    """MTF versus (field, frequency)."""

    def test_keys(self):
        result = mtf_field_map(create_focused_system(), num_fields=3, num_rays=11)
        for key in ("field_fractions", "frequencies_cyc_per_mm", "mtf",
                    "mtf_t", "mtf_s", "rms_wavefront_waves", "f_number"):
            assert key in result

    def test_shape_matches_requested_grid(self):
        result = mtf_field_map(
            create_focused_system(), frequencies=[10.0, 20.0, 30.0],
            num_fields=4, num_rays=11)
        assert len(result["mtf"]) == 4
        assert all(len(row) == 3 for row in result["mtf"])
        assert len(result["field_fractions"]) == 4

    def test_values_within_unit_interval(self):
        result = mtf_field_map(create_focused_system(), num_fields=3, num_rays=11)
        for row in result["mtf"]:
            for value in row:
                assert -1e-12 <= value <= 1.0 + 1e-12

    def test_f_number_is_reported(self):
        # Real marginal ray leaves L2 with slope 0.25 (paraxial F/2), so the
        # working F-number is 1 / (2 sin(atan 0.25)).
        result = mtf_field_map(create_focused_system(), num_fields=3, num_rays=11)
        assert result["f_number"] == pytest.approx(1 / (2 * math.sin(math.atan(0.25))), rel=1e-6)

    def test_aberration_free_relay_is_diffraction_limited(self):
        # Ideal lenses image perfectly: the MTF must be the diffraction
        # limit 2/pi (acos v - v sqrt(1 - v^2)), v = nu lambda N.
        result = mtf_field_map(create_focused_system(), frequencies=[20.0, 100.0],
                               num_fields=2, num_rays=64)
        n_w = result["f_number"]
        for row in result["mtf"]:
            for nu, m in zip([20.0, 100.0], row):
                v = nu * 1e3 * 550e-9 * n_w
                ideal = 2 / math.pi * (math.acos(v) - v * math.sqrt(1 - v * v))
                assert m == pytest.approx(ideal, abs=0.01)
        assert max(result["rms_wavefront_waves"]) < 1e-6

    def test_low_frequency_contrast_beats_high_frequency(self):
        result = mtf_field_map(
            create_focused_system(), frequencies=[2.0, 50.0],
            num_fields=3, num_rays=21)
        for row in result["mtf"]:
            assert row[0] >= row[1]

    def test_contrast_falls_towards_the_field_edge(self):
        # A real singlet: off-axis aberrations lower the edge contrast.
        from optics.presets import get_preset_by_id
        result = mtf_field_map(get_preset_by_id("thick_lens")["system"],
                               frequencies=[20.0], num_fields=3, num_rays=32)
        assert result["mtf"][0][0] > result["mtf"][-1][0]

    def test_wavefront_error_grows_with_field(self):
        from optics.presets import get_preset_by_id
        result = mtf_field_map(get_preset_by_id("thick_lens")["system"],
                               frequencies=[20.0], num_fields=3, num_rays=32)
        assert result["rms_wavefront_waves"][-1] > result["rms_wavefront_waves"][0]

    def test_default_frequencies_are_mm_based(self):
        result = mtf_field_map(create_focused_system(), num_fields=2, num_rays=11)
        assert result["frequencies_cyc_per_mm"] == [20.0, 40.0, 60.0, 80.0, 100.0]

    def test_tangential_equals_sagittal_on_axis(self):
        # Rotational symmetry: on axis the two sections must agree; off axis
        # a real singlet's astigmatism separates them.
        from optics.presets import get_preset_by_id
        result = mtf_field_map(get_preset_by_id("thick_lens")["system"],
                               frequencies=[20.0], num_fields=3, num_rays=32)
        assert result["mtf_t"][0][0] == pytest.approx(result["mtf_s"][0][0], abs=1e-6)
        assert abs(result["mtf_t"][-1][0] - result["mtf_s"][-1][0]) > 0.01


class TestMtfFocusMap:
    """MTF versus (defocus, frequency)."""

    def test_keys(self):
        result = mtf_focus_map(create_focused_system(), num_points=7, num_rays=11)
        for key in ("defocus_m", "defocus_um", "frequencies_cyc_per_mm", "mtf",
                    "best_defocus", "best_defocus_um", "best_mtf",
                    "depth_of_focus", "depth_of_focus_um", "field_fraction",
                    "f_number", "evaluation_frequency_cyc_per_mm"):
            assert key in result

    def test_shape_matches_requested_grid(self):
        result = mtf_focus_map(create_focused_system(), frequencies=[5.0, 15.0],
                               num_points=9, num_rays=11)
        assert len(result["defocus_um"]) == 9
        assert all(len(row) == 2 for row in result["mtf"])

    def test_best_focus_is_a_peak(self):
        result = mtf_focus_map(create_focused_system(), frequencies=[2.0],
                               num_points=11, num_rays=21)
        assert result["best_mtf"] >= max(result["mtf"][0]) - 1e-12
        for row in result["mtf"]:
            assert result["best_mtf"] >= row[0] - 1e-12

    def test_depth_of_focus_is_non_negative(self):
        result = mtf_focus_map(create_focused_system(), num_points=11, num_rays=21)
        assert result["depth_of_focus"] >= 0.0
        assert result["depth_of_focus_um"] >= 0.0

    def test_evaluation_frequency_is_reported(self):
        result = mtf_focus_map(create_focused_system(), frequencies=[5.0, 20.0],
                               num_points=7, num_rays=11)
        assert result["evaluation_frequency_cyc_per_mm"] in (5.0, 20.0)

    def test_values_within_unit_interval(self):
        result = mtf_focus_map(create_focused_system(), num_points=7, num_rays=11)
        for row in result["mtf"]:
            for value in row:
                assert -1e-12 <= value <= 1.0 + 1e-12


class TestIlluminationSummary:
    """Combined throughput report."""

    def test_keys(self):
        result = illumination_summary(create_focused_system(), num_fields=5, num_rays=11)
        for key in ("vignetting", "relative_illumination",
                    "edge_relative_illumination", "edge_loss_percent",
                    "meets_50pct_rule"):
            assert key in result

    def test_unvignetted_system_meets_the_50_percent_rule(self):
        result = illumination_summary(create_focused_system(), num_fields=5, num_rays=11)
        assert result["meets_50pct_rule"] is True
        assert result["edge_relative_illumination"] == pytest.approx(1.0)

    def test_heavy_vignetting_can_fail_the_rule(self):
        system = create_focused_system()
        system.components.append(
            ApertureStop(id="STO", position=0.125, diameter=0.008))
        result = illumination_summary(system, num_fields=5, num_rays=21)
        assert result["edge_relative_illumination"] < 1.0
        assert result["meets_50pct_rule"] == (
            result["edge_relative_illumination"] >= 0.50)

    def test_summary_includes_the_mtf_maps(self):
        result = illumination_summary(create_focused_system(), num_fields=5,
                                      num_rays=11, focus_points=9)
        assert len(result["mtf_field"]["field_fractions"]) == 5
        assert len(result["mtf_focus"]["defocus_m"]) == 9
        assert result["mtf_field"]["f_number"] == result["mtf_focus"]["f_number"]

    def test_mtf_maps_can_be_skipped(self):
        # The through-focus map traces a ray fan at every defocus position, so
        # it can be left out when only the throughput figures are wanted.
        result = illumination_summary(create_focused_system(), num_fields=5,
                                      num_rays=11, include_mtf=False)
        assert "mtf_field" not in result
        assert "mtf_focus" not in result
        assert "vignetting" in result
        assert "relative_illumination" in result
