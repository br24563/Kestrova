"""
Numerical stability tests.

Tests floating point precision, cancellation errors, and extreme values.
"""

import math
import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.lenses import image_distance, object_distance, system_matrix, thin_lens_matrix, propagation_matrix
from optics.analysis import analyze_system, effective_focal_length
from optics.models import OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings


class TestFloatingPointPrecision:
    """Test floating point precision and consistency."""
    
    def test_image_distance_precision(self):
        """Image distance should be precise to 10+ decimal places."""
        f = 0.1
        s = -0.2
        s_prime = image_distance(f, s)
        # Calculate expected value manually
        expected = f * s / (s + f)
        assert s_prime == pytest.approx(expected, rel=1e-12)
    
    def test_inverse_consistency(self):
        """image_distance and object_distance should be inverses."""
        f = 0.1
        s_original = -0.25
        s_prime = image_distance(f, s_original)
        s_recovered = object_distance(f, s_prime)
        assert s_recovered == pytest.approx(s_original, rel=1e-10)
    
    def test_multiple_calculations_consistent(self):
        """Same calculation should give same result every time."""
        f = 0.1
        s = -0.2
        results = [image_distance(f, s) for _ in range(100)]
        assert all(r == results[0] for r in results)


class TestSmallPerturbations:
    """Test behavior with very small perturbations."""
    
    def test_small_object_distance_change(self):
        """Small change in object distance should produce small change in image distance."""
        f = 0.1
        s1 = -0.2
        s2 = -0.2 + 1e-9  # 1nm change
        
        s_prime1 = image_distance(f, s1)
        s_prime2 = image_distance(f, s2)
        
        # Change should be small and finite
        assert math.isfinite(s_prime2)
        assert abs(s_prime2 - s_prime1) < 1e-6
    
    def test_small_focal_length_change(self):
        """Small change in focal length should produce small change in image distance."""
        f1 = 0.1
        f2 = 0.1 + 1e-9
        s = -0.2
        
        s_prime1 = image_distance(f1, s)
        s_prime2 = image_distance(f2, s)
        
        assert math.isfinite(s_prime2)
        assert abs(s_prime2 - s_prime1) < 1e-6


class TestLargeDynamicRange:
    """Test handling of values spanning many orders of magnitude."""
    
    def test_very_small_focal_length(self):
        """Focal length of 1 micrometer."""
        f = 1e-6
        s = -2e-6  # 2f to avoid exact focal point
        s_prime = image_distance(f, s)
        assert math.isfinite(s_prime)
        assert s_prime > 0
    
    def test_very_large_focal_length(self):
        """Focal length of 1 kilometer."""
        f = 1e3
        s = -1e4
        s_prime = image_distance(f, s)
        assert math.isfinite(s_prime)
        assert s_prime > 0
    
    def test_mixed_scale_system(self):
        """System with components at very different scales."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.001, focal_length=0.001, aperture_diameter=0.0005, material="N-BK7"),
                ThinLens(id="L2", position=1.0, focal_length=1.0, aperture_diameter=0.5, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.0001),
            image_plane=ImagePlane(position=1.5),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        analysis = analyze_system(system)
        # Should complete without error
        assert math.isfinite(analysis.effective_focal_length)


class TestMatrixOperations:
    """Test ABCD matrix operations for numerical stability."""
    
    def test_matrix_multiplication_stability(self):
        """Matrix multiplication should be stable."""
        M1 = thin_lens_matrix(0.1)
        M2 = propagation_matrix(0.05)
        M3 = thin_lens_matrix(0.1)
        
        # Multiply matrices
        M_total = system_matrix([M1, M2, M3])
        
        # Check for NaN or Inf
        assert np.all(np.isfinite(M_total))
    
    def test_identity_matrix(self):
        """System with no elements should give identity matrix."""
        M = system_matrix([])
        assert M[0][0] == pytest.approx(1.0)
        assert M[0][1] == pytest.approx(0.0)
        assert M[1][0] == pytest.approx(0.0)
        assert M[1][1] == pytest.approx(1.0)
    
    def test_inverse_propagation(self):
        """Forward then backward propagation should give identity."""
        d = 0.1
        M_fwd = propagation_matrix(d)
        M_bwd = propagation_matrix(-d)
        
        # Multiply
        M_total = M_bwd @ M_fwd
        
        # Should be close to identity
        assert M_total[0][0] == pytest.approx(1.0, abs=1e-12)
        assert M_total[0][1] == pytest.approx(0.0, abs=1e-12)
        assert M_total[1][0] == pytest.approx(0.0, abs=1e-12)
        assert M_total[1][1] == pytest.approx(1.0, abs=1e-12)


class TestCancellationErrors:
    """Test for catastrophic cancellation."""
    
    def test_near_symmetric_case(self):
        """Object at 2f should give image at 2f (symmetric case)."""
        f = 0.1
        s = -2 * f
        s_prime = image_distance(f, s)
        assert s_prime == pytest.approx(2 * f, rel=1e-12)
    
    def test_near_focal_point(self):
        """Object very close to focal point should give very large image distance."""
        f = 0.1
        epsilon = 1e-6  # Small but not too small
        s = -f - epsilon  # Just outside focal point (beyond f)
        s_prime = image_distance(f, s)
        
        # Should be very large but finite
        assert math.isfinite(s_prime)
        assert s_prime > 1.0  # At least 1 meter away


class TestIterativeConvergence:
    """Test convergence of iterative algorithms."""
    
    def test_analysis_convergence(self):
        """Analysis should converge to stable result."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        # Run analysis multiple times
        results = [analyze_system(system) for _ in range(10)]
        efls = [r.effective_focal_length for r in results]
        
        # All results should be identical
        assert all(e == efls[0] for e in efls)


class TestEdgeCaseInputs:
    """Test edge case inputs that might cause issues."""
    
    def test_zero_thickness(self):
        """Zero thickness should be handled."""
        M = propagation_matrix(0.0)
        assert M[0][1] == pytest.approx(0.0)
    
    def test_negative_thickness(self):
        """Negative thickness (backward propagation) should work."""
        M = propagation_matrix(-0.1)
        assert M[0][1] == pytest.approx(-0.1)
    
    def test_very_large_matrix_chain(self):
        """Chain of many matrices should be stable."""
        matrices = []
        for _ in range(100):
            matrices.append(propagation_matrix(0.001))
            matrices.append(thin_lens_matrix(0.1))
        
        M_total = system_matrix(matrices)
        assert np.all(np.isfinite(M_total))
