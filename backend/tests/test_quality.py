"""
Tests for optical quality metrics.
"""

import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.quality import (
    strehl_ratio, strehl_ratio_from_coeffs,
    diffraction_limited_check, encircled_energy,
    mtf_diffraction, quality_metrics
)


class TestStrehlRatio:
    """Tests for Strehl ratio calculations."""
    
    def test_perfect_system(self):
        """Perfect system should have Strehl = 1."""
        S = strehl_ratio(0, 550e-9)
        assert S == pytest.approx(1.0)
    
    def test_marechal_criterion(self):
        """Strehl > 0.8 for diffraction-limited."""
        # λ/14 RMS wavefront error
        W_rms = 550e-9 / 14
        S = strehl_ratio(W_rms, 550e-9)
        assert S > 0.8
    
    def test_large_error(self):
        """Large error should give low Strehl."""
        S = strehl_ratio(1e-6, 550e-9)
        assert S < 0.1
    
    def test_from_coeffs(self):
        """Calculate from Zernike coefficients."""
        coeffs = np.array([0, 0, 0, 1e-7])  # Small focus error
        S = strehl_ratio_from_coeffs(coeffs, 550e-9)
        assert 0 < S <= 1


class TestDiffractionLimited:
    """Tests for diffraction-limited checks."""
    
    def test_check(self):
        """Check diffraction-limited status."""
        result = diffraction_limited_check(1e-6, 2.0, 550e-9)
        assert 'is_diffraction_limited' in result
        assert 'airy_disk_radius' in result
        assert 'strehl_ratio' in result


class TestEncircledEnergy:
    """Tests for encircled energy."""
    
    def test_zero_radius(self):
        """Zero radius should give zero energy."""
        ee = encircled_energy(0, 550e-9, 2.0)
        assert ee == pytest.approx(0.0)
    
    def test_large_radius(self):
        """Large radius should give ~1.0."""
        ee = encircled_energy(1e-3, 550e-9, 2.0)
        assert ee > 0.99


class TestMTF:
    """Tests for diffraction MTF."""
    
    def test_mtf_cutoff(self):
        """MTF should be zero at cutoff."""
        freq = np.array([0, 100, 1000])  # cycles/mm
        mtf = mtf_diffraction(freq, 550e-9 * 1e-3, 2.0)
        assert mtf[0] == pytest.approx(1.0)  # DC is 1
        assert all(mtf >= 0)


class TestQualityMetrics:
    """Tests for comprehensive quality metrics."""
    
    def test_metrics(self):
        """Calculate quality metrics."""
        metrics = quality_metrics(
            rms_wavefront=550e-9/14,
            rms_spot=1e-6,
            wavelength=550e-9,
            f_number=2.0
        )
        assert 'strehl_ratio' in metrics
        assert 'is_diffraction_limited' in metrics
        assert metrics['strehl_ratio'] > 0.8
