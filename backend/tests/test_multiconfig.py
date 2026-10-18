"""
Tests for multi-configuration module.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.multiconfig import (
    MultiConfigSystem, Configuration, ConfigType,
    ZoomConfig, FocusConfig, ThermalConfig
)
from optics.models import OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings


def create_test_system():
    return OpticalSystem(
        components=[
            ThinLens(id="L1", position=0.1, focal_length=0.05, aperture_diameter=0.025, material="N-BK7"),
            ThinLens(id="L2", position=0.2, focal_length=0.05, aperture_diameter=0.025, material="N-BK7"),
        ],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=0.01),
        image_plane=ImagePlane(position=0.3),
        analysis_settings=AnalysisSettings(num_rays=11, ray_types=['chief', 'marginal', 'fill'], aperture_fraction=1.0, wavelength=550e-9),
    )


class TestConfiguration:
    """Tests for configurations."""
    
    def test_create_config(self):
        config = Configuration(config_id=0, config_type=ConfigType.ZOOM, name="Wide")
        assert config.config_id == 0
        assert config.config_type == ConfigType.ZOOM
    
    def test_zoom_config(self):
        config = ZoomConfig(config_id=0, zoom_position=0.0, focal_length=50.0)
        assert config.zoom_position == 0.0
        assert config.focal_length == 50.0
    
    def test_focus_config(self):
        config = FocusConfig(config_id=0, object_distance=1000.0)
        assert config.object_distance == 1000.0


class TestMultiConfigSystem:
    """Tests for multi-config systems."""
    
    def test_create_system(self):
        system = create_test_system()
        mcs = MultiConfigSystem(base_system=system)
        assert len(mcs.configurations) == 0
    
    def test_add_config(self):
        system = create_test_system()
        mcs = MultiConfigSystem(base_system=system)
        config = Configuration(config_id=0, config_type=ConfigType.ZOOM)
        idx = mcs.add_config(config)
        assert idx == 0
        assert len(mcs.configurations) == 1
    
    def test_get_system(self):
        system = create_test_system()
        mcs = MultiConfigSystem(base_system=system)
        config = Configuration(config_id=0, config_type=ConfigType.ZOOM)
        mcs.add_config(config)
        result = mcs.get_system(0)
        assert result is not None
        assert len(result.components) == 2
