"""
Tests for polarization analysis module.
"""

import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.polarization import (
    JonesVector, JonesMatrix,
    MuellerMatrix, StokesVector,
    jones_linear_polarizer, jones_wave_plate,
    mueller_linear_polarizer, mueller_wave_plate,
    stokes_unpolarized, stokes_linear, stokes_right_circular,
    degree_of_polarization
)


class TestJonesVector:
    """Tests for Jones vectors."""
    
    def test_horizontal(self):
        j = JonesVector.horizontal()
        assert j.Ex == pytest.approx(1.0)
        assert j.Ey == pytest.approx(0.0)
    
    def test_vertical(self):
        j = JonesVector.vertical()
        assert j.Ex == pytest.approx(0.0)
        assert j.Ey == pytest.approx(1.0)
    
    def test_intensity(self):
        j = JonesVector(1, 1)
        assert j.intensity == pytest.approx(2.0)
    
    def test_apply_matrix(self):
        j = JonesVector.horizontal()
        pol = jones_linear_polarizer(0)
        result = j.apply(pol)
        assert result.Ex == pytest.approx(1.0, abs=0.01)


class TestJonesMatrix:
    """Tests for Jones matrices."""
    
    def test_identity(self):
        I = JonesMatrix(np.eye(2, dtype=complex))
        j = JonesVector(1, 1)
        result = j.apply(I)
        assert result.Ex == pytest.approx(1.0)
        assert result.Ey == pytest.approx(1.0)
    
    def test_linear_polarizer(self):
        pol = jones_linear_polarizer(0)
        j = JonesVector.horizontal()
        result = j.apply(pol)
        assert result.intensity == pytest.approx(1.0, abs=0.01)
    
    def test_wave_plate(self):
        wp = jones_wave_plate(np.pi / 2)
        assert wp.matrix.shape == (2, 2)


class TestMuellerMatrix:
    """Tests for Mueller matrices."""
    
    def test_linear_polarizer(self):
        M = mueller_linear_polarizer(0)
        S = StokesVector(1, 1, 0, 0)
        result = M @ S
        assert result.S0 > 0
    
    def test_wave_plate(self):
        M = mueller_wave_plate(np.pi / 2)
        assert M.matrix.shape == (4, 4)


class TestStokesVector:
    """Tests for Stokes vectors."""
    
    def test_unpolarized(self):
        S = stokes_unpolarized(1.0)
        assert S.S0 == 1.0
        assert S.S1 == 0.0
        assert S.dop == pytest.approx(0.0)
    
    def test_linear(self):
        S = stokes_linear(1.0, 0)
        assert S.S0 == 1.0
        assert S.S1 == 1.0
        assert S.dop == pytest.approx(1.0)
    
    def test_circular(self):
        S = stokes_right_circular(1.0)
        assert S.S3 == pytest.approx(1.0)
        assert S.docp == pytest.approx(1.0)


class TestDegreeOfPolarization:
    """Tests for DOP calculations."""
    
    def test_unpolarized(self):
        S = stokes_unpolarized(1.0)
        assert degree_of_polarization(S) == pytest.approx(0.0)
    
    def test_fully_polarized(self):
        S = stokes_linear(1.0, 0)
        assert degree_of_polarization(S) == pytest.approx(1.0)
