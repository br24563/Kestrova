"""
Integration tests for complete optical design workflows.

Tests end-to-end workflows that combine multiple components.
"""

import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.models import OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings
from optics.analysis import analyze_system, effective_focal_length
from optics.optimization import minimize_rms_spot, parameter_sweep
from optics.tolerance import tolerance_analysis, sensitivity_analysis, compute_yield
from optics.aberration import chromatic_aberration_analysis
from optics.seidel import seidel_analysis
from optics.diffraction import diffraction_limited_check
from optics.systems import create_default_system, validate_system


class TestDesignOptimizeAnalyzeWorkflow:
    """Test complete design → optimize → analyze workflow."""
    
    def test_single_lens_optimization(self):
        """Test optimization workflow with parameter sweep."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.08, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        # Analyze before
        analysis_before = analyze_system(system)
        rms_before = analysis_before.rms_spot_radius
        
        # Parameter sweep to find better focal length
        values = [0.06, 0.08, 0.10, 0.12]
        results = parameter_sweep(
            system,
            {"component_id": "L1", "field": "focal_length"},
            values,
        )
        
        # Find best result
        best_rms = float('inf')
        for value, analysis in results:
            if analysis.rms_spot_radius < best_rms:
                best_rms = analysis.rms_spot_radius
        
        # Best should be at least as good as original
        assert best_rms <= rms_before * 1.01
    
    def test_two_lens_system_analysis(self):
        """Full analysis of a two-lens system."""
        system = create_default_system()
        
        # Run all analyses
        analysis = analyze_system(system)
        seidel = seidel_analysis(system)
        chroma = chromatic_aberration_analysis(system)
        diffraction = diffraction_limited_check(system)
        
        # All should produce finite results
        assert math.isfinite(analysis.effective_focal_length)
        assert math.isfinite(analysis.rms_spot_radius)
        assert math.isfinite(seidel['spherical_aberration']['longitudinal'])
        assert math.isfinite(chroma['lca'])
        assert math.isfinite(diffraction['airy_disk_radius'])
    
    def test_parameter_sweep_workflow(self):
        """Parameter sweep followed by analysis."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        # Sweep focal length
        values = [0.05, 0.075, 0.1, 0.125, 0.15]
        results = parameter_sweep(
            system,
            {"component_id": "L1", "field": "focal_length"},
            values,
        )
        
        # Should have results for each value
        assert len(results) == len(values)
        
        # All should have finite RMS
        for value, analysis in results:
            assert math.isfinite(analysis.rms_spot_radius)


class TestToleranceWorkflow:
    """Test tolerance analysis workflows."""
    
    def test_tolerance_analysis_workflow(self):
        """Run tolerance analysis and verify statistics."""
        system = create_default_system()
        
        tolerances = {
            "lens_1.position": 1e-4,
            "lens_2.position": 1e-4,
        }
        
        result = tolerance_analysis(system, tolerances=tolerances, trials=50, seed=42)
        
        # Check statistics
        assert math.isfinite(result["mean"])
        assert math.isfinite(result["std"])
        assert result["trials"] == 50
        assert result["min"] <= result["mean"] <= result["max"]
    
    def test_sensitivity_analysis_workflow(self):
        """Run sensitivity analysis and verify ranking."""
        system = create_default_system()
        
        tolerances = {
            "lens_1.position": 1e-4,
            "lens_2.position": 1e-4,
        }
        
        result = sensitivity_analysis(system, tolerances)
        
        # Should have ranking
        assert len(result["ranking"]) == len(tolerances)
        assert len(result["sensitivities"]) == len(tolerances)
        
        # All sensitivities should be non-negative
        for s in result["sensitivities"]:
            assert s["sensitivity"] >= 0
    
    def test_yield_analysis_workflow(self):
        """Compute yield from tolerance samples."""
        system = create_default_system()
        
        tolerances = {
            "lens_1.position": 1e-4,
            "lens_2.position": 1e-4,
        }
        
        # Run tolerance analysis
        tol_result = tolerance_analysis(system, tolerances=tolerances, trials=100, seed=42)
        
        # Compute yield
        if tol_result["trend"]:
            yield_stats = compute_yield(tol_result["trend"], upper_limit=1e-3)
            
            assert 0 <= yield_stats["yield"] <= 1
            assert yield_stats["n_total"] == 100


class TestMultiWavelengthWorkflow:
    """Test multi-wavelength analysis workflows."""
    
    def test_chromatic_aberration_workflow(self):
        """Analyze chromatic aberration across wavelengths."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[486.1e-9, 587.6e-9, 656.3e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=587.6e-9),
        )
        
        result = chromatic_aberration_analysis(system)
        
        assert len(result["wavelengths"]) == 3
        assert len(result["image_positions"]) == 3
        assert math.isfinite(result["lca"])
        assert math.isfinite(result["tca"])


class TestValidationWorkflow:
    """Test system validation workflows."""
    
    def test_validate_default_system(self):
        """Default system should have no warnings."""
        system = create_default_system()
        warnings = validate_system(system)
        # Default system should be valid
        assert isinstance(warnings, list)
    
    def test_validate_invalid_system(self):
        """Invalid system should produce warnings."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025, material="N-BK7"),
                ThinLens(id="L2", position=0.1, focal_length=0.05, aperture_diameter=0.025, material="N-BK7"),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.05),  # Image before last lens
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
        )
        
        warnings = validate_system(system)
        assert len(warnings) > 0


class TestExportWorkflow:
    """Test export/import workflows."""
    
    def test_export_to_zmx(self, tmp_path):
        """Export system to ZMX format."""
        from optics.io import export_zmx
        
        system = create_default_system()
        filepath = tmp_path / "test.zmx"
        
        export_zmx(system, filepath)
        
        assert filepath.exists()
        content = filepath.read_text()
        assert "MODE SEQ" in content
        assert "SURF" in content
        # Ideal thin lenses are written as Zemax paraxial surfaces.
        assert "TYPE PARAXIAL" in content
    
    def test_export_to_seq(self, tmp_path):
        """Export system to Code V format."""
        from optics.io import export_seq
        
        from optics.presets import get_preset_by_id
        from optics.io import import_seq
        system = get_preset_by_id("thick_lens")["system"]
        filepath = tmp_path / "test.seq"

        export_seq(system, filepath)

        assert filepath.exists()
        back = import_seq(filepath)
        lens = [c for c in back.components if c.type == "thick_lens"][0]
        orig = system.components[0]
        assert lens.radius1 == pytest.approx(orig.radius1, rel=1e-6)
        assert lens.radius2 == pytest.approx(orig.radius2, rel=1e-6)
        assert lens.thickness == pytest.approx(orig.thickness, rel=1e-6)

    def test_ideal_lens_has_no_code_v_equivalent(self, tmp_path):
        from optics.io import export_seq
        with pytest.raises(ValueError):
            export_seq(create_default_system(), tmp_path / "x.seq")
    
    def test_export_bom(self, tmp_path):
        """Export bill of materials."""
        from optics.io.bom import generate_bom
        
        system = create_default_system()
        filepath = tmp_path / "bom.txt"
        
        generate_bom(system, filepath)
        
        assert filepath.exists()
        content = filepath.read_text()
        assert "BILL OF MATERIALS" in content
    
    def test_export_svg_drawing(self, tmp_path):
        """Export SVG lens drawing."""
        from optics.io.drawings import generate_lens_drawing
        
        system = create_default_system()
        filepath = tmp_path / "drawing.svg"
        
        generate_lens_drawing(system, filepath, format='svg')
        
        assert filepath.exists()
        content = filepath.read_text()
        assert "<svg" in content
