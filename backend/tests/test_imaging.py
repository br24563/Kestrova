"""
Tests for the image simulator (roadmap item 11).

Covers the sensor model, the f-number and magnification helpers, the Airy
and system PSFs, the object test targets, the noise/exposure chain, the
full-field image simulation, MTF measurement from a bar target, radial
distortion and illumination, and the stdlib-only PNG writer.
"""

import math
import os
import struct
import sys
import zlib

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from optics.imaging import (
    SensorConfig, SimulationResult, TEST_TARGETS,
    effective_f_number, working_f_number, magnification,
    object_pixel_pitch, field_of_view,
    airy_psf, psf_for_system, rms_spot_radius,
    test_target, bars_band_rows, sensor_response, simulate_image,
    distortion_curve, relative_illumination_profile, relative_illumination_map,
    mtf_from_bar_target, image_quality_metrics, image_statistics,
    encode_png_gray, save_png, ascii_preview,
)
# ``_distort`` is module-private, but it carries a subtle sign convention that
# is worth pinning down directly with a synthetic distortion curve.
from optics.imaging import _distort
from optics.models import (
    OpticalSystem, ThinLens, ApertureStop, Object, ImagePlane, AnalysisSettings,
)

# ``test_target`` is a helper imported from the module under test; stop pytest
# from collecting it as a test of its own.
test_target.__test__ = False


def create_relay_system(image_z=0.175, aperture=0.025, object_height=0.010):
    """Two-thin-lens 0.5x relay; paraxial image at z = 175 mm."""
    return OpticalSystem(
        components=[
            ThinLens(id="L1", position=0.100, focal_length=0.050,
                     aperture_diameter=aperture, material="N-BK7"),
            ThinLens(id="L2", position=0.150, focal_length=0.050,
                     aperture_diameter=aperture, material="N-BK7"),
        ],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=object_height, orientation=0.0),
        image_plane=ImagePlane(position=image_z),
        analysis_settings=AnalysisSettings(num_rays=11, wavelength=550e-9),
    )


def create_singlet_system(sensor=None, aperture=0.0125, object_height=None,
                          image_z=0.200, lens_z=0.100, focal_length=0.050):
    """
    Single thin lens at 1:1 (lens at 2f, image at 4f), m = -1.

    With ``object_height`` left at None the object is sized so that the edge
    of the field lands exactly on the sensor's half-diagonal, which is the
    convention ``simulate_image(full_field=True)`` assumes.
    """
    if sensor is None:
        sensor = SensorConfig()
    if object_height is None:
        object_height = sensor.half_diagonal() / 1.0     # |m| = 1
    return OpticalSystem(
        components=[ThinLens(id="L1", position=lens_z, focal_length=focal_length,
                             aperture_diameter=aperture, material="N-BK7")],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=object_height, orientation=0.0),
        image_plane=ImagePlane(position=image_z),
        analysis_settings=AnalysisSettings(num_rays=11, wavelength=550e-9),
    )


def create_real_singlet(aperture=0.0125, object_height=0.004, defocus=0.0):
    """
    Equiconvex N-BK7 singlet (R = +/-51.5 mm, 5 mm thick, f ~ 50 mm) at
    about 1:1, image plane at its paraxial image (+ defocus). Unlike the
    ideal ThinLens it has real spherical aberration, coma and astigmatism.
    """
    from optics.models import ThickLens
    from optics.raytrace import first_order
    system = OpticalSystem(
        components=[ThickLens(id="L1", position=0.100, radius1=0.0515, radius2=-0.0515,
                              thickness=0.005, aperture_diameter=aperture, material="N-BK7")],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=object_height, orientation=0.0),
        image_plane=ImagePlane(position=0.3),
        analysis_settings=AnalysisSettings(num_rays=11, wavelength=550e-9),
    )
    z = first_order(system).image_z
    return system.model_copy(update={"image_plane": ImagePlane(position=z + defocus)})


def create_apertureless_system():
    """A system with no aperture-bearing component at all."""
    return OpticalSystem(
        components=[],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=0.005, orientation=0.0),
        image_plane=ImagePlane(position=0.100),
        analysis_settings=AnalysisSettings(num_rays=11, wavelength=550e-9),
    )


def create_wide_field_system():
    """A 26.6 degree object-space half-field, for illumination falloff."""
    return create_singlet_system(object_height=0.050)


