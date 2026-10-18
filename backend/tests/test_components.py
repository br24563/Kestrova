"""
Tests for optical components.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.components import (
    Prism, RightAnglePrism, PorroPrism, DovePrism, PentaPrism, WedgePrism,
    FoldMirror, DichroicMirror, BeamSplitCube, BeamSplitPlate, create_prism
)


class TestPrisms:
    """Tests for prism components."""
    
    def test_right_angle_prism(self):
        prism = RightAnglePrism(size=25.4)
        assert prism.deviation_angle() == 90.0
        assert prism.reflection_count == 1
    
    def test_porro_prism(self):
        prism = PorroPrism(size=25.4)
        assert prism.deviation_angle() == 180.0
        assert prism.reflection_count == 2
    
    def test_dove_prism(self):
        prism = DovePrism(length=50.8, height=25.4)
        assert prism.reflection_count == 1
    
    def test_penta_prism(self):
        prism = PentaPrism(size=25.4)
        assert prism.deviation_angle() == 90.0
        assert prism.reflection_count == 2
    
    def test_wedge_prism(self):
        prism = WedgePrism(wedge_angle=5.0, size=25.4)
        dev = prism.deviation_angle()
        assert dev > 0  # Should deviate beam
    
    def test_create_prism_factory(self):
        prism = create_prism('right_angle', size=25.4)
        assert isinstance(prism, RightAnglePrism)


class TestMirrors:
    """Tests for mirror components."""
    
    def test_fold_mirror(self):
        mirror = FoldMirror(size=25.4)
        assert mirror.reflectivity > 0.8
    
    def test_dichroic_mirror(self):
        mirror = DichroicMirror(cutoff_wavelength=550.0)
        R, T = mirror.response(600.0)
        assert R + T == pytest.approx(1.0, abs=0.1)


class TestBeamSplitters:
    """Tests for beam splitter components."""
    
    def test_cube_splitter(self):
        splitter = BeamSplitCube(size=25.4, ratio=0.5)
        assert splitter.reflectivity == 0.5
        assert splitter.transmission == 0.5
    
    def test_plate_splitter(self):
        splitter = BeamSplitPlate(size=25.4, ratio=0.5)
        assert splitter.reflectivity == 0.5
