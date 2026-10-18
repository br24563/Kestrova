"""
Tests for physical optics module.
"""

import math
import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.physical import (
    GaussianBeam, BeamParameter, ABCDMatrix,
    free_space_propagation, lens_transform, propagate_beam,
    fresnel_diffraction, fraunhofer_diffraction, angular_spectrum_propagation,
    SingleModeFiber, MultiModeFiber, coupling_efficiency, alignment_sensitivity,
    TemporalCoherence, SpatialCoherence, interference_pattern, fringe_visibility
)


class TestBeamParameter:
    """Tests for beam parameter."""
    
    def test_from_waist(self):
        bp = BeamParameter.from_waist(10e-6, 550e-9)
        assert bp.w0 == pytest.approx(10e-6, rel=1e-6)
        assert bp.z_R > 0
    
    def test_beam_radius(self):
        bp = BeamParameter.from_waist(10e-6, 550e-9)
        # At waist, beam radius equals w0
        assert bp.w == pytest.approx(bp.w0, rel=0.01)
    
    def test_divergence(self):
        bp = BeamParameter.from_waist(10e-6, 550e-9)
        assert bp.divergence > 0


class TestGaussianBeam:
    """Tests for Gaussian beam."""
    
    def test_creation(self):
        beam = GaussianBeam(w0=10e-6, wavelength=550e-9)
        assert beam.w0 == 10e-6
        assert beam.wavelength == 550e-9
        assert beam.M2 == 1.0
    
    def test_beam_radius(self):
        beam = GaussianBeam(w0=10e-6, wavelength=550e-9)
        # At waist
        w = beam.beam_radius(beam.position)
        assert w == pytest.approx(10e-6, rel=0.01)
    
    def test_divergence(self):
        beam = GaussianBeam(w0=10e-6, wavelength=550e-9)
        div = beam.divergence()
        assert div > 0
        # Smaller waist = larger divergence
        beam2 = GaussianBeam(w0=5e-6, wavelength=550e-9)
        assert beam2.divergence() > div
    
    def test_intensity(self):
        beam = GaussianBeam(w0=10e-6, wavelength=550e-9, power=1.0)
        I = beam.intensity(beam.position, 0)
        assert I > 0


class TestABCDMatrix:
    """Tests for ABCD matrix."""
    
    def test_free_space(self):
        M = ABCDMatrix.free_space(0.1)
        assert M.A == 1
        assert M.B == 0.1
        assert M.C == 0
        assert M.D == 1
    
    def test_thin_lens(self):
        M = ABCDMatrix.thin_lens(0.1)
        assert M.A == 1
        assert M.B == 0
        assert M.C == pytest.approx(-10)
        assert M.D == 1
    
    def test_matrix_multiplication(self):
        M1 = ABCDMatrix.free_space(0.1)
        M2 = ABCDMatrix.thin_lens(0.05)
        M3 = M1 @ M2
        assert isinstance(M3, ABCDMatrix)


class TestPropagation:
    """Tests for beam propagation."""
    
    def test_free_space_propagation(self):
        beam = GaussianBeam(w0=10e-6, wavelength=550e-9)
        propagated = free_space_propagation(beam, 0.1)
        assert propagated.position == pytest.approx(0.1)
    
    def test_lens_transform(self):
        beam = GaussianBeam(w0=10e-6, wavelength=550e-9)
        transformed = lens_transform(beam, 0.1)
        assert isinstance(transformed, GaussianBeam)
    
    def test_propagate_beam(self):
        beam = GaussianBeam(w0=10e-6, wavelength=550e-9)
        elements = [
            ('free_space', 0.05),
            ('lens', 0.1),
            ('free_space', 0.1)
        ]
        result = propagate_beam(beam, elements)
        assert isinstance(result, GaussianBeam)


class TestDiffraction:
    """Tests for diffraction propagation."""
    
    def test_fresnel_diffraction(self):
        # Create simple field
        field = np.ones((64, 64), dtype=complex)
        result = fresnel_diffraction(field, 550e-9, 0.01, 1e-6)
        assert result.shape == field.shape
    
    def test_fraunhofer_diffraction(self):
        field = np.ones((64, 64), dtype=complex)
        result = fraunhofer_diffraction(field, 550e-9, 0.1, 1e-6)
        assert result.shape == field.shape
    
    def test_angular_spectrum(self):
        field = np.ones((64, 64), dtype=complex)
        result = angular_spectrum_propagation(field, 550e-9, 0.01, 1e-6)
        assert result.shape == field.shape


class TestFiber:
    """Tests for fiber coupling."""
    
    def test_single_mode_fiber(self):
        smf = SingleModeFiber(core_radius=4e-6, wavelength=1550e-9, NA=0.12)
        assert smf.is_single_mode
        assert smf.mode_field_diameter > 0
    
    def test_multi_mode_fiber(self):
        mmf = MultiModeFiber(wavelength=850e-9)
        assert not mmf.is_single_mode
        assert mmf.num_modes > 1
    
    def test_coupling_efficiency(self):
        beam = GaussianBeam(w0=5e-6, wavelength=1550e-9)
        fiber = SingleModeFiber(core_radius=4e-6, wavelength=1550e-9, NA=0.12)
        eff = coupling_efficiency(beam, fiber)
        assert 0 <= eff <= 1
    
    def test_alignment_sensitivity(self):
        beam = GaussianBeam(w0=5e-6, wavelength=1550e-9)
        fiber = SingleModeFiber(core_radius=4e-6, wavelength=1550e-9, NA=0.12)
        sensitivity = alignment_sensitivity(beam, fiber, scan_range=10e-6, num_points=10)
        assert 'lateral_efficiency' in sensitivity
        assert 'peak_efficiency' in sensitivity


class TestCoherence:
    """Tests for coherence modeling."""
    
    def test_temporal_coherence(self):
        tc = TemporalCoherence(wavelength=550e-9, bandwidth=1e-9)
        assert tc.coherence_length > 0
        assert tc.coherence_time > 0
    
    def test_spatial_coherence(self):
        sc = SpatialCoherence(wavelength=550e-9, source_size=1e-3, distance=1.0)
        assert sc.coherence_width > 0
    
    def test_interference_pattern(self):
        x, I = interference_pattern(
            wavelength=550e-9,
            slit_separation=0.1e-3,
            screen_distance=1.0,
            screen_width=10e-3,
            num_points=100
        )
        assert len(x) == 100
        assert len(I) == 100
    
    def test_fringe_visibility(self):
        vis = fringe_visibility(1.0, 0.1)
        assert 0 <= vis <= 1
        # Perfect contrast
        vis_perfect = fringe_visibility(1.0, 0.0)
        assert vis_perfect == pytest.approx(1.0)
