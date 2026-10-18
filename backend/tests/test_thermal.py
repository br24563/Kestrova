"""
Tests for thermal analysis module.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.thermal import (
    ThermalAnalyzer, thermal_defocus, athermalization_check, temperature_sweep,
    ThermalProperties, get_thermal_properties, index_at_temperature
)
from optics.models import OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings


def create_test_system():
    return OpticalSystem(
        components=[
            ThinLens(id="L1", position=0.1, focal_length=0.05, aperture_diameter=0.025, material="N-BK7"),
        ],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=0.01),
        image_plane=ImagePlane(position=0.3),
        analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
    )


class TestThermalProperties:
    """Tests for thermal properties."""
    
    def test_get_properties(self):
        props = get_thermal_properties("N-BK7")
        assert props is not None
        assert props.name == "N-BK7"
        assert props.dn_dT != 0
    
    def test_index_at_temperature(self):
        n = index_at_temperature("N-BK7", 1.5168, 20.0, 100.0)
        assert n != 1.5168  # Should change with temperature


class TestThermalAnalyzer:
    """Tests for thermal analyzer."""
    
    def test_create_analyzer(self):
        system = create_test_system()
        analyzer = ThermalAnalyzer(system)
        assert analyzer.base_temp == 20.0
    
    def test_analyze_at_temperature(self):
        system = create_test_system()
        analyzer = ThermalAnalyzer(system)
        result = analyzer.analyze_at_temperature(50.0)
        assert result.temperature == 50.0
        assert result.focal_shift >= 0
    
    def test_temperature_sweep(self):
        system = create_test_system()
        analyzer = ThermalAnalyzer(system)
        results = analyzer.temperature_sweep((-20, 60), 5)
        assert len(results) == 5


class TestThermalFunctions:
    """Tests for thermal analysis functions."""
    
    def test_thermal_defocus(self):
        system = create_test_system()
        defocus = thermal_defocus(system, 50.0)
        assert isinstance(defocus, float)
    
    def test_temperature_sweep_function(self):
        system = create_test_system()
        results = temperature_sweep(system, (-20, 60), 5)
        assert len(results) == 5
        assert 'temperature' in results[0]
