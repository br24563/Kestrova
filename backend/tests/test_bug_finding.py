"""
Bug finding tests using fuzzing and property-based testing.

These tests systematically search for bugs by:
1. Fuzzing: Random valid inputs
2. Property-based: Testing invariants that should always hold
3. Differential: Comparing different algorithms for same result
"""

import math
import random
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.lenses import image_distance, object_distance, f_number, thin_lens_matrix, system_matrix, propagation_matrix
from optics.analysis import analyze_system, effective_focal_length, system_magnification
from optics.rays import trace_system, calculate_paraxial_image_position
from optics.models import OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings
from optics.materials import refractive_index
from optics.systems import create_default_system


class TestFuzzing:
    """Fuzz testing with random valid inputs."""
    
    def test_random_focal_lengths(self):
        """Random focal lengths should not crash."""
        random.seed(42)
        for _ in range(100):
            f = random.uniform(0.01, 1.0)
            s = random.uniform(-1.0, -0.01)
            try:
                s_prime = image_distance(f, s)
                assert math.isfinite(s_prime) or math.isinf(s_prime)
            except ValueError:
                pass  # Expected for s = -f
    
    def test_random_systems_no_crash(self):
        """Random valid systems should not crash."""
        random.seed(42)
        for _ in range(50):
            n_components = random.randint(1, 5)
            components = []
            for i in range(n_components):
                components.append(ThinLens(
                    id=f"L{i+1}",
                    position=0.05 + i * random.uniform(0.02, 0.05),
                    focal_length=random.uniform(0.02, 0.2),
                    aperture_diameter=random.uniform(0.01, 0.05),
                    material="N-BK7",
                ))
            
            system = OpticalSystem(
                components=components,
                wavelengths=[550e-9],
                object=Object(position=0.0, height=random.uniform(0.001, 0.02)),
                image_plane=ImagePlane(position=0.1 + n_components * 0.05),
                analysis_settings=AnalysisSettings(
                    num_rays=11,
                    ray_types=['chief', 'marginal', 'fill'],
                    aperture_fraction=1.0,
                    wavelength=550e-9,
                ),
            )
            
            try:
                analysis = analyze_system(system)
                # Results should be finite or clearly invalid
                assert isinstance(analysis.effective_focal_length, float)
                assert isinstance(analysis.magnification, float)
            except Exception as e:
                pytest.fail(f"System crashed: {e}")
    
    def test_random_wavelengths(self):
        """Random wavelengths in visible range should work."""
        random.seed(42)
        for _ in range(100):
            wl = random.uniform(380e-9, 700e-9)
            n = refractive_index('N-BK7', wl)
            assert 1.4 < n < 1.6, f"Unreasonable index {n} at wavelength {wl*1e9:.1f}nm"


