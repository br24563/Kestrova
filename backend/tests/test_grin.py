"""
Tests for GRIN materials module.
"""

import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.grin import (
    GRINProfile, AxialGRIN, RadialGRIN, GRIN3D,
    GRINMaterial, create_grin_material, GRIN_MATERIALS,
    GRINRay, trace_grin, grin_lens_focus
)


class TestGRINProfile:
    """Tests for GRIN profiles."""
    
    def test_axial_grin(self):
        profile = AxialGRIN(n0=1.5, coefficients=[1.5, -0.01, 0.001])
        n = profile.index(0)
        assert n == pytest.approx(1.5)
    
    def test_radial_grin(self):
        profile = RadialGRIN(n0=1.5, g=0.1)
        n_center = profile.index(0, 0, 0)
        n_edge = profile.index(0.1, 0, 0)
        assert n_center > n_edge  # Index decreases radially
    
    def test_grin3d(self):
        profile = GRIN3D(n0=1.5, gradient_vector=np.array([0.01, 0, 0]))
        n = profile.index(1, 0, 0)
        assert n == pytest.approx(1.51)


class TestGRINMaterial:
    """Tests for GRIN materials."""
    
    def test_create_material(self):
        mat = create_grin_material('Test', 'radial', n0=1.5, g=0.1)
        assert mat.name == 'Test'
        assert mat.profile.n0 == 1.5
    
    def test_no_unsourced_predefined_materials(self):
        # Vendor GRIN parameters are not published in a form we can cite,
        # so no presets are shipped; materials are built from user data.
        assert GRIN_MATERIALS == {}


class TestGRINTracer:
    """Tests for GRIN ray tracing."""
    
    def test_trace_grin(self):
        profile = RadialGRIN(n0=1.5, g=0.1)
        ray = GRINRay(
            position=np.array([0.0, 0.0, 0.0]),
            direction=np.array([0.0, 0.0, 1.0])
        )
        path = trace_grin(ray, profile, 0.01, step_size=0.001)
        assert len(path) > 0
        assert path[-1].position[2] > 0  # Ray propagated forward
    
    def test_grin_lens_focus(self):
        profile = RadialGRIN(n0=1.5, g=0.5)
        z, r = grin_lens_focus(profile, 0.01, r0=0.001)
        assert len(z) > 0
        assert len(r) > 0
