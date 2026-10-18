"""
Tests for the chromatic aberration analysis module.

These tests verify that chromatic aberration is correctly computed
for systems with wavelength-dependent refractive index.
"""

import pytest
from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings,
)
from optics.aberration import (
    F_LINE, D_LINE, C_LINE,
    image_position_at_wavelength, image_height_at_wavelength,
    longitudinal_chromatic_aberration, lateral_chromatic_aberration,
    chromatic_aberration_analysis,
)


def make_thick_lens_system() -> OpticalSystem:
    """Create a single thick lens system for testing."""
    return OpticalSystem(
        components=[
            ThickLens(
                id="lens_1",
                position=0.100,
                radius1=0.100,
                radius2=-0.100,
                thickness=0.010,
                aperture_diameter=0.025,
                material="N-BK7",
            ),
        ],
        object=Object(position=0.0, height=0.010),
        image_plane=ImagePlane(position=0.250),
        analysis_settings=AnalysisSettings(num_rays=11),
    )


class TestImageAtWavelength:
    """Tests for image position/height at a specific wavelength."""

    def test_image_position_at_d_line(self):
        """Image position at d-line should be computable."""
        system = make_thick_lens_system()
        pos = image_position_at_wavelength(system, D_LINE)
        assert pos > 0.100  # Image to the right of the lens

    def test_image_height_at_d_line(self):
        """Image height at d-line should be computable."""
        system = make_thick_lens_system()
        height = image_height_at_wavelength(system, D_LINE)
        assert height != 0


class TestChromaticAberration:
    """Tests for chromatic aberration calculations."""

    def test_longitudinal_aberration_positive(self):
        """Blue should focus closer than red (normal dispersion)."""
        system = make_thick_lens_system()
        lca = longitudinal_chromatic_aberration(system)
        # Blue (higher index) => shorter focal length => image closer to lens
        assert lca < 0

    def test_lateral_aberration_nonzero(self):
        """Different wavelengths should produce different image heights."""
        system = make_thick_lens_system()
        tca = lateral_chromatic_aberration(system)
        assert tca != 0

    def test_full_analysis(self):
        """Full chromatic aberration analysis should return all fields."""
        system = make_thick_lens_system()
        result = chromatic_aberration_analysis(system)

        assert len(result["wavelengths"]) == 3
        assert len(result["image_positions"]) == 3
        assert len(result["image_heights"]) == 3
        assert "lca" in result
        assert "tca" in result

    def test_custom_wavelengths(self):
        """Custom wavelength list should be respected."""
        system = make_thick_lens_system()
        wavelengths = [450e-9, 550e-9, 650e-9]
        result = chromatic_aberration_analysis(system, wavelengths)
        assert result["wavelengths"] == wavelengths
        assert len(result["image_positions"]) == 3

    def test_thin_lens_chromatic_aberration(self):
        """A thin lens should have non-zero chromatic aberration."""
        system = OpticalSystem(
            components=[
                ThinLens(
                    id="lens_1",
                    position=0.100,
                    focal_length=0.050,
                    aperture_diameter=0.025,
                    material="N-BK7",
                ),
            ],
            wavelengths=[486.1e-9, 587.6e-9, 656.3e-9],
            object=Object(position=0.0, height=0.010),
            image_plane=ImagePlane(position=0.200),
            analysis_settings=AnalysisSettings(num_rays=11, ray_types=["chief","marginal","fill"], aperture_fraction=1.0, wavelength=587.6e-9),
        )
        lca = longitudinal_chromatic_aberration(system)
        # N-BK7 has dispersion: chromatic aberration should be non-zero
        assert lca != 0.0, "Thin lens should have chromatic aberration"
        assert abs(lca) < 0.01, f"LCA should be small but non-zero, got {lca}"