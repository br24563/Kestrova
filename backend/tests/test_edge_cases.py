"""
Edge case and boundary condition tests.

Tests extreme inputs and boundary conditions to ensure robustness.
"""

import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.lenses import image_distance, object_distance, f_number, numerical_aperture
from optics.rays import calculate_paraxial_image_position, calculate_paraxial_image_height
from optics.analysis import analyze_system, effective_focal_length
from optics.models import OpticalSystem, ThinLens, ThickLens, ApertureStop, Object, ImagePlane, AnalysisSettings
from optics.systems import create_default_system, validate_system


class TestObjectAtInfinity:
    """Test object at infinity edge case."""
    
    def test_image_at_focal_plane(self):
        """Object at infinity should produce image at focal plane."""
        f = 0.1  # 100mm
        s_prime = image_distance(f, float('-inf'))
        assert s_prime == pytest.approx(f, rel=1e-10)
    
    def test_magnification_approaches_zero(self):
        """Magnification should approach zero for object at infinity."""
        f = 0.1
        s = -1e10  # Very far away
        s_prime = image_distance(f, s)
        m = s_prime / s
        assert abs(m) < 1e-6


class TestObjectAtFocalPoint:
    """Test object at focal point (image at infinity)."""
    
    def test_image_at_infinity(self):
        """Object at focal point should produce image at infinity."""
        f = 0.1
        s = -f  # Object at focal point
        # This should raise ValueError or return infinity
        with pytest.raises((ValueError, ZeroDivisionError)):
            image_distance(f, s)
    
    def test_near_focal_point(self):
        """Object just inside focal point should produce virtual image."""
        f = 0.1
        s = -f * 0.999  # Just inside focal point
        s_prime = image_distance(f, s)
        assert s_prime < 0  # Virtual image (negative distance)


class TestZeroAndNegativeAperture:
    """Test aperture edge cases."""
    
    def test_zero_aperture_raises(self):
        """Zero aperture should raise ValueError."""
        with pytest.raises(ValueError):
            ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0)
    
    def test_negative_aperture_raises(self):
        """Negative aperture should raise ValueError."""
        with pytest.raises(ValueError):
            ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=-0.025)
    
    def test_very_small_aperture(self):
        """Very small aperture should work."""
        lens = ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=1e-6)
        assert lens.aperture_diameter == 1e-6
    
    def test_very_large_aperture(self):
        """Very large aperture should work."""
        lens = ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=1.0)
        assert lens.aperture_diameter == 1.0


class TestExtremeFocalLengths:
    """Test very short and very long focal lengths."""
    
    def test_very_short_focal_length(self):
        """Focal length of 1 micrometer."""
        f = 1e-6
        s = -2e-6  # 2um object distance (2f)
        s_prime = image_distance(f, s)
        assert math.isfinite(s_prime)
        assert s_prime > 0
    
    def test_very_long_focal_length(self):
        """Focal length of 1 kilometer."""
        f = 1e3
        s = -1e4  # 10km object distance
        s_prime = image_distance(f, s)
        assert math.isfinite(s_prime)
    
    def test_diverging_lens(self):
        """Negative focal length (diverging lens)."""
        f = -0.1
        s = -0.2
        s_prime = image_distance(f, s)
        assert s_prime < 0  # Virtual image


class TestSingleComponentSystem:
    """Test system with only one lens."""
    
    def test_single_lens_system(self):
        """System with one lens should work."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        analysis = analyze_system(system)
        assert math.isfinite(analysis.effective_focal_length)
        assert math.isfinite(analysis.rms_spot_radius)


class TestManyComponentSystem:
    """Test system with many components."""
    
    def test_ten_element_system(self):
        """System with 10 lenses."""
        components = []
        for i in range(10):
            components.append(ThinLens(
                id=f"L{i+1}",
                position=0.05 + i * 0.03,
                focal_length=0.05 + i * 0.01,
                aperture_diameter=0.02,
                material="N-BK7",
            ))
        
        system = OpticalSystem(
            components=components,
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.005),
            image_plane=ImagePlane(position=0.4),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        analysis = analyze_system(system)
        assert math.isfinite(analysis.effective_focal_length)


class TestExtremeFNumber:
    """Test very fast and very slow optics."""
    
    def test_very_fast_optics(self):
        """f/0.5 system."""
        f = 0.05
        D = 0.1  # Aperture larger than focal length
        fn = f_number(f, D)
        assert fn == pytest.approx(0.5, rel=1e-6)
    
    def test_very_slow_optics(self):
        """f/100 system."""
        f = 0.1
        D = 0.001  # Very small aperture
        fn = f_number(f, D)
        assert fn == pytest.approx(100.0, rel=1e-6)
    
    def test_high_na_system(self):
        """Numerical aperture > 0.9."""
        na = numerical_aperture(1.5, math.radians(60))  # n=1.5, 60 degree half-angle
        assert na > 0.9


class TestVirtualImages:
    """Test virtual image formation."""
    
    def test_concave_lens_virtual_image(self):
        """Concave lens should always produce virtual image."""
        f = -0.1
        for s in [-0.05, -0.1, -0.2, -0.5]:
            s_prime = image_distance(f, s)
            assert s_prime < 0, f"Expected virtual image for s={s}, got s'={s_prime}"
    
    def test_converging_lens_inside_focal(self):
        """Converging lens with object inside focal length produces virtual image."""
        f = 0.1
        s = -0.05  # Inside focal length
        s_prime = image_distance(f, s)
        assert s_prime < 0  # Virtual image


class TestValidationWarnings:
    """Test system validation warnings."""
    
    def test_overlapping_components_warning(self):
        """Components at same position should generate warning."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
                ThinLens(id="L2", position=0.1, focal_length=0.05, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        warnings = validate_system(system)
        assert any('overlap' in w.lower() for w in warnings)
    
    def test_object_after_lens_warning(self):
        """Object after first lens should generate warning."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.0, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.1, height=0.01),  # Object at same position as lens
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        warnings = validate_system(system)
        assert len(warnings) > 0


class TestNaNAndInfinityHandling:
    """Test handling of NaN and Infinity inputs."""
    
    def test_nan_focal_length_propagates(self):
        """NaN focal length should propagate through calculations."""
        # NaN is technically a valid float, so it may not be rejected
        # but it should produce NaN results, not crash
        lens = ThinLens(id="L1", position=0.1, focal_length=float('nan'), aperture_diameter=0.025)
        assert math.isnan(lens.focal_length)
    
    def test_infinity_focal_length_handled(self):
        """Infinity focal length (flat surface) should be handled."""
        lens = ThinLens(id="L1", position=0.1, focal_length=float('inf'), aperture_diameter=0.025)
        assert lens.focal_length == float('inf')
        # Image at focal plane for object at infinity
        s_prime = image_distance(float('inf'), float('-inf'))
        assert math.isfinite(s_prime) or math.isinf(s_prime)
    
    def test_nan_position_propagates(self):
        """NaN position should propagate through calculations."""
        lens = ThinLens(id="L1", position=float('nan'), focal_length=0.1, aperture_diameter=0.025)
        assert math.isnan(lens.position)