def fwhm_pixels(psf):
    """Interpolated full width at half maximum of a PSF, along the centre row."""
    psf = np.asarray(psf, dtype=float)
    row = psf[psf.shape[0] // 2]
    centre = int(np.argmax(row))
    half = row[centre] / 2.0
    if half <= 0:
        return float("nan")
    right = None
    for i in range(centre, len(row) - 1):
        if row[i] >= half >= row[i + 1] and row[i] > row[i + 1]:
            right = i + (row[i] - half) / (row[i] - row[i + 1])
            break
    left = None
    for i in range(centre, 0, -1):
        if row[i] >= half >= row[i - 1] and row[i] > row[i - 1]:
            left = i - (row[i] - half) / (row[i] - row[i - 1])
            break
    if left is None or right is None:
        return float("nan")
    return right - left


class TestSensorConfig:
    """Detector defaults and derived quantities."""

    def test_defaults_describe_a_small_cmos(self):
        s = SensorConfig()
        assert s.resolution == 128
        assert s.pixel_pitch == pytest.approx(5.0e-6)
        assert 0.0 < s.quantum_efficiency <= 1.0
        assert s.full_well > 0
        assert s.read_noise > 0
        assert s.bit_depth >= 8

    def test_max_adu_follows_the_bit_depth(self):
        assert SensorConfig(bit_depth=8).max_adu == 255
        assert SensorConfig(bit_depth=12).max_adu == 4095
        assert SensorConfig(bit_depth=16).max_adu == 65535

    def test_half_diagonal(self):
        s = SensorConfig(resolution=100, pixel_pitch=10e-6)
        expected = math.sqrt(2) * 100 * 10e-6 / 2.0
        assert s.half_diagonal() == pytest.approx(expected)

    def test_default_gain_matches_the_full_well_to_the_adc(self):
        # ADC full scale must not clip the signal before the well fills.
        s = SensorConfig()
        assert s.max_adu * s.gain == pytest.approx(s.full_well, rel=0.001)

    def test_field_of_view_uses_the_resolution_and_magnification(self):
        s = SensorConfig()
        system = create_singlet_system(sensor=s)
        assert field_of_view(system, s) == pytest.approx(
            s.resolution * object_pixel_pitch(system, s))


class TestFNumberAndMagnification:
    """f-number, magnification and the derived object-space sampling."""

    def test_effective_f_number_is_efl_over_diameter(self):
        # The relay has EFL = 50 mm and a 25 mm aperture.
        assert effective_f_number(create_relay_system()) == pytest.approx(
            2.0, rel=1e-6)

    def test_effective_f_number_is_positive_and_finite(self):
        value = effective_f_number(create_relay_system())
        assert math.isfinite(value) and value > 0

    def test_stopping_down_raises_the_f_number(self):
        wide = effective_f_number(create_relay_system(aperture=0.025))
        narrow = effective_f_number(create_relay_system(aperture=0.00625))
        assert narrow == pytest.approx(4.0 * wide, rel=0.01)

    def test_a_system_without_an_aperture_has_no_finite_f_number(self):
        assert math.isinf(effective_f_number(create_apertureless_system()))

    def test_working_f_number_exceeds_the_paraxial_one(self):
        # A finite conjugate presents N(1 + |m|) to the image.
        system = create_relay_system()
        assert working_f_number(system) >= effective_f_number(system)

    def test_working_f_number_of_a_1to1_system(self):
        # m = -1, so the image-side cone is about half the paraxial one.
        system = create_singlet_system()
        assert magnification(system) == pytest.approx(-1.0, rel=1e-6)
        assert working_f_number(system) == pytest.approx(
            2.0 * effective_f_number(system), rel=0.02)

    def test_magnification_follows_the_lens_dispersion(self):
        # The ideal lens has f = 50 mm at the reference wavelength (550 nm);
        # at 587.6 nm f scales by (n_550 - 1)/(n_587.6 - 1) of N-BK7, and the
        # thin-lens equation with the object 100 mm away gives m.
        from optics.materials import refractive_index
        system = create_singlet_system()
        assert magnification(system) == pytest.approx(-1.0, rel=1e-9)
        f = 0.050 * (refractive_index("N-BK7", 550e-9) - 1) / (refractive_index("N-BK7", 587.6e-9) - 1)
        s_img = 1.0 / (1.0 / f - 1.0 / 0.100)
        assert magnification(system, 587.6e-9) == pytest.approx(-s_img / 0.100, rel=1e-9)

    def test_magnification_of_the_relay(self):
        assert magnification(create_relay_system()) == pytest.approx(
            -0.5, rel=0.01)

    def test_magnification_does_not_depend_on_object_height(self):
        assert magnification(create_relay_system(object_height=0.0)) == pytest.approx(-0.5, rel=1e-9)

    def test_object_pixel_pitch_divides_by_magnification(self):
        s = SensorConfig()
        system = create_singlet_system(sensor=s)
        # The singlet is exactly 1:1 at the catalog reference, so one object
        # pixel maps onto one sensor pixel.
        assert magnification(system) == pytest.approx(-1.0, rel=1e-6)
        assert object_pixel_pitch(system, s) == pytest.approx(
            s.pixel_pitch / 1.0, rel=1e-3)

    def test_object_pixel_pitch_shrinks_for_a_reducing_system(self):
        s = SensorConfig()
        system = create_relay_system()
        # |m| = 0.5, so an object pixel spans two sensor pixels.
        assert object_pixel_pitch(system, s) == pytest.approx(
            s.pixel_pitch / 0.5, rel=0.02)

    def test_field_of_view_scales_with_resolution(self):
        small = SensorConfig(resolution=64)
        large = SensorConfig(resolution=128)
        system = create_singlet_system()
        assert field_of_view(system, large) == pytest.approx(
            2.0 * field_of_view(system, small), rel=1e-6)


class TestAiryPsf:
    """Diffraction-limited PSF on the pixel grid."""

    def test_sums_to_one(self):
        assert airy_psf(4.0, 550e-9, 0.5e-6).sum() == pytest.approx(1.0)

    def test_is_normalised_over_a_range_of_f_numbers(self):
        for n in (1.0, 2.0, 8.0, 32.0):
            assert airy_psf(n, 550e-9, 0.5e-6).sum() == pytest.approx(1.0)

    def test_peak_is_at_the_centre(self):
        psf = airy_psf(4.0, 550e-9, 0.5e-6)
        centre = (psf.shape[0] // 2, psf.shape[1] // 2)
        assert psf[centre] == psf.max()

    def test_is_symmetric(self):
        psf = airy_psf(4.0, 550e-9, 0.5e-6)
        assert np.allclose(psf, psf[::-1, :])
        assert np.allclose(psf, psf[:, ::-1])

    def test_is_non_negative(self):
        assert airy_psf(4.0, 550e-9, 0.5e-6).min() >= 0.0

    def test_main_lobe_falls_off_from_the_centre(self):
        psf = airy_psf(8.0, 550e-9, 0.25e-6)
        c = psf.shape[0] // 2
        core = psf[c, c:c + 10]
        assert all(b <= a + 1e-12 for a, b in zip(core, core[1:]))

    def test_fwhm_scales_with_f_number(self):
        # FWHM = 1.028 lambda N, so doubling N doubles the blur.
        f4 = fwhm_pixels(airy_psf(4.0, 550e-9, 0.25e-6))
        f8 = fwhm_pixels(airy_psf(8.0, 550e-9, 0.25e-6))
        f16 = fwhm_pixels(airy_psf(16.0, 550e-9, 0.25e-6))
        assert f8 / f4 == pytest.approx(2.0, rel=0.10)
        assert f16 / f8 == pytest.approx(2.0, rel=0.10)

    def test_fwhm_matches_the_airy_formula(self):
        wavelength, n, pitch = 550e-9, 16.0, 0.25e-6
        expected_px = 1.028 * wavelength * n / pitch
        assert fwhm_pixels(airy_psf(n, wavelength, pitch)) == pytest.approx(
            expected_px, rel=0.05)

    def test_fwhm_scales_with_wavelength(self):
        red = fwhm_pixels(airy_psf(8.0, 650e-9, 0.25e-6))
        blue = fwhm_pixels(airy_psf(8.0, 450e-9, 0.25e-6))
        assert red / blue == pytest.approx(650.0 / 450.0, rel=0.05)

    def test_infinite_f_number_is_a_delta(self):
        psf = airy_psf(float("inf"), 550e-9, 5e-6)
        assert psf.sum() == pytest.approx(1.0)
        assert psf[psf.shape[0] // 2, psf.shape[1] // 2] == pytest.approx(1.0)

    def test_zero_f_number_is_a_delta(self):
        psf = airy_psf(0.0, 550e-9, 5e-6)
        assert psf.sum() == pytest.approx(1.0)

    def test_explicit_size_is_respected(self):
        assert airy_psf(4.0, 550e-9, 5e-6, size=51).shape == (51, 51)

    def test_grid_is_sized_to_contain_the_disk(self):
        coarse = airy_psf(2.0, 550e-9, 0.25e-6).shape[0]
        fine = airy_psf(16.0, 550e-9, 0.25e-6).shape[0]
        assert fine > coarse


class TestSystemPsf:
    """PSF of a real system and the geometric spot it is built from."""

    def test_psf_sums_to_one(self):
        assert psf_for_system(create_singlet_system(), 0.0).sum() == pytest.approx(1.0)

    def test_psf_is_non_negative(self):
        assert psf_for_system(create_singlet_system(), 0.0).min() >= 0.0

    def test_ideal_lens_has_no_spot(self):
        # An ideal lens images a point to a point.
        assert rms_spot_radius(create_singlet_system(), 0.0) < 1e-12

    def test_real_singlet_spot_is_positive_on_axis(self):
        assert rms_spot_radius(create_real_singlet(), 0.0) > 1e-6

    def test_rms_spot_grows_with_aperture(self):
        # Third-order spherical aberration: transverse blur ~ aperture^3.
        small = rms_spot_radius(create_real_singlet(aperture=0.00625), 0.0)
        large = rms_spot_radius(create_real_singlet(aperture=0.0125), 0.0)
        assert large / small == pytest.approx(8.0, rel=0.25)

    def test_rms_spot_grows_with_field(self):
        system = create_real_singlet(object_height=0.004)
        assert rms_spot_radius(system, 1.0) > rms_spot_radius(system, 0.0)

    def test_system_without_surfaces_is_rejected(self):
        with pytest.raises(ValueError):
            rms_spot_radius(create_apertureless_system(), 0.0)

    def test_defocus_broadens_the_psf(self):
        sharp = psf_for_system(create_real_singlet(aperture=0.004), 0.0)
        blurred = psf_for_system(create_real_singlet(aperture=0.004, defocus=0.002), 0.0)
        assert fwhm_pixels(blurred) > fwhm_pixels(sharp)
        assert blurred.sum() == pytest.approx(1.0)

    def test_a_perfect_system_psf_is_the_airy_disk(self):
        # Ideal lens: the FFT PSF integrated into pixels must equal the
        # analytic Airy pattern for the real working F-number.
        system = create_singlet_system()
        sensor = SensorConfig()
        sharp = psf_for_system(system, 0.0, sensor, size=15)
        expected = airy_psf(working_f_number(system), 550e-9, sensor.pixel_pitch, size=15)
        assert np.abs(sharp - expected).max() < 0.015 * expected.max()

    def test_slower_system_has_a_broader_psf(self):
        fast = psf_for_system(create_singlet_system(aperture=0.025), 0.0)
        slow = psf_for_system(create_singlet_system(aperture=0.003125), 0.0)
        assert fwhm_pixels(slow) > fwhm_pixels(fast)


class TestTestTargets:
    """Object-plane test patterns."""

    def test_target_names_are_the_documented_set(self):
        assert set(TEST_TARGETS) == {
            "bars", "siemens", "grid", "checkerboard", "edge", "point", "flat"}

    @pytest.mark.parametrize("kind", TEST_TARGETS)
    def test_every_target_has_the_right_shape_and_range(self, kind):
        t = test_target(kind, 64)
        assert t.shape == (64, 64)
        assert t.dtype == np.float64
        assert t.min() >= 0.0
        assert t.max() <= 1.0

    @pytest.mark.parametrize("kind", [k for k in TEST_TARGETS if k != "flat"])
    def test_every_target_spans_the_full_range_by_default(self, kind):
        # ``flat`` is deliberately uniform, so it is excluded here.
        assert test_target(kind, 64).max() == pytest.approx(1.0)
        assert test_target(kind, 64).min() == pytest.approx(0.0)

    def test_unknown_target_is_rejected(self):
        with pytest.raises(ValueError):
            test_target("not-a-target", 32)

    def test_target_name_is_case_insensitive(self):
        assert np.array_equal(test_target("BARS", 32), test_target("bars", 32))

    def test_flat_is_uniform(self):
        t = test_target("flat", 32)
        assert np.all(t == 1.0)

    def test_point_is_a_single_centre_pixel(self):
        t = test_target("point", 33)
        assert np.count_nonzero(t) == 1
        assert t[16, 16] == 1.0

    def test_edge_is_a_half_field_step(self):
        t = test_target("edge", 32)
        assert np.all(t[:, :16] == 0.0)
        assert np.all(t[:, 16:] == 1.0)

    def test_bars_is_binary_and_half_filled(self):
        t = test_target("bars", 128)
        assert set(np.unique(t)) <= {0.0, 1.0}
        assert t.mean() == pytest.approx(0.5, abs=0.01)

    def test_bars_alternate_at_the_expected_period(self):
        t = test_target("bars", 128)
        row = t[8]
        # The first band has a 4-pixel period: 1 1 0 0 repeating.
        assert list(row[:8]) == [1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]

    def test_bars_bands_are_ordered_from_finest_to_coarsest(self):
        t = test_target("bars", 128)

        def transitions(row):
            return int(np.count_nonzero(np.diff(row) != 0))

        counts = [transitions(t[next(iter(bars_band_rows(128, i, 4)))])
                  for i in range(4)]
        assert all(b < a for a, b in zip(counts, counts[1:]))

    def test_bars_duty_changes_the_fill(self):
        sparse = test_target("bars", 128, duty=0.25)
        dense = test_target("bars", 128, duty=0.75)
        assert sparse.mean() == pytest.approx(0.25, abs=0.01)
        assert dense.mean() == pytest.approx(0.75, abs=0.01)

    def test_grid_has_both_horizontal_and_vertical_lines(self):
        t = test_target("grid", 64, line_width=2)
        # A grid column and a grid row both carry bright pixels.
        assert t[0].max() == 1.0            # vertical lines reach the top row
        assert t[:, 0].max() == 1.0         # horizontal lines reach column 0
        assert 0.0 < t.mean() < 1.0

    def test_checkerboard_is_binary_and_modulated(self):
        t = test_target("checkerboard", 128)
        assert set(np.unique(t)) <= {0.0, 1.0}
        assert 0.0 < t.mean() < 1.0

    def test_siemens_star_has_spokes(self):
        t = test_target("siemens", 128, num_spokes=36)
        assert set(np.unique(t)) <= {0.0, 1.0}
        # Walking a circle around the centre must cross spokes repeatedly.
        theta = np.linspace(0.0, 2.0 * math.pi, 400, endpoint=False)
        radius = 50.0
        ys = np.round(63.5 + radius * np.sin(theta)).astype(int)
        xs = np.round(63.5 + radius * np.cos(theta)).astype(int)
        ring = t[ys, xs]
        assert np.count_nonzero(np.diff(ring) != 0) >= 20

    def test_size_is_respected_and_clamped_to_a_minimum(self):
        assert test_target("flat", 37).shape == (37, 37)
        assert test_target("flat", 2).shape == (4, 4)
        assert test_target("flat", 1).shape == (4, 4)

    def test_contrast_and_background_scale_the_pattern(self):
        t = test_target("flat", 8, contrast=0.5, background=0.25)
        assert np.allclose(t, 0.75)
        dark = test_target("flat", 8, contrast=0.0, background=0.3)
        assert np.allclose(dark, 0.3)

    def test_result_never_leaves_the_unit_range(self):
        t = test_target("bars", 32, contrast=2.0, background=1.0)
        assert t.min() >= 0.0 and t.max() <= 1.0


class TestBarsBandRows:
    """Row ranges of the bar-target bands."""

    def test_four_bands_tile_the_image_in_order(self):
        bands = [list(bars_band_rows(128, i, 4)) for i in range(4)]
        assert all(b for b in bands)
        assert all(bands[i][-1] < bands[i + 1][0] for i in range(3))

    def test_rows_stay_inside_the_image(self):
        for i in range(4):
            rows = list(bars_band_rows(128, i, 4))
            assert rows[0] >= 0
            assert rows[-1] < 128

    def test_last_band_reaches_the_bottom(self):
        rows = list(bars_band_rows(128, 3, 4))
        assert rows[-1] >= 100

    def test_band_measuring_window_avoids_the_band_edges(self):
        # The measurement window must sit strictly inside its band so that
        # bleed from a neighbouring band cannot contaminate the fundamental.
        band_h = 128 // 4
        for i in range(4):
            rows = list(bars_band_rows(128, i, 4))
            assert rows[0] >= i * band_h
            assert rows[-1] < (i + 1) * band_h
            assert len(rows) >= 8


class TestSensorResponse:
    """Exposure, noise and digitisation."""

    def test_exposure_scales_the_signal_to_the_requested_well_fraction(self):
        s = SensorConfig()
        r = sensor_response(np.ones((8, 8)), s, noise=False)
        assert r["peak_electrons"] == pytest.approx(0.8 * s.full_well)

    def test_default_gain_does_not_clip_in_the_adc(self):
        # The default gain is chosen so the ADC spans the full well.
        s = SensorConfig()
        r = sensor_response(np.ones((8, 8)), s, noise=False)
        assert r["saturated_pixels"] == 0
        assert r["peak_electrons"] < s.full_well
        assert r["adu"].max() < s.max_adu

    def test_low_gain_clips_in_the_adc_and_is_reported_as_saturation(self):
        # With a low gain the ADC is the limiting element; the signal
        # saturates long before the well fills, and that must be visible.
        s = SensorConfig(gain=2.0)
        r = sensor_response(np.ones((8, 8)), s, noise=False)
        assert r["adc_full_scale_electrons"] == pytest.approx(2.0 * s.max_adu)
        assert r["peak_electrons"] < s.full_well      # the well never filled
        assert r["saturated_pixels"] == 64            # yet every pixel clipped
        assert r["adu"].max() == s.max_adu

    def test_high_gain_makes_the_full_well_the_limit(self):
        s = SensorConfig(gain=100.0)
        r = sensor_response(np.ones((8, 8)), s, noise=False)
        assert r["saturated_pixels"] == 0
        over = sensor_response(np.ones((8, 8)), s, noise=False,
                               peak_fraction_of_full_well=1.5)
        assert over["saturated_pixels"] == 64

    def test_digitised_image_is_adu_over_full_scale(self):
        s = SensorConfig()
        r = sensor_response(np.ones((8, 8)), s, noise=False)
        assert np.allclose(r["image"], r["adu"].astype(float) / s.max_adu)

    def test_outputs_stay_in_range(self):
        s = SensorConfig()
        r = sensor_response(test_target("bars", 32), s, seed=7)
        assert r["adu"].dtype == np.uint16
        assert r["adu"].min() >= 0
        assert r["adu"].max() <= s.max_adu
        assert 0.0 <= r["image"].min() and r["image"].max() <= 1.0

    def test_noiseless_mode_is_deterministic(self):
        s = SensorConfig()
        a = sensor_response(test_target("bars", 32), s, noise=False)
        b = sensor_response(test_target("bars", 32), s, noise=False)
        assert np.array_equal(a["adu"], b["adu"])

    def test_seed_makes_the_noise_repeatable(self):
        s = SensorConfig()
        a = sensor_response(test_target("bars", 32), s, seed=123)
        b = sensor_response(test_target("bars", 32), s, seed=123)
        c = sensor_response(test_target("bars", 32), s, seed=456)
        assert np.array_equal(a["adu"], b["adu"])
        assert not np.array_equal(a["adu"], c["adu"])

    def test_noise_perturbs_the_signal_around_the_ideal(self):
        s = SensorConfig()
        ideal = sensor_response(np.ones((32, 32)), s, noise=False)
        noisy = sensor_response(np.ones((32, 32)), s, seed=5)
        assert noisy["peak_electrons"] == pytest.approx(
            ideal["peak_electrons"], rel=0.05)

    def test_snr_scales_as_the_square_root_of_the_signal(self):
        s = SensorConfig()
        bright = sensor_response(np.ones((8, 8)), s, noise=False,
                                 peak_fraction_of_full_well=0.8)
        dim = sensor_response(np.ones((8, 8)), s, noise=False,
                              peak_fraction_of_full_well=0.2)
        # Four times the signal is twice the SNR, up to read noise.
        assert bright["peak_snr"] / dim["peak_snr"] == pytest.approx(2.0, rel=0.03)
        assert bright["mean_snr"] > dim["mean_snr"]

    def test_snr_approaches_photon_limited_for_a_strong_signal(self):
        s = SensorConfig()
        r = sensor_response(np.ones((8, 8)), s, noise=False)
        expected = 0.8 * s.full_well / math.sqrt(0.8 * s.full_well
                                                 + s.read_noise ** 2)
        assert r["peak_snr"] == pytest.approx(expected, rel=1e-6)

    def test_read_noise_sets_the_floor_for_a_empty_image(self):
        s = SensorConfig()
        r = sensor_response(np.zeros((8, 8)), s, seed=3)
        assert r["mean_snr"] == pytest.approx(0.0, abs=0.5)

    def test_an_all_zero_image_is_handled(self):
        s = SensorConfig()
        r = sensor_response(np.zeros((4, 4)), s, noise=False)
        assert np.all(r["adu"] == 0)
        assert r["peak_electrons"] == pytest.approx(0.0)

    def test_dark_current_adds_a_constant_offset(self):
        clean = SensorConfig(dark_current=0.0, read_noise=0.0,
                             quantum_efficiency=1.0)
        dark = SensorConfig(dark_current=10000.0, exposure_time=1.0,
                            read_noise=0.0, quantum_efficiency=1.0)
        a = sensor_response(np.ones((4, 4)), clean, noise=False)
        b = sensor_response(np.ones((4, 4)), dark, noise=False)
        assert b["peak_electrons"] > a["peak_electrons"]

    def test_quantum_efficiency_does_not_change_the_mean_signal(self):
        # QE changes the photon count, not the detected electron count for a
        # fixed exposure target.
        high = SensorConfig(quantum_efficiency=1.0)
        low = SensorConfig(quantum_efficiency=0.2)
        a = sensor_response(np.ones((4, 4)), high, noise=False)
        b = sensor_response(np.ones((4, 4)), low, noise=False)
        assert a["peak_electrons"] == pytest.approx(b["peak_electrons"])

    def test_report_includes_the_adc_scale(self):
        s = SensorConfig()
        r = sensor_response(np.ones((4, 4)), s, noise=False)
        assert r["adc_full_scale_electrons"] == pytest.approx(s.max_adu * s.gain)
        assert r["max_adu"] == s.max_adu


class TestSimulateImage:
    """The end-to-end image simulation."""

    def test_returns_a_complete_result(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        assert isinstance(sim, SimulationResult)
        for name in ("image", "adu", "electrons", "ideal", "psf",
                     "illumination"):
            assert isinstance(getattr(sim, name), np.ndarray)
        assert isinstance(sim.metadata, dict)

    def test_arrays_match_the_sensor_resolution(self):
        s = SensorConfig(resolution=64)
        sim = simulate_image(create_singlet_system(sensor=s), target_kind="bars",
                             sensor=s, with_noise=False)
        for name in ("image", "adu", "electrons", "ideal", "illumination"):
            assert getattr(sim, name).shape == (64, 64)

    def test_displayed_image_stays_in_range(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        assert sim.image.min() >= 0.0
        assert sim.image.max() <= 1.0

    def test_the_ideal_image_is_the_requested_target(self):
        sim = simulate_image(create_singlet_system(), target_kind="siemens",
                             with_noise=False)
        assert np.allclose(sim.ideal, test_target("siemens", 128))

    def test_an_explicit_target_overrides_target_kind(self):
        target = test_target("grid", 128, line_width=3)
        sim = simulate_image(create_singlet_system(), target=target,
                             with_noise=False)
        assert np.allclose(sim.ideal, target)

    def test_target_kwargs_reach_the_target_builder(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             target_kwargs={"duty": 0.25}, with_noise=False)
        assert sim.ideal.mean() == pytest.approx(0.25, abs=0.01)

    def test_psf_is_normalised(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        assert sim.psf.sum() == pytest.approx(1.0)
        assert sim.psf.ndim == 2

    def test_metadata_reports_the_system_parameters(self):
        sensor = SensorConfig()
        system = create_singlet_system(sensor=sensor)
        sim = simulate_image(system, target_kind="bars", sensor=sensor,
                             with_noise=False)
        m = sim.metadata
        for key in ("sensor", "f_number", "magnification",
                    "object_pixel_pitch_um", "field_of_view_mm",
                    "image_pixel_pitch_um", "wavelength_m", "field_fraction",
                    "full_field", "with_diffraction", "with_aberration",
                    "with_vignetting", "with_distortion", "with_noise",
                    "psf_fwhm_pixels", "edge_distortion_percent",
                    "min_relative_illumination", "saturated_pixels",
                    "mean_snr", "peak_snr", "peak_electrons"):
            assert key in m, key
        assert m["f_number"] == pytest.approx(effective_f_number(system))
        # simulate_image always evaluates the paraxial model at the analysis
        # wavelength, which can differ slightly from the no-argument call for
        # a dispersive system.
        assert m["magnification"] == pytest.approx(
            magnification(system, system.analysis_settings.wavelength))
        assert m["image_pixel_pitch_um"] == pytest.approx(
            sensor.pixel_pitch * 1e6)
        assert m["psf_fwhm_pixels"] > 0.0
        assert m["sensor"]["resolution"] == sensor.resolution

    def test_switches_are_recorded_in_the_metadata(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False, with_diffraction=False,
                             with_aberration=False, with_vignetting=False)
        assert sim.metadata["with_diffraction"] is False
        assert sim.metadata["with_aberration"] is False
        assert sim.metadata["with_vignetting"] is False

    def test_no_noise_is_reproducible(self):
        a = simulate_image(create_singlet_system(), target_kind="bars",
                           with_noise=False)
        b = simulate_image(create_singlet_system(), target_kind="bars",
                           with_noise=False)
        assert np.array_equal(a.adu, b.adu)

    def test_seed_controls_the_noise(self):
        a = simulate_image(create_singlet_system(), target_kind="bars", seed=11)
        b = simulate_image(create_singlet_system(), target_kind="bars", seed=11)
        c = simulate_image(create_singlet_system(), target_kind="bars", seed=12)
        assert np.array_equal(a.adu, b.adu)
        assert not np.array_equal(a.adu, c.adu)

    def test_noise_is_a_small_perturbation(self):
        clean = simulate_image(create_singlet_system(), target_kind="bars",
                               with_noise=False)
        noisy = simulate_image(create_singlet_system(), target_kind="bars",
                               seed=99)
        assert np.abs(noisy.image - clean.image).max() < 0.1

    def test_ideal_reproduces_the_target_exactly(self):
        system = create_singlet_system()
        sim = simulate_image(system, target_kind="bars", with_noise=False)
        assert np.array_equal(sim.ideal, test_target("bars", 128))

    def test_image_is_the_digitised_electrons(self):
        sensor = SensorConfig()
        sim = simulate_image(create_singlet_system(sensor=sensor),
                             target_kind="bars", sensor=sensor,
                             with_noise=False)
        assert np.allclose(sim.image, sim.adu.astype(float) / sensor.max_adu)

    def test_axis_illumination_is_uniform_and_unity(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             field_fraction=0.0, with_noise=False)
        assert np.allclose(sim.illumination, 1.0)

    def test_single_field_illumination_map_is_flat(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             field_fraction=1.0, with_noise=False)
        assert sim.illumination.max() - sim.illumination.min() == pytest.approx(0.0)

    def test_disabling_vignetting_gives_full_illumination(self):
        sim = simulate_image(create_wide_field_system(), target_kind="bars",
                             full_field=True, with_vignetting=False,
                             with_noise=False)
        assert np.allclose(sim.illumination, 1.0)

    def test_full_field_illumination_falls_towards_the_corner(self):
        sim = simulate_image(create_wide_field_system(), target_kind="bars",
                             full_field=True, with_noise=False)
        n = sim.illumination.shape[0]
        centre = sim.illumination[n // 2, n // 2]
        corner = sim.illumination[0, 0]
        assert corner < centre
        # cos^4 over a 26.6 degree half-field is about 0.64.
        assert 0.5 < corner < 0.8
        assert sim.metadata["min_relative_illumination"] == pytest.approx(
            float(sim.illumination.min()))

    def test_full_field_is_reported_in_the_metadata(self):
        axis = simulate_image(create_singlet_system(), target_kind="bars",
                              with_noise=False)
        full = simulate_image(create_singlet_system(), target_kind="bars",
                              full_field=True, with_noise=False)
        assert axis.metadata["full_field"] is False
        assert full.metadata["full_field"] is True

    def test_full_field_survives_a_negative_magnification(self):
        # The singlet images at m = -1, so the distortion curve reports
        # negative image heights. Interpolating the positive sensor radii
        # against that signed curve used to collapse the whole image onto its
        # centre pixel, flattening the picture to a constant.
        system = create_singlet_system()
        assert magnification(system) < 0.0
        axis = simulate_image(system, target_kind="bars", with_noise=False)
        full = simulate_image(system, target_kind="bars", full_field=True,
                              with_noise=False)
        assert full.image.std() > 0.1
        correlation = np.corrcoef(axis.image.ravel(), full.image.ravel())[0, 1]
        assert correlation > 0.99

    def test_distortion_remap_is_a_no_op_for_an_undistorted_system(self):
        # A singlet with the stop at the lens has negligible distortion, so
        # enabling the remap must barely change the image.
        system = create_singlet_system()
        assert distortion_curve(system)["max_abs_distortion_percent"] < 0.01
        remapped = simulate_image(system, target_kind="bars",
                                  full_field=True, with_noise=False)
        plain = simulate_image(system, target_kind="bars", full_field=True,
                               with_distortion=False, with_noise=False)
        assert np.abs(remapped.image - plain.image).max() < 0.05

    def test_distortion_remap_scales_radius_by_the_distortion_factor(self):
        # Unit-test the radial remap directly with a synthetic curve, so the
        # exact mapping can be checked independently of any real system.
        sensor = SensorConfig(resolution=9, pixel_pitch=1e-3)   # 1 mm pixels
        # real / paraxial = 1.25 at every radius, so the ideal image is
        # sampled at 1 / 1.25 = 0.8 times the output radius.
        curve = {
            "real_image_height_mm": [0.0, 1.0, 2.0, 3.0, 4.0],
            "paraxial_image_height_mm": [0.0, 0.8, 1.6, 2.4, 3.2],
        }
        ideal = np.tile(np.arange(9, dtype=float), (9, 1))
        out = _distort(ideal, sensor, curve)
        assert out[4, 4] == pytest.approx(4.0)      # the axis is fixed
        assert out[4, 8] == pytest.approx(4.0 + 4.0 * 0.8)
        assert out[4, 0] == pytest.approx(4.0 - 4.0 * 0.8)

    def test_signed_image_heights_are_used_as_radii(self):
        # An inverting system reports negative image heights. Interpolating
        # the positive sensor radii against a signed, descending curve clamps
        # every sample to one point, collapsing the image to a constant.
        sensor = SensorConfig(resolution=9, pixel_pitch=1e-3)
        positive = {
            "real_image_height_mm": [0.0, 1.0, 2.0, 3.0, 4.0],
            "paraxial_image_height_mm": [0.0, 0.8, 1.6, 2.4, 3.2],
        }
        negative = {
            "real_image_height_mm": [-v for v in positive["real_image_height_mm"]],
            "paraxial_image_height_mm": [
                -v for v in positive["paraxial_image_height_mm"]],
        }
        ideal = np.tile(np.arange(9, dtype=float), (9, 1))
        out = _distort(ideal, sensor, negative)
        assert np.allclose(out, _distort(ideal, sensor, positive))
        assert out[4, 8] != out[4, 4]        # the row is not flattened

    def test_distortion_remap_returns_the_image_for_a_degenerate_curve(self):
        sensor = SensorConfig(resolution=9, pixel_pitch=1e-3)
        ideal = np.tile(np.arange(9, dtype=float), (9, 1))
        assert np.allclose(_distort(ideal, sensor, {}), ideal)
        assert np.allclose(
            _distort(ideal, sensor, {"real_image_height_mm": [1.0],
                                     "paraxial_image_height_mm": [1.0]}), ideal)
        flat_curve = {"real_image_height_mm": [2.0, 2.0, 2.0],
                      "paraxial_image_height_mm": [1.0, 2.0, 3.0]}
        assert np.allclose(_distort(ideal, sensor, flat_curve), ideal)

    def test_diffraction_and_aberration_can_be_switched_off(self):
        system = create_singlet_system()
        plain = simulate_image(system, target_kind="bars", with_noise=False,
                               with_diffraction=False, with_aberration=False)
        # With both off the PSF reduces to a delta.
        assert plain.psf.max() == pytest.approx(1.0)
        assert plain.psf.sum() == pytest.approx(1.0)

    def test_a_diffraction_limited_system_resolves_more_when_faster(self):
        # Without aberrations only diffraction blurs: a larger aperture
        # (F/2 against F/16 working) resolves the finest bars better.
        slow = simulate_image(create_singlet_system(aperture=0.003125),
                              target_kind="bars", with_noise=False)
        fast = simulate_image(create_singlet_system(aperture=0.025),
                              target_kind="bars", with_noise=False)
        mtf_slow = mtf_from_bar_target(slow.ideal, slow.image)["mtf"]
        mtf_fast = mtf_from_bar_target(fast.ideal, fast.image)["mtf"]
        assert mtf_fast[0] > mtf_slow[0]

    def test_a_flat_target_stays_flat(self):
        sim = simulate_image(create_singlet_system(), target_kind="flat",
                             with_noise=False)
        # A uniform object must survive both the blur and the illumination.
        assert sim.image.max() - sim.image.min() == pytest.approx(0.0, abs=1e-9)

    def test_a_point_target_is_blurred(self):
        # F/80 working: Airy radius ~54 um, about 11 pixels.
        sim = simulate_image(create_singlet_system(aperture=0.00125), target_kind="point",
                             with_noise=False)
        assert np.count_nonzero(sim.image > 0.5 * sim.image.max()) > 1

    def test_a_large_psf_does_not_exhaust_memory(self):
        # A strongly aberrated system produces a PSF hundreds of pixels wide;
        # a direct convolution would need gigabytes for this.
        # 15 mm of defocus at about F/8 gives a blur disk ~1.9 mm across.
        system = create_real_singlet(aperture=0.0125, object_height=0.004, defocus=0.015)
        assert rms_spot_radius(system, 0.0) > 5.0e-4
        sim = simulate_image(system, target_kind="bars", with_noise=False)
        assert sim.image.shape == (128, 128)
        assert np.all(np.isfinite(sim.image))


class TestMtfFromBarTarget:
    """Measuring the achieved MTF from the simulated bar chart."""

    def test_frequency_axis_is_the_inverse_bar_period(self):
        bars = test_target("bars", 128)
        r = mtf_from_bar_target(bars, bars, periods=(4, 8, 16, 32),
                                pixel_pitch=5.0e-6)
        # period (px) * pitch (m) -> mm; frequency = 1 / period_mm.
        assert r["frequency_cyc_per_mm"] == pytest.approx([50.0, 25.0, 12.5, 6.25])

    def test_periods_are_echoed_back(self):
        bars = test_target("bars", 128)
        r = mtf_from_bar_target(bars, bars)
        assert r["periods_pixels"] == [4.0, 8.0, 16.0, 32.0]

    def test_an_image_compared_with_itself_is_perfect(self):
        bars = test_target("bars", 128)
        for value in mtf_from_bar_target(bars, bars)["mtf"]:
            assert value == pytest.approx(1.0, rel=1e-6)

    def test_object_modulation_is_positive(self):
        bars = test_target("bars", 128)
        r = mtf_from_bar_target(bars, bars)
        assert all(v > 0.0 for v in r["object_modulation"])
        assert all(v > 0.0 for v in r["image_modulation"])

    def test_mtf_never_exceeds_unity_for_a_blurred_image(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        for value in mtf_from_bar_target(sim.ideal, sim.image)["mtf"]:
            assert value <= 1.0 + 1e-9

    def test_mtf_falls_as_spatial_frequency_rises(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        r = mtf_from_bar_target(sim.ideal, sim.image)
        # The bands run from the finest bars to the coarsest, so the MTF must
        # rise across the list as the spatial frequency falls.
        assert r["frequency_cyc_per_mm"] == sorted(
            r["frequency_cyc_per_mm"], reverse=True)
        values = r["mtf"]
        assert all(b >= a - 1e-9 for a, b in zip(values, values[1:]))
        assert values[0] < values[-1]

    def test_mtf_ratio_matches_the_modulation_ratio(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        r = mtf_from_bar_target(sim.ideal, sim.image)
        for obj, img, mtf in zip(r["object_modulation"], r["image_modulation"],
                                 r["mtf"]):
            assert mtf == pytest.approx(img / obj)

    def test_a_uniform_image_has_no_measurable_mtf(self):
        bars = test_target("bars", 128)
        flat = np.full((128, 128), 0.5)
        assert all(v == pytest.approx(0.0)
                   for v in mtf_from_bar_target(bars, flat)["mtf"])

    def test_shape_mismatch_is_rejected(self):
        with pytest.raises(ValueError):
            mtf_from_bar_target(test_target("bars", 64),
                                test_target("bars", 128))

    def test_custom_periods_are_honoured(self):
        bars = test_target("bars", 128, periods=(8, 16))
        r = mtf_from_bar_target(bars, bars, periods=(8, 16))
        assert len(r["mtf"]) == 2
        assert r["frequency_cyc_per_mm"] == pytest.approx([25.0, 12.5])

    def test_a_coarser_pitch_lowers_the_reported_frequency(self):
        bars = test_target("bars", 128)
        fine = mtf_from_bar_target(bars, bars, pixel_pitch=5.0e-6)
        coarse = mtf_from_bar_target(bars, bars, pixel_pitch=10.0e-6)
        assert coarse["frequency_cyc_per_mm"][0] == pytest.approx(
            0.5 * fine["frequency_cyc_per_mm"][0])


class TestImageQualityMetrics:
    """Image-versus-object comparison metrics."""

    def test_identical_images_score_perfectly(self):
        bars = test_target("bars", 64)
        q = image_quality_metrics(bars, bars)
        assert q["rmse"] == pytest.approx(0.0)
        assert math.isinf(q["psnr_db"])
        assert q["correlation"] == pytest.approx(1.0)
        assert q["contrast_ideal"] == pytest.approx(q["contrast_simulated"])

    def test_blurred_images_lose_correlation_and_contrast(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        q = image_quality_metrics(sim.ideal, sim.image)
        assert q["rmse"] > 0.0
        assert math.isfinite(q["psnr_db"])
        assert q["correlation"] < 1.0
        # The exposure normalises the brightest pixel, so the displayed image
        # still spans the full range; only the correlation shows the loss.
        assert q["contrast_simulated"] <= q["contrast_ideal"] + 1e-12

    def test_psnr_follows_its_definition(self):
        system = create_singlet_system()
        sim = simulate_image(system, target_kind="bars", with_noise=False)
        q = image_quality_metrics(sim.ideal, sim.image)
        expected = 20.0 * math.log10(1.0 / q["rmse"])
        assert q["psnr_db"] == pytest.approx(expected, rel=1e-6)

    def test_contrast_of_a_binary_target_is_unity(self):
        assert image_quality_metrics(test_target("bars", 64),
                                     test_target("bars", 64))["contrast_ideal"] \
            == pytest.approx(1.0)

    def test_period_argument_adds_a_targeted_measurement(self):
        sim = simulate_image(create_singlet_system(), target_kind="bars",
                             with_noise=False)
        q = image_quality_metrics(sim.ideal, sim.image, period_pixels=16.0)
        for key in ("modulation_ideal", "modulation_simulated", "mtf_measured"):
            assert key in q
        assert q["mtf_measured"] == pytest.approx(
            q["modulation_simulated"] / q["modulation_ideal"])
        assert 0.0 < q["mtf_measured"] <= 1.0

    def test_shape_mismatch_is_rejected(self):
        with pytest.raises(ValueError):
            image_quality_metrics(test_target("bars", 64),
                                  test_target("bars", 128))


class TestDistortion:
    """Radial distortion from real chief-ray traces."""

    def test_keys(self):
        out = distortion_curve(create_singlet_system())
        for key in ("field_fractions", "real_image_height_mm",
                    "paraxial_image_height_mm", "distortion_percent",
                    "edge_distortion_percent", "max_abs_distortion_percent"):
            assert key in out

    def test_field_fractions_run_from_the_axis_to_the_edge(self):
        fractions = distortion_curve(create_singlet_system())["field_fractions"]
        assert fractions[0] == pytest.approx(0.0)
        assert fractions[-1] == pytest.approx(1.0)
        assert fractions == sorted(fractions)

    def test_on_axis_there_is_no_distortion(self):
        out = distortion_curve(create_singlet_system())
        assert out["distortion_percent"][0] == pytest.approx(0.0)
        assert out["real_image_height_mm"][0] == pytest.approx(0.0, abs=1e-9)
        assert out["paraxial_image_height_mm"][0] == pytest.approx(0.0, abs=1e-9)

    def test_image_heights_grow_with_field(self):
        out = distortion_curve(create_singlet_system())
        magnitudes = [abs(h) for h in out["real_image_height_mm"]]
        assert all(b >= a for a, b in zip(magnitudes, magnitudes[1:]))

    def test_an_inverting_system_reports_negative_image_heights(self):
        # m = -1, so the image is inverted and the heights are negative.
        out = distortion_curve(create_singlet_system())
        assert out["real_image_height_mm"][-1] < 0.0

    def test_max_abs_is_the_largest_magnitude(self):
        out = distortion_curve(create_singlet_system())
        assert out["max_abs_distortion_percent"] == pytest.approx(
            max(abs(d) for d in out["distortion_percent"]))

    def test_edge_value_is_the_last_curve_point(self):
        out = distortion_curve(create_singlet_system())
        assert out["edge_distortion_percent"] == pytest.approx(
            out["distortion_percent"][-1])

    def test_the_relay_is_nearly_distortion_free(self):
        out = distortion_curve(create_relay_system())
        assert abs(out["edge_distortion_percent"]) < 1.0

    def test_a_singlet_with_the_stop_at_the_lens_is_essentially_free(self):
        out = distortion_curve(create_singlet_system())
        assert out["max_abs_distortion_percent"] < 0.01

    def test_num_fields_is_respected(self):
        assert len(distortion_curve(create_singlet_system(),
                                    num_fields=5)["distortion_percent"]) == 5

    def test_field_fraction_max_limits_the_range(self):
        out = distortion_curve(create_singlet_system(), num_fields=5,
                               field_fraction_max=0.5)
        assert out["field_fractions"][-1] == pytest.approx(0.5)

    def test_shrinking_the_field_reduces_the_image_height(self):
        small = distortion_curve(create_singlet_system(),
                                 field_fraction_max=0.5)
        large = distortion_curve(create_singlet_system(),
                                 field_fraction_max=1.0)
        assert abs(small["real_image_height_mm"][-1]) < \
            abs(large["real_image_height_mm"][-1])


class TestRelativeIllumination:
    """cos^4 obliquity and vignetting across the field."""

    def test_profile_keys(self):
        prof = relative_illumination_profile(create_singlet_system())
        for key in ("field_fractions", "cos4", "vignetting",
                    "relative_illumination", "edge_relative_illumination"):
            assert key in prof

    def test_profile_is_normalised_on_axis(self):
        for system in (create_singlet_system(), create_wide_field_system()):
            prof = relative_illumination_profile(system)
            assert prof["relative_illumination"][0] == pytest.approx(1.0)
            assert prof["cos4"][0] == pytest.approx(1.0)

    def test_profile_never_exceeds_unity(self):
        prof = relative_illumination_profile(create_wide_field_system())
        assert all(0.0 < v <= 1.0 + 1e-12 for v in prof["relative_illumination"])

    def test_profile_matches_the_exact_disk_irradiance(self):
        # Stop at the ideal lens, image 100 mm behind it: each image point is
        # lit by the uniform 12.5 mm pupil disk (off-axis form factor).
        system = create_wide_field_system()
        prof = relative_illumination_profile(system)
        z, a = 0.100, 0.0125 / 2

        def e(h):
            return (1 - (z * z + h * h - a * a)
                    / math.sqrt((z * z + h * h + a * a) ** 2 - 4 * h * h * a * a))

        for frac, ri in zip(prof["field_fractions"], prof["relative_illumination"]):
            h = system.object.height * frac      # |m| = 1
            assert ri == pytest.approx(e(h) / e(0.0), abs=1e-4)

    def test_a_narrow_field_barely_falls_off(self):
        prof = relative_illumination_profile(create_singlet_system())
        assert prof["relative_illumination"][-1] > 0.99

    def test_a_wide_field_falls_off_by_the_cos4_law(self):
        system = create_wide_field_system()
        prof = relative_illumination_profile(system)
        # With |m| = 1 the chief ray leaves the image plane at the same angle
        # it entered object space, which is atan(h / object distance).
        theta = math.atan(system.object.height / 0.100)
        expected = math.cos(theta) ** 4
        assert expected == pytest.approx(0.64, rel=0.01)
        assert prof["relative_illumination"][-1] == pytest.approx(
            expected, rel=0.02)

    def test_edge_relative_illumination_matches_the_last_point(self):
        prof = relative_illumination_profile(create_wide_field_system())
        assert prof["edge_relative_illumination"] == pytest.approx(
            prof["relative_illumination"][-1])

    def test_edge_loss_is_the_complement_in_percent(self):
        prof = relative_illumination_profile(create_wide_field_system())
        assert prof["edge_loss_percent"] == pytest.approx(
            100.0 * (1.0 - prof["relative_illumination"][-1]), rel=1e-6)

    def test_map_matches_the_sensor_shape(self):
        s = SensorConfig(resolution=64)
        assert relative_illumination_map(create_singlet_system(), s).shape == (64, 64)

    def test_map_is_normalised_at_the_centre(self):
        m = relative_illumination_map(create_wide_field_system(), SensorConfig())
        # The grid is even-sized, so the four centre pixels straddle the axis
        # and sit a fraction of a pixel off it.
        assert m.max() == pytest.approx(1.0, rel=1e-3)
        assert m[63:65, 63:65].mean() == pytest.approx(1.0, rel=1e-3)

    def test_map_falls_towards_the_corner(self):
        m = relative_illumination_map(create_wide_field_system(), SensorConfig())
        assert m[0, 0] < m[64, 64]
        # The sensor half-diagonal is field fraction 1.0 by convention.
        assert m[0, 0] == pytest.approx(0.64, rel=0.05)

    def test_map_is_radially_symmetric(self):
        m = relative_illumination_map(create_wide_field_system(), SensorConfig())
        assert np.allclose(m, m[::-1, :])
        assert np.allclose(m, m[:, ::-1])

    def test_map_never_exceeds_unity(self):
        m = relative_illumination_map(create_wide_field_system(), SensorConfig())
        assert m.min() > 0.0
        assert m.max() <= 1.0 + 1e-12

    def test_without_vignetting_the_map_is_the_cos4_law(self):
        s = SensorConfig()
        system = create_wide_field_system()
        without = relative_illumination_map(system, s, vignetting=False)
        theta = math.atan(system.object.height / 0.100)
        assert without[0, 0] == pytest.approx(math.cos(theta) ** 4, rel=1e-3)

    def test_a_narrow_field_map_is_almost_flat(self):
        m = relative_illumination_map(create_singlet_system(), SensorConfig())
        assert m.min() > 0.99


def decode_png_gray(data):
    """
    Minimal decoder for the 8-bit greyscale PNG that ``encode_png_gray`` writes.

    Only understands the subset the writer produces: colour type 0, bit depth
    8, filter type 0 on every scanline. That is enough to verify the bytes on
    the wire rather than trusting the encoder's own output.
    """
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "missing PNG signature"
    pos, width, height, idat = 8, 0, 0, b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length                       # length + tag + payload + crc
        if tag == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", payload[:10])
            assert depth == 8, f"expected 8-bit, got {depth}"
            assert colour == 0, f"expected greyscale, got type {colour}"
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = width + 1
    rows = []
    for r in range(height):
        line = raw[r * stride:(r + 1) * stride]
        assert line[0] == 0, "expected filter type 0"
        rows.append(np.frombuffer(line[1:], dtype=np.uint8))
    return np.array(rows)


class TestOutputHelpers:
    """PNG encoding, ASCII preview and image statistics."""

    def test_png_signature_and_markers(self):
        png = encode_png_gray(test_target("bars", 32))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert b"IHDR" in png
        assert b"IDAT" in png
        assert b"IEND" in png

    def test_png_round_trips_the_pixels(self):
        image = test_target("bars", 32)
        decoded = decode_png_gray(encode_png_gray(image))
        assert decoded.shape == (32, 32)
        expected = np.round(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
        assert np.array_equal(decoded, expected)

    def test_invert_flips_the_greyscale(self):
        image = test_target("bars", 32)
        plain = decode_png_gray(encode_png_gray(image))
        inverted = decode_png_gray(encode_png_gray(image, invert=True))
        assert np.array_equal(inverted, 255 - plain)

    def test_normalisation_stretches_a_narrow_range(self):
        image = np.linspace(0.4, 0.6, 32 * 32).reshape(32, 32)
        decoded = decode_png_gray(encode_png_gray(image))
        assert decoded.min() == 0
        assert decoded.max() == 255

    def test_normalisation_off_keeps_the_absolute_level(self):
        image = np.full((8, 8), 0.5)
        decoded = decode_png_gray(encode_png_gray(image, normalize=False))
        assert np.all(decoded == 128)

    def test_a_flat_image_encodes_without_division_errors(self):
        decoded = decode_png_gray(encode_png_gray(np.full((8, 8), 0.7)))
        assert decoded.shape == (8, 8)

    def test_a_larger_image_gives_a_larger_file(self):
        small = encode_png_gray(test_target("siemens", 32))
        large = encode_png_gray(test_target("siemens", 256))
        assert len(large) > len(small)

    def test_encode_rejects_a_non_2d_array(self):
        with pytest.raises(ValueError):
            encode_png_gray(np.zeros((4, 4, 3)))

    def test_save_png_writes_a_readable_file(self, tmp_path):
        image = test_target("grid", 32)
        path = tmp_path / "grid.png"
        returned = save_png(str(path), image)
        assert returned == str(path)
        assert path.exists()
        assert decode_png_gray(path.read_bytes()).shape == (32, 32)

    def test_save_png_round_trips_through_disk(self, tmp_path):
        image = test_target("bars", 64)
        path = tmp_path / "bars.png"
        save_png(str(path), image)
        expected = np.round(image * 255.0).astype(np.uint8)
        assert np.array_equal(decode_png_gray(path.read_bytes()), expected)

    def test_ascii_preview_dimensions(self):
        art = ascii_preview(test_target("bars", 128), width=40, height=20)
        lines = art.split("\n")
        assert len(lines) == 20
        assert all(len(line) == 40 for line in lines)

    def test_ascii_preview_default_dimensions(self):
        lines = ascii_preview(test_target("bars", 128)).split("\n")
        assert len(lines) == 28          # half the width, square image
        assert len(lines[0]) == 56

    def test_ascii_preview_uses_the_requested_characters(self):
        art = ascii_preview(test_target("bars", 64), width=16, height=8,
                            chars="#.")
        assert set(art) <= {"#", ".", "\n"}
        assert "#" in art and "." in art

    def test_ascii_preview_renders_a_flat_image_uniformly(self):
        art = ascii_preview(np.full((16, 16), 0.5), width=8, height=4)
        assert len(set(art.replace("\n", ""))) == 1

    def test_ascii_preview_rejects_a_1d_array(self):
        with pytest.raises(ValueError):
            ascii_preview(np.zeros(16))

    def test_ascii_preview_is_not_fooled_by_a_constant_image(self):
        lines = ascii_preview(np.full((32, 32), 3.0), width=8, height=4)
        assert len(lines.split("\n")) == 4

    def test_image_statistics(self):
        image = test_target("bars", 64)
        stats = image_statistics(image)
        assert stats["shape"] == [64, 64]
        assert stats["min"] == pytest.approx(0.0)
        assert stats["max"] == pytest.approx(1.0)
        assert stats["mean"] == pytest.approx(0.5, abs=0.01)
        assert stats["std"] == pytest.approx(0.5, abs=0.01)

    def test_image_statistics_of_a_flat_image(self):
        stats = image_statistics(np.full((8, 8), 0.25))
        assert stats["std"] == pytest.approx(0.0)
        assert stats["mean"] == pytest.approx(0.25)
