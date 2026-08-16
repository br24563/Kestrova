"""
Tests for the optical materials module.

These tests verify the refractive index data and the Sellmeier
wavelength-dependent index calculations.
"""

import math
import pytest
from optics.materials import (
    REFRACTIVE_INDICES, SELLMEIER_COEFFICIENTS,
    refractive_index, refractive_index_sellmeier,
)


class TestRefractiveIndex:
    """Tests for the refractive_index function."""

    def test_air(self):
        """Air should have index 1.0."""
        assert refractive_index("air") == pytest.approx(1.0)

    def test_nbk7_reference(self):
        """N-BK7 at reference wavelength should return catalog value."""
        assert refractive_index("N-BK7") == pytest.approx(1.5168)

    def test_unknown_material_raises(self):
        """Unknown material should raise ValueError."""
        with pytest.raises(ValueError):
            refractive_index("BogusGlass")

    def test_wavelength_dependent_nbk7(self):
        """N-BK7 index should differ at a non-reference wavelength."""
        n_blue = refractive_index("N-BK7", 486.1e-9)  # F line (blue)
        n_red = refractive_index("N-BK7", 656.3e-9)   # C line (red)
        # Normal dispersion: blue has higher index than red
        assert n_blue > n_red
        # Both should be close to the reference value
        assert abs(n_blue - 1.5168) < 0.05
        assert abs(n_red - 1.5168) < 0.05

    def test_material_without_sellmeier_uses_reference(self):
        """Materials without Sellmeier coefficients use the reference index."""
        # N-SF2 has no Sellmeier coefficients in the data
        assert refractive_index("N-SF2", 486.1e-9) == pytest.approx(1.6477)


class TestRefractiveIndexSellmeier:
    """Tests for the refractive_index_sellmeier function."""

    def test_nbk7_at_reference(self):
        """Sellmeier at 587.6nm should be close to the catalog value."""
        n = refractive_index_sellmeier("N-BK7", 587.6e-9)
        assert n == pytest.approx(1.5168, abs=0.01)

    def test_fused_silica_at_reference(self):
        """Fused silica Sellmeier at 587.6nm should be close to catalog."""
        n = refractive_index_sellmeier("FusedSilica", 587.6e-9)
        assert n == pytest.approx(1.4585, abs=0.01)

    def test_unknown_material_raises(self):
        """Material without Sellmeier coefficients should raise ValueError."""
        with pytest.raises(ValueError):
            refractive_index_sellmeier("N-SF2", 587.6e-9)

    def test_dispersion_direction(self):
        """Index should decrease with increasing wavelength (normal dispersion)."""
        n_blue = refractive_index_sellmeier("N-BK7", 486.1e-9)
        n_red = refractive_index_sellmeier("N-BK7", 656.3e-9)
        assert n_blue > n_red

    def test_all_sellmeier_materials_have_reference_index(self):
        """Every material with Sellmeier coefficients should have a reference index."""
        for material in SELLMEIER_COEFFICIENTS:
            assert material in REFRACTIVE_INDICES