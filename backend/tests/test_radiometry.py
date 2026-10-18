"""
Tests for radiometry, photometry, and BRDF models (roadmap item 11).

Validates the photopic luminosity function against CIE values, the
radiometric identities (inverse-square, cos^4, etendue), Planck and
Stefan-Boltzmann laws, and the Harvey-Shack/scalar BRDF models.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from optics.radiometry import (
    MAX_LUMINOUS_EFFICACY,
    photopic_luminosity, luminous_efficacy, radiant_to_luminous,
    luminous_to_radiant, photon_energy, photon_flux,
    solid_angle_cone, solid_angle_from_f_number,
    f_number_from_numerical_aperture, numerical_aperture_from_f_number,
    etendue, etendue_from_f_number, irradiance_from_flux,
    illuminance_from_flux, radiance_from_irradiance,
    image_irradiance_from_object, relative_illumination_cos4,
    wien_peak_wavelength, planck_spectral_radiance, planck_spectral_exitance,
    stefan_boltzmann_exitance, band_integrated_radiance,
    band_integrated_flux, blackbody_luminous_efficacy,
    BRDFParameters, brdf_lambertian, brdf_abg, brdf_value,
    total_integrated_scatter, BRDF_DATABASE, get_brdf, list_brdf_names,
)


class TestPhotopicLuminosity:
    """CIE 1931 photopic V(lambda) from the Wyman multi-lobe fit."""

    def test_peak_is_at_555_nm(self):
        values = [(wl, photopic_luminosity(wl)) for wl in range(500, 620, 5)]
        peak_wl, peak_v = max(values, key=lambda pair: pair[1])
        assert 550 <= peak_wl <= 565
        assert peak_v == pytest.approx(1.0, abs=0.01)

    @pytest.mark.parametrize("wavelength,expected", [
        (450, 0.038), (510, 0.503), (555, 1.000), (600, 0.631), (650, 0.107),
    ])
    def test_matches_cie_table(self, wavelength, expected):
        assert photopic_luminosity(wavelength) == pytest.approx(expected, abs=0.01)

    def test_bounded(self):
        for wl in range(300, 900, 7):
            assert 0.0 <= photopic_luminosity(wl) <= 1.0

    def test_far_ultraviolet_is_near_zero(self):
        assert photopic_luminosity(300.0) < 1e-3

    def test_far_infrared_is_near_zero(self):
        assert photopic_luminosity(900.0) < 1e-3


class TestLuminousEfficacy:
    """Conversion between watts and lumens."""

    def test_maximum_is_683(self):
        assert MAX_LUMINOUS_EFFICACY == pytest.approx(683.0)
        assert luminous_efficacy(555e-9) == pytest.approx(683.0, rel=0.01)

    def test_monochromatic_round_trip(self):
        watts = 0.001
        lumens = radiant_to_luminous(watts, 555e-9)
        assert luminous_to_radiant(lumens, 555e-9) == pytest.approx(watts, rel=1e-9)

    def test_green_is_brighter_than_red(self):
        assert luminous_efficacy(555e-9) > luminous_efficacy(650e-9)

    def test_out_of_band_emits_no_light(self):
        assert luminous_efficacy(300e-9) == pytest.approx(0.0, abs=1e-9)
        assert luminous_to_radiant(100.0, 300e-9) == pytest.approx(0.0)


class TestPhotons:
    """Photon energy and flux."""

    def test_photon_energy_is_positive(self):
        assert photon_energy(550e-9) > 0.0

    def test_shorter_wavelength_carries_more_energy(self):
        assert photon_energy(400e-9) > photon_energy(700e-9)

    def test_energy_times_flux_returns_power(self):
        watts = 1e-3
        count = photon_flux(watts, 550e-9)
        assert count * photon_energy(550e-9) == pytest.approx(watts, rel=1e-9)

    def test_zero_wavelength_is_safe(self):
        assert photon_energy(0.0) == 0.0
        assert photon_flux(1.0, 0.0) == 0.0


class TestSolidAngle:
    """Cone and f-number solid angles."""

    def test_half_space_is_two_pi(self):
        assert solid_angle_cone(math.pi / 2) == pytest.approx(2.0 * math.pi)

    def test_zero_angle_is_zero(self):
        assert solid_angle_cone(0.0) == pytest.approx(0.0)

    def test_monotonic_in_angle(self):
        values = [solid_angle_cone(a) for a in (0.1, 0.3, 0.6, 1.0)]
        assert all(b > a for a, b in zip(values, values[1:]))

    def test_f_number_cone_is_positive_and_bounded(self):
        omega = solid_angle_from_f_number(2.0)
        assert 0.0 < omega < 2.0 * math.pi

    def test_faster_lens_collects_more_solid_angle(self):
        assert solid_angle_from_f_number(1.4) > solid_angle_from_f_number(8.0)

    def test_invalid_f_number_is_safe(self):
        assert solid_angle_from_f_number(0.0) == 0.0
        assert solid_angle_from_f_number(-2.0) == 0.0

    def test_f_number_to_na_round_trip(self):
        fno = 2.8
        assert f_number_from_numerical_aperture(
            numerical_aperture_from_f_number(fno)) == pytest.approx(fno, rel=1e-9)

    def test_na_relation_at_f2(self):
        assert numerical_aperture_from_f_number(2.0) == pytest.approx(0.25)

    def test_invalid_na_is_infinite(self):
        assert math.isinf(f_number_from_numerical_aperture(0.0))


class TestRadiometricIdentities:
    """Etendue, irradiance, and the camera equation."""

    def test_etendue_is_area_times_solid_angle(self):
        assert etendue(1e-4, 0.5) == pytest.approx(5e-5)

    def test_etendue_from_f_number_uses_projected_solid_angle(self):
        # G = A * pi sin^2 U with sin U = 1 / (2N); the plain solid angle
        # 2 pi (1 - cos U) is only its small-angle limit.
        assert etendue_from_f_number(1e-4, 2.0) == pytest.approx(
            1e-4 * math.pi * (1.0 / (2.0 * 2.0)) ** 2)
        assert etendue_from_f_number(1e-4, 2.0) < 1e-4 * solid_angle_from_f_number(2.0)

    def test_irradiance_is_flux_over_area(self):
        assert irradiance_from_flux(1.0, 1e-4) == pytest.approx(1e4)

    def test_zero_area_is_safe(self):
        assert irradiance_from_flux(1.0, 0.0) == 0.0
        assert illuminance_from_flux(1.0, 0.0) == 0.0

    def test_illuminance_is_lumens_over_area(self):
        assert illuminance_from_flux(100.0, 1.0) == pytest.approx(100.0)

    def test_radiance_from_irradiance(self):
        assert radiance_from_irradiance(2.0, 0.5) == pytest.approx(4.0)

    def test_inverse_square_law_in_f_number(self):
        # Image irradiance falls as 1/N^2: two stops needs four times less.
        fast = image_irradiance_from_object(1.0, 2.0)
        slow = image_irradiance_from_object(1.0, 4.0)
        assert fast == pytest.approx(4.0 * slow)

    def test_camera_equation_value(self):
        assert image_irradiance_from_object(1.0, 2.0) == pytest.approx(
            math.pi / 16.0, rel=1e-9)

    def test_transmission_scales_irradiance(self):
        full = image_irradiance_from_object(1.0, 2.0, transmission=1.0)
        half = image_irradiance_from_object(1.0, 2.0, transmission=0.5)
        assert half == pytest.approx(0.5 * full)

    def test_invalid_f_number_gives_zero(self):
        assert image_irradiance_from_object(1.0, 0.0) == 0.0

    def test_cos4_helper(self):
        assert relative_illumination_cos4(math.radians(30)) == pytest.approx(0.5625, rel=1e-9)


class TestBlackbody:
    """Planck, Wien, and Stefan-Boltzmann."""

    def test_wien_peak_of_the_sun(self):
        assert wien_peak_wavelength(5800.0) * 1e9 == pytest.approx(500.0, abs=5.0)

    def test_wien_peak_shifts_blue_when_hot(self):
        assert wien_peak_wavelength(6000.0) < wien_peak_wavelength(3000.0)

    def test_planck_is_positive(self):
        assert planck_spectral_radiance(5800.0, 550e-9) > 0.0

    def test_planck_peaks_near_wien_wavelength(self):
        temperature = 5800.0
        peak = wien_peak_wavelength(temperature)
        samples = [(wl, planck_spectral_radiance(temperature, wl * 1e-9))
                   for wl in range(100, 2000, 10)]
        best_wl, _ = max(samples, key=lambda pair: pair[1])
        assert abs(best_wl - peak * 1e9) < 30.0

    def test_planck_increases_with_temperature(self):
        cold = planck_spectral_radiance(3000.0, 550e-9)
        hot = planck_spectral_radiance(6000.0, 550e-9)
        assert hot > cold

    def test_planck_handles_extreme_arguments(self):
        # Must not overflow for a cold body at a short wavelength.
        assert planck_spectral_radiance(100.0, 100e-9) == 0.0
        assert planck_spectral_radiance(0.0, 550e-9) == 0.0
        assert planck_spectral_radiance(5800.0, 0.0) == 0.0

    def test_exitance_is_pi_times_radiance(self):
        assert planck_spectral_exitance(5800.0, 550e-9) == pytest.approx(
            math.pi * planck_spectral_radiance(5800.0, 550e-9))

    def test_stefan_boltzmann_scaling(self):
        # Doubling T multiplies total exitance by 16.
        assert stefan_boltzmann_exitance(6000.0) == pytest.approx(
            16.0 * stefan_boltzmann_exitance(3000.0), rel=1e-9)

    def test_stefan_boltzmann_value(self):
        assert stefan_boltzmann_exitance(5800.0) / 1e6 == pytest.approx(64.2, rel=0.01)

    def test_band_integration_is_positive_and_bounded(self):
        total = stefan_boltzmann_exitance(5800.0) / math.pi
        band = band_integrated_radiance(5800.0, 0.0, 100e-6, num_samples=400)
        assert 0.0 < band < total

    def test_visible_band_is_a_fraction_of_the_total(self):
        visible = band_integrated_radiance(5800.0, 400e-9, 700e-9)
        everything = band_integrated_radiance(5800.0, 1e-9, 100e-6, num_samples=400)
        assert 0.0 < visible < everything

    def test_band_flux_scales_with_area_and_solid_angle(self):
        one = band_integrated_flux(5800.0, 400e-9, 700e-9, 1e-4, 1e-2)
        two = band_integrated_flux(5800.0, 400e-9, 700e-9, 2e-4, 1e-2)
        assert two == pytest.approx(2.0 * one, rel=1e-9)

    def test_solar_efficacy_is_realistic(self):
        efficacy = blackbody_luminous_efficacy(5800.0)
        assert 80.0 < efficacy < 110.0

    def test_efficacy_rises_with_temperature(self):
        assert blackbody_luminous_efficacy(3000.0) < blackbody_luminous_efficacy(5800.0)

    def test_zero_temperature_is_safe(self):
        assert blackbody_luminous_efficacy(0.0) == 0.0

class TestBRDFModels:
    """Lambertian and Harvey-Shack (ABg) BRDF models."""

    def test_lambertian_brdf_is_rho_over_pi(self):
        assert brdf_lambertian(0.5) == pytest.approx(0.5 / math.pi)
        assert brdf_lambertian(1.0) == pytest.approx(1.0 / math.pi)

    def test_lambertian_brdf_is_never_negative(self):
        assert brdf_lambertian(-0.5) == 0.0

    def test_abg_formula(self):
        params = BRDFParameters(model="abg", A=1e-4, B=1e-3, g=2.0)
        beta = 1e-3
        assert brdf_abg(params, beta) == pytest.approx(1e-4 / (1e-3 + 1e-6))

    def test_abg_falls_with_scatter_angle(self):
        params = BRDFParameters(model="abg", A=1e-4, B=1e-3, g=2.0)
        assert brdf_abg(params, 1e-3) > brdf_abg(params, 1e-1)

    def test_abg_zero_at_zero_angle_is_bounded(self):
        params = BRDFParameters(model="abg", A=1e-4, B=1e-3, g=2.0)
        assert brdf_abg(params, 0.0) == pytest.approx(1e-4 / 1e-3)

    def test_abg_with_zero_shoulder_is_safe(self):
        params = BRDFParameters(model="abg", A=1e-4, B=0.0, g=2.0)
        assert brdf_abg(params, 0.0) == 0.0

    def test_brdf_value_dispatches_on_model(self):
        lam = BRDFParameters(model="lambertian", diffuse_fraction=0.4)
        abg = BRDFParameters(model="abg", A=1e-4, B=1e-3, g=2.0)
        assert brdf_value(lam) == pytest.approx(brdf_lambertian(0.4))
        assert brdf_value(abg, 1e-2) == pytest.approx(brdf_abg(abg, 1e-2))

    def test_brdf_value_accepts_alias_names(self):
        for name in ("abg", "ABG", "harvey-shack", "HarveyShack"):
            params = BRDFParameters(model=name, A=1e-4, B=1e-3, g=2.0)
            assert brdf_value(params, 1e-2) == pytest.approx(brdf_abg(params, 1e-2))

    def test_tis_is_a_fraction(self):
        for name in list_brdf_names():
            tis = total_integrated_scatter(get_brdf(name))
            assert 0.0 <= tis < 1.0

    def test_polished_surfaces_scatter_less_than_rough_ones(self):
        polished = total_integrated_scatter(get_brdf("superpolished_glass"))
        rough = total_integrated_scatter(get_brdf("fine_ground_glass"))
        assert polished < rough

    def test_tis_of_a_polish_is_small(self):
        assert total_integrated_scatter(get_brdf("polished_glass")) < 0.05

    def test_tis_handles_degenerate_arguments(self):
        params = get_brdf("polished_glass")
        assert total_integrated_scatter(params, beta_max=0.0) == 0.0
        assert total_integrated_scatter(params, num_samples=1) == 0.0


class TestBRDFDatabase:
    """Reference surface-finish library."""

    def test_database_is_populated(self):
        assert len(BRDF_DATABASE) >= 8

    def test_expected_entries_present(self):
        for name in ("polished_glass", "superpolished_glass", "fine_ground_glass",
                     "black_anodized_aluminum", "spectralon", "black_felt"):
            assert name in BRDF_DATABASE

    def test_names_are_sorted(self):
        names = list_brdf_names()
        assert names == sorted(names)

    def test_lookup_is_case_and_separator_insensitive(self):
        for key in ("Polished Glass", "polished-glass", "POLISHED_GLASS"):
            assert get_brdf(key) is not None

    def test_unknown_lookup_returns_none(self):
        assert get_brdf("unobtainium") is None
        assert get_brdf("") is None

    def test_every_entry_is_usable(self):
        for name in list_brdf_names():
            params = get_brdf(name)
            value = brdf_value(params, 1e-2)
            assert value >= 0.0
            assert math.isfinite(value)

    def test_entries_document_their_source(self):
        for name in list_brdf_names():
            assert get_brdf(name).source