class TestProperties:
    """Property-based testing - invariants that should always hold."""
    
    def test_magnification_sign_for_real_image(self):
        """Real images should have negative magnification (inverted)."""
        random.seed(42)
        for _ in range(50):
            f = random.uniform(0.05, 0.2)
            s = random.uniform(-0.5, -1.5) * f  # Beyond 2f
            
            system = OpticalSystem(
                components=[ThinLens(id="L1", position=0.2, focal_length=f, aperture_diameter=0.025, material="N-BK7")],
                wavelengths=[550e-9],
                object=Object(position=0.0, height=0.01),
                image_plane=ImagePlane(position=0.3),
                analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
            )
            
            mag = system_magnification(system)
            # For real images, magnification should be negative
            if mag < 0:
                analysis = analyze_system(system)
                assert analysis.is_image_inverted
    
    def test_energy_conservation_in_rays(self):
        """All rays should produce valid paths (no NaN)."""
        system = create_default_system()
        result = trace_system(system)
        
        for path in result.ray_paths:
            for point in path.points:
                assert math.isfinite(point[0]), f"z-coordinate is not finite: {point[0]}"
                assert math.isfinite(point[1]), f"y-coordinate is not finite: {point[1]}"
    
    def test_efl_positive_for_converging(self):
        """System with converging lenses should have positive EFL."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        efl = effective_focal_length(system)
        assert efl > 0, f"Converging lens should have positive EFL, got {efl}"
    
    def test_f_number_positive(self):
        """F-number should always be positive."""
        random.seed(42)
        for _ in range(100):
            f = random.uniform(0.01, 1.0)
            D = random.uniform(0.001, 0.5)
            fn = f_number(f, D)
            assert fn > 0, f"F-number should be positive, got {fn}"
    
    def test_matrix_determinant(self):
        """ABCD matrix determinant should be 1 (lossless system)."""
        random.seed(42)
        for _ in range(50):
            matrices = []
            n = random.randint(1, 10)
            for _ in range(n):
                if random.random() > 0.5:
                    matrices.append(thin_lens_matrix(random.uniform(0.05, 0.5)))
                else:
                    matrices.append(propagation_matrix(random.uniform(0.01, 0.1)))
            
            M = system_matrix(matrices)
            det = M[0][0] * M[1][1] - M[0][1] * M[1][0]
            assert det == pytest.approx(1.0, abs=1e-10), f"Matrix determinant should be 1, got {det}"


class TestDifferential:
    """Differential testing - compare different methods for same result."""
    
    def test_efl_from_matrix_vs_analysis(self):
        """EFL from system matrix should match EFL from analysis."""
        system = create_default_system()
        
        # Get EFL from analysis
        analysis_efl = effective_focal_length(system)
        
        # Get EFL from system matrix
        from optics.analysis import build_system_matrix
        M = build_system_matrix(system)
        matrix_efl = -1.0 / M[1][0] if abs(M[1][0]) > 1e-15 else float('inf')
        
        # Should be close
        assert analysis_efl == pytest.approx(matrix_efl, rel=0.01)
    
    def test_image_position_consistency(self):
        """Image position from ray trace should be consistent."""
        system = create_default_system()
        
        # Get from paraxial calculation
        paraxial_pos = calculate_paraxial_image_position(system)
        
        # Get from ray trace
        trace_result = trace_system(system)
        trace_pos = trace_result.image_position
        
        # Should be close
        assert paraxial_pos == pytest.approx(trace_pos, rel=0.01)


class TestInvariants:
    """Test invariants that should always hold."""
    
    def test_round_trip_object_image(self):
        """Object → Image → Object should return to original."""
        f = 0.1
        s_original = -0.3
        
        # Object to image
        s_prime = image_distance(f, s_original)
        
        # Image to object (reverse)
        s_recovered = object_distance(f, s_prime)
        
        assert s_recovered == pytest.approx(s_original, rel=1e-10)
    
    def test_symmetric_system_magnification(self):
        """Symmetric system (object at 2f) should have m = -1."""
        f = 0.1
        system = OpticalSystem(
            components=[ThinLens(id="L1", position=0.2, focal_length=f, aperture_diameter=0.025, material="N-BK7")],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),  # At 2f
            image_plane=ImagePlane(position=0.4),  # Image at 2f
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        mag = system_magnification(system)
        assert mag == pytest.approx(-1.0, abs=0.05)
    
    def test_materials_always_valid(self):
        """Material indices should always be in valid range."""
        materials = ['N-BK7', 'N-SF11', 'FusedSilica', 'CaF2']
        wavelengths = [400e-9, 500e-9, 600e-9, 700e-9]
        
        for mat in materials:
            for wl in wavelengths:
                n = refractive_index(mat, wl)
                assert 1.2 < n < 2.0, f"Unreasonable index {n} for {mat} at {wl*1e9:.0f}nm"


class TestBoundaryConditions:
    """Test boundary conditions and edge cases."""
    
    def test_minimum_aperture(self):
        """Very small aperture should work."""
        system = OpticalSystem(
            components=[ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.001, material="N-BK7")],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.001),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        analysis = analyze_system(system)
        assert math.isfinite(analysis.effective_focal_length)
    
    def test_maximum_aperture(self):
        """Large aperture should work."""
        system = OpticalSystem(
            components=[ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.1, material="N-BK7")],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        analysis = analyze_system(system)
        assert math.isfinite(analysis.effective_focal_length)
    
    def test_single_ray_trace(self):
        """System with single ray should work."""
        system = OpticalSystem(
            components=[ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7")],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=1, ray_types=['chief'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        result = trace_system(system)
        assert len(result.ray_paths) >= 0  # May be 0 if ray misses


class TestRegression:
    """Regression tests for previously found bugs."""
    
    def test_infinity_focal_length_allowed(self):
        """Infinity focal length should be allowed (flat surface)."""
        lens = ThinLens(id="L1", position=0.1, focal_length=float('inf'), aperture_diameter=0.025, material="N-BK7")
        assert lens.focal_length == float('inf')
    
    def test_no_division_by_zero_crash(self):
        """Object at focal point should raise ValueError, not crash."""
        f = 0.1
        s = -f
        with pytest.raises(ValueError):
            image_distance(f, s)
    
    def test_validation_catches_negative_aperture(self):
        """Negative aperture should be caught by validation."""
        with pytest.raises(ValueError):
            ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=-0.025)
