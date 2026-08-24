"""
Tests for the Seidel (third-order) monochromatic aberration analysis.

These tests verify that the five monochromatic aberrations are computed
correctly for known optical systems using the exact real-ray tracer.
"""

import pytest
from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings,
)
from optics.seidel import (
    spherical_aberration, coma, astigmatism_and_field_curvature,
    distortion, seidel_analysis,
)


def make_single_lens_system(
    f: float = 0.050,
    aperture: float = 0.025,
    obj_pos: float = 0.0,
    obj_height: float = 0.010,
    lens_pos: float = 0.100,
    image_pos: float = 0.200,
) -> OpticalSystem:
    """Create a simple single thin-lens system for testing."""
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1",
                position=lens_pos,
                focal_length=f,
                aperture_diameter=aperture,
                material="N-BK7",
            ),
        ],
        object=Object(position=obj_pos, height=obj_height),
        image_plane=ImagePlane(position=image_pos),
        analysis_settings=AnalysisSettings(num_rays=11),
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


class TestSphericalAberration:
    """Tests for spherical aberration."""

    def test_single_lens_has_spherical_aberration(self):
        """A single biconvex lens should have nonzero spherical aberration."""
        system = make_single_lens_system()
        result = spherical_aberration(system)
        assert "longitudinal" in result
        assert "transverse" in result
        # A real lens has nonzero SA
        assert abs(result["longitudinal"]) > 1e-6
        assert abs(result["transverse"]) > 1e-6

    def test_no_lens_returns_zero(self):
        """A system with no lens should return zero SA."""
        system = OpticalSystem(
            components=[],
            object=Object(position=0.0, height=0.010),
            image_plane=ImagePlane(position=0.200),
            analysis_settings=AnalysisSettings(num_rays=11),
        )
        result = spherical_aberration(system)
        assert result["longitudinal"] == 0.0
        assert result["transverse"] == 0.0


class TestComa:
    """Tests for coma."""

    def test_off_axis_object_has_coma(self):
        """An off-axis object should produce nonzero coma."""
        system = make_single_lens_system(obj_height=0.010)
        value = coma(system)
        assert value != 0

    def test_on_axis_object_zero_coma(self):
        """An on-axis object should produce zero coma."""
        system = make_single_lens_system(obj_height=0.0)
        value = coma(system)
        assert value == pytest.approx(0.0, abs=1e-9)


class TestAstigmatismAndFieldCurvature:
    """Tests for astigmatism and field curvature."""

    def test_off_axis_has_astigmatism(self):
        """An off-axis object should produce nonzero astigmatism."""
        system = make_single_lens_system(obj_height=0.010)
        result = astigmatism_and_field_curvature(system)
        assert "astigmatism" in result
        assert "field_curvature" in result
        assert "tangential_focus" in result
        assert "sagittal_focus" in result
        assert result["astigmatism"] != 0

    def test_no_lens_returns_zero(self):
        """A system with no lens should return zero astigmatism."""
        system = OpticalSystem(
            components=[],
            object=Object(position=0.0, height=0.010),
            image_plane=ImagePlane(position=0.200),
            analysis_settings=AnalysisSettings(num_rays=11),
        )
        result = astigmatism_and_field_curvature(system)
        assert result["astigmatism"] == 0.0
        assert result["field_curvature"] == 0.0


class TestDistortion:
    """Tests for distortion."""

    def test_off_axis_has_distortion(self):
        """An off-axis object should produce nonzero distortion."""
        system = make_single_lens_system(obj_height=0.010)
        value = distortion(system)
        assert value != 0

    def test_on_axis_zero_distortion(self):
        """An on-axis object should produce zero distortion."""
        system = make_single_lens_system(obj_height=0.0)
        value = distortion(system)
        assert value == pytest.approx(0.0, abs=1e-9)


class TestSeidelAnalysis:
    """Tests for the full Seidel analysis."""

    def test_full_analysis_returns_all_fields(self):
        """seidel_analysis should return all five aberrations."""
        system = make_single_lens_system()
        result = seidel_analysis(system)

        assert "spherical_aberration" in result
        assert "coma" in result
        assert "astigmatism" in result
        assert "field_curvature" in result
        assert "distortion" in result
        assert "paraxial_image_position" in result
        assert "paraxial_image_height" in result

    def test_thick_lens_analysis(self):
        """Seidel analysis should work for thick lenses too."""
        system = make_thick_lens_system()
        result = seidel_analysis(system)
        assert "spherical_aberration" in result
        assert "coma" in result
        assert "astigmatism" in result
        assert "field_curvature" in result
        assert "distortion" in result