"""
Tests for the diffraction analysis module.

These tests verify the Fraunhofer diffraction metrics (Airy disk, PSF,
encircled energy, MTF, OTF) produce correct values for known cases.
"""

import math

import numpy as np
import pytest
from optics.models import (
    OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings,
)
from optics.diffraction import (
    airy_disk_radius, psf, encircled_energy, mtf, otf,
    diffraction_limited_check, diffraction_analysis,
)


def make_single_lens_system(
    f: float = 0.050,
    aperture: float = 0.025,
) -> OpticalSystem:
    """Create a single thin-lens system (F/2 at 550 nm)."""
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1", position=0.100, focal_length=f,
                aperture_diameter=aperture, material="N-BK7",
            ),
        ],
        object=Object(position=0.0, height=0.010),
        image_plane=ImagePlane(position=0.200),
        analysis_settings=AnalysisSettings(num_rays=11),
    )


class TestAiryDisk:
    """Tests for the Airy disk radius."""

    def test_explicit_f_number(self):
        """r = 1.22 * lambda * F for explicit F-number."""
        # F = 2, lambda = 550 nm => r = 1.22 * 550e-9 * 2
        r = airy_disk_radius(na=None, f_number=2.0, wavelength=550e-9)
        assert r == pytest.approx(1.22 * 550e-9 * 2.0, rel=1e-12)

    def test_explicit_na(self):
        """r = 0.61 * lambda / NA."""
        r = airy_disk_radius(na=0.5, wavelength=550e-9)
        assert r == pytest.approx(0.61 * 550e-9 / 0.5, rel=1e-12)

    def test_system_uses_analysis(self):
        """System-based radius is finite and positive."""
        system = make_single_lens_system()
        r = airy_disk_radius(system)
        assert r > 0
        assert np.isfinite(r)


class TestPSF:
    """Tests for the point spread function."""

    def test_peak_normalized(self):
        """The PSF should be normalized to 1 at r=0."""
        system = make_single_lens_system()
        data = psf(system, num_points=16)
        assert data["intensity"][0] == pytest.approx(1.0)

    def test_first_zero_at_airy(self):
        """The PSF should reach its first zero at the Airy radius."""
        system = make_single_lens_system()
        airy = airy_disk_radius(system)
        data = psf(system, num_points=128)
        # Find the minimum near r = airy
        idx = int(np.argmin(np.abs(data["r"] - airy)))
        assert data["intensity"][idx] < 0.01


class TestEncircledEnergy:
    """Encircled energy tests."""

    def test_energy_at_airy_is_838(self):
        """The classic result: ~83.8% within the first Airy ring."""
        system = make_single_lens_system()
        airy = airy_disk_radius(system)
        res = encircled_energy(system, radius=airy)
        assert res["energy"][0] == pytest.approx(0.838, abs=0.01)

    def test_energy_monotonic_up_to_one(self):
        """Encircled energy should increase and approach 1."""
        system = make_single_lens_system()
        data = encircled_energy(system, num_points=64)
        energies = data["energy"]
        assert energies[0] >= 0
        assert energies[-1] > 0.9
        assert all(energies[i] <= energies[i + 1] for i in range(len(energies) - 1))


class TestMTF:
    """Modulation transfer function tests."""

    def test_mtf_at_zero_is_one(self):
        """MTF at zero spatial frequency is 1."""
        system = make_single_lens_system()
        data = mtf(system)
        assert data["mtf"][0] == pytest.approx(1.0)

    def test_mtf_at_cutoff_is_zero(self):
        """MTF at the cutoff frequency is 0."""
        system = make_single_lens_system()
        data = mtf(system)
        # Last sample is at (or just below) cutoff
        assert data["mtf"][-1] < 1e-6

    def test_mtf_bounded_by_one(self):
        """MTF should never exceed 1."""
        system = make_single_lens_system()
        data = mtf(system)
        assert np.all(data["mtf"] >= 0.0)
        assert np.all(data["mtf"] <= 1.0)


class TestOTF:
    """Optical transfer function tests."""

    def test_otf_real_for_aberration_free(self):
        """For a diffraction-limited system the OTF is real (imag ~ 0)."""
        system = make_single_lens_system()
        data = otf(system)
        assert np.all(np.abs(data["otf"].imag) < 1e-12)
        assert np.allclose(data["otf"].real, data["mtf"])

    def test_otf_matches_mtf_modulus(self):
        """|OTF| equals the MTF."""
        system = make_single_lens_system()
        data = otf(system)
        assert np.allclose(np.abs(data["otf"]), data["mtf"])


class TestDiffractionLimited:
    """Diffraction-limited assessment tests."""

    def test_check_returns_keys(self):
        """diffraction_limited_check returns the expected keys."""
        system = make_single_lens_system()
        chk = diffraction_limited_check(system)
        assert "airy_disk_radius" in chk
        assert "rms_spot_radius" in chk
        assert "is_diffraction_limited" in chk
        assert "margin" in chk


class TestFullAnalysis:
    def test_full_analysis_keys(self):
        """diffraction_analysis returns all sub-analyses."""
        system = make_single_lens_system()
        full = diffraction_analysis(system, num_points=8)
        assert "psf" in full
        assert "encircled_energy" in full
        assert "mtf" in full
        assert "strehl_ratio" in full
        assert "airy_disk_radius" in full
        assert "diffraction_limited" in full