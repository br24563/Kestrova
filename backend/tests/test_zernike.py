"""
Tests for Zernike polynomial analysis.
"""

import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.zernike import (
    zernike_standard, zernike_fringe, zernike_fit, zernike_evaluate,
    wavefront_to_zernike, zernike_coeffs
)


class TestZernikePolynomials:
    """Tests for Zernike polynomial calculations."""
    
    def test_piston(self):
        """Piston should be constant."""
        rho = np.linspace(0, 1, 10)
        theta = np.zeros(10)
        Z = zernike_standard(1, rho, theta)
        assert np.allclose(Z, 1.0)
    
    def test_tilt(self):
        """Tilt should vary linearly."""
        rho = np.array([0, 0.5, 1.0])
        theta = np.zeros(3)
        Z = zernike_standard(2, rho, theta)  # X tilt (Noll j=2)
        assert Z[2] > Z[0]  # Increases with rho
    
    def test_focus(self):
        """Focus should be quadratic."""
        rho = np.linspace(0, 1, 10)
        theta = np.zeros(10)
        Z = zernike_standard(4, rho, theta)  # Focus
        # Should be minimum at center
        assert Z[0] < Z[-1]


class TestZernikeFit:
    """Tests for Zernike fitting."""
    
    def test_fit_piston(self):
        """Fit constant wavefront."""
        x = np.linspace(-1, 1, 50)
        X, Y = np.meshgrid(x, x)
        wavefront = np.ones_like(X) * 0.5  # Constant
        
        coeffs = zernike_fit(wavefront, X, Y, num_terms=6)
        # First coefficient (piston) should be ~0.5
        assert coeffs[0] == pytest.approx(0.5, abs=0.1)
    
    def test_fit_focus(self):
        """Fit quadratic wavefront."""
        x = np.linspace(-1, 1, 50)
        X, Y = np.meshgrid(x, x)
        R = np.sqrt(X**2 + Y**2)
        R[R > 1] = 0
        wavefront = R**2  # Quadratic
        
        coeffs = zernike_fit(wavefront, X, Y, num_terms=10)
        # Should have significant focus term
        assert abs(coeffs[3]) > 0.01  # Focus coefficient


class TestWavefrontAnalysis:
    """Tests for wavefront analysis."""
    
    def test_wavefront_to_zernike(self):
        """Convert wavefront to Zernike coefficients."""
        x = np.linspace(-1, 1, 32)
        X, Y = np.meshgrid(x, x)
        R = np.sqrt(X**2 + Y**2)
        mask = R <= 1
        wavefront = np.zeros_like(X)
        wavefront[mask] = R[mask]**2
        
        analysis = wavefront_to_zernike(wavefront, X, Y, num_terms=10)
        assert 'coefficients' in analysis
        assert 'rms_wavefront' in analysis
        assert analysis['rms_wavefront'] > 0
    
    def test_zernike_coeffs_list(self):
        """Get list of Zernike coefficients."""
        coeffs = zernike_coeffs(10)
        assert len(coeffs) == 10
        assert coeffs[0]['name'] == 'Piston'
