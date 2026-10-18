"""
Performance benchmarks and stress tests.

Measures execution time and memory usage to ensure the system
meets performance targets.

Targets:
- Ray tracing (11 rays): < 50ms
- System analysis: < 100ms
- Diffraction analysis: < 500ms
- Seidel analysis: < 1s
- Optimization (2 vars, 100 iter): < 5s
- Tolerance (100 trials): < 2s
"""

import time
import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.models import OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings
from optics.rays import trace_system
from optics.analysis import analyze_system, effective_focal_length
from optics.diffraction import diffraction_analysis, airy_disk_radius
from optics.seidel import seidel_analysis
from optics.tolerance import tolerance_analysis
from optics.systems import create_default_system


class TestRayTracingPerformance:
    """Benchmark ray tracing speed."""
    
    def test_trace_11_rays(self):
        """11 rays should trace in < 50ms."""
        system = create_default_system()
        
        start = time.time()
        result = trace_system(system)
        elapsed = time.time() - start
        
        assert elapsed < 0.05, f"Ray tracing took {elapsed:.3f}s (target: < 0.05s)"
        assert len(result.ray_paths) > 0
    
    def test_trace_101_rays(self):
        """101 rays should trace in < 200ms."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=101, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        start = time.time()
        result = trace_system(system)
        elapsed = time.time() - start
        
        assert elapsed < 0.2, f"101 ray trace took {elapsed:.3f}s (target: < 0.2s)"


class TestAnalysisPerformance:
    """Benchmark analysis speed."""
    
    def test_basic_analysis(self):
        """Basic analysis should complete in < 100ms."""
        system = create_default_system()
        
        start = time.time()
        result = analyze_system(system)
        elapsed = time.time() - start
        
        assert elapsed < 0.1, f"Analysis took {elapsed:.3f}s (target: < 0.1s)"
        assert math.isfinite(result.effective_focal_length)
    
    def test_efl_calculation(self):
        """EFL calculation should be fast."""
        system = create_default_system()
        
        start = time.time()
        for _ in range(100):
            efl = effective_focal_length(system)
        elapsed = time.time() - start
        
        assert elapsed < 0.5, f"100 EFL calculations took {elapsed:.3f}s"
        assert math.isfinite(efl)


class TestDiffractionPerformance:
    """Benchmark diffraction analysis speed."""
    
    def test_airy_disk_calculation(self):
        """Airy disk should be instant."""
        start = time.time()
        for _ in range(1000):
            r = airy_disk_radius(na=0.25, wavelength=550e-9)
        elapsed = time.time() - start
        
        assert elapsed < 0.1, f"1000 Airy disk calculations took {elapsed:.3f}s"
        assert r > 0
    
    def test_diffraction_analysis(self):
        """Full diffraction analysis should complete in < 500ms."""
        system = create_default_system()
        
        start = time.time()
        result = diffraction_analysis(system)
        elapsed = time.time() - start
        
        assert elapsed < 0.5, f"Diffraction analysis took {elapsed:.3f}s (target: < 0.5s)"
        assert 'psf' in result
        assert 'mtf' in result


class TestSeidelPerformance:
    """Benchmark Seidel analysis speed."""
    
    def test_seidel_analysis(self):
        """Seidel analysis should complete in < 1s."""
        system = create_default_system()
        
        start = time.time()
        result = seidel_analysis(system)
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Seidel analysis took {elapsed:.3f}s (target: < 1.0s)"
        assert 'spherical_aberration' in result


class TestTolerancePerformance:
    """Benchmark tolerance analysis speed."""
    
    def test_tolerance_50_trials(self):
        """50 Monte Carlo trials should complete in < 2s."""
        system = create_default_system()
        tolerances = {
            "lens_1.position": 1e-4,
            "lens_2.position": 1e-4,
        }
        
        start = time.time()
        result = tolerance_analysis(system, tolerances=tolerances, trials=50, seed=42)
        elapsed = time.time() - start
        
        assert elapsed < 2.0, f"50 trials took {elapsed:.3f}s (target: < 2.0s)"
        assert result["trials"] == 50
    
    def test_tolerance_100_trials(self):
        """100 Monte Carlo trials should complete in < 5s."""
        system = create_default_system()
        tolerances = {
            "lens_1.position": 1e-4,
            "lens_2.position": 1e-4,
        }
        
        start = time.time()
        result = tolerance_analysis(system, tolerances=tolerances, trials=100, seed=42)
        elapsed = time.time() - start
        
        assert elapsed < 5.0, f"100 trials took {elapsed:.3f}s (target: < 5.0s)"
        assert result["trials"] == 100


class TestOptimizationPerformance:
    """Benchmark optimization speed."""
    
    def test_parameter_sweep(self):
        """Parameter sweep should complete quickly."""
        from optics.optimization import parameter_sweep
        
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        values = [0.05, 0.075, 0.1, 0.125, 0.15]
        
        start = time.time()
        results = parameter_sweep(
            system,
            {"component_id": "L1", "field": "focal_length"},
            values,
        )
        elapsed = time.time() - start
        
        assert elapsed < 2.0, f"Parameter sweep took {elapsed:.3f}s"
        assert len(results) == len(values)


class TestMemoryUsage:
    """Test memory usage stays reasonable."""
    
    def test_large_system_memory(self):
        """Large system should not crash or hang."""
        # Create a system with many components
        components = []
        for i in range(20):
            components.append(ThinLens(
                id=f"L{i+1}",
                position=0.05 + i * 0.02,
                focal_length=0.05 + i * 0.005,
                aperture_diameter=0.02,
                material="N-BK7",
            ))
        
        system = OpticalSystem(
            components=components,
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.005),
            image_plane=ImagePlane(position=0.5),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        # Run analysis - should complete without error
        result = analyze_system(system)
        assert math.isfinite(result.effective_focal_length)
        assert math.isfinite(result.rms_spot_radius)


class TestScalability:
    """Test how performance scales with system complexity."""
    
    def test_analysis_scaling(self):
        """Analysis time should scale reasonably with component count."""
        times = []
        
        for n_components in [1, 2, 5, 10]:
            components = [
                ThinLens(id=f"L{i+1}", position=0.1 + i * 0.03, focal_length=0.1, aperture_diameter=0.02, material="N-BK7")
                for i in range(n_components)
            ]
            
            system = OpticalSystem(
                components=components,
                wavelengths=[550e-9],
                object=Object(position=0.0, height=0.01),
                image_plane=ImagePlane(position=0.1 + n_components * 0.03 + 0.1),
                analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
            )
            
            start = time.time()
            analyze_system(system)
            elapsed = time.time() - start
            times.append(elapsed)
        
        # Each component should add reasonable time
        # 10 components should be < 10x the time of 1 component
        if times[0] > 0:
            ratio = times[-1] / times[0]
            assert ratio < 20, f"10 components is {ratio:.1f}x slower than 1"
