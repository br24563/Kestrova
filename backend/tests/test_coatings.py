"""
Tests for thin film coating module.
"""

import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.coatings import (
    Layer, Coating,
    design_ar_coating, design_hr_coating,
    reflection_transmission
)


class TestLayer:
    """Tests for coating layers."""
    
    def test_layer_creation(self):
        layer = Layer('MgF2', 100)
        assert layer.material == 'MgF2'
        assert layer.thickness == 100
        assert layer.n is not None
    
    def test_optical_thickness(self):
        layer = Layer('MgF2', 100)
        assert layer.optical_thickness > 0


class TestCoating:
    """Tests for multilayer coatings."""
    
    def test_coating_creation(self):
        coating = Coating(name='Test')
        assert coating.layers == []
    
    def test_add_layer(self):
        coating = Coating(name='Test')
        coating.add_layer('MgF2', 100)
        assert len(coating.layers) == 1
    
    def test_reflectance(self):
        coating = design_ar_coating(550)
        R = coating.reflectance(550)
        assert 0 <= R <= 1
    
    def test_transmittance(self):
        coating = design_ar_coating(550)
        T = coating.transmittance(550)
        assert 0 <= T <= 1


class TestARCoating:
    """Tests for anti-reflection coatings."""
    
    def test_design(self):
        coating = design_ar_coating(550, 1.5)
        assert len(coating.layers) == 1
        assert coating.layers[0].material == 'MgF2'
    
    def test_performance(self):
        coating = design_ar_coating(550, 1.5)
        R = coating.reflectance(550)
        # AR coating should reduce reflection
        assert R < 0.05  # Less than 5% reflection


class TestHRCoating:
    """Tests for high-reflectivity coatings."""
    
    def test_design(self):
        coating = design_hr_coating(550, num_pairs=5)
        assert len(coating.layers) == 11  # 5 pairs + cap
    
    def test_performance(self):
        coating = design_hr_coating(550, num_pairs=10)
        R = coating.reflectance(550)
        # HR coating should have high reflection
        assert R > 0.9  # More than 90% reflection


class TestTransferMatrix:
    """Tests for transfer matrix calculations."""
    
    def test_reflection_transmission(self):
        layers = [Layer('MgF2', 100)]
        R, T, r, t = reflection_transmission(layers, 550)
        assert 0 <= R <= 1
        assert 0 <= T <= 1
        assert abs(R + T) <= 1.01  # Energy conservation
