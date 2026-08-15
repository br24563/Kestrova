"""
Tests for the spherical surface and thick lens calculations.

These tests verify the lensmaker's equation and thick lens ray tracing.
"""

import pytest
from optics.models import (
    OpticalSystem, ThickLens, Object, ImagePlane, AnalysisSettings,
)
from optics.surfaces import (
    spherical_surface_power, spherical_surface_image_distance,
    spherical_surface_refract, lensmaker_focal_length,
)
from optics.rays import (
    generate_rays, trace_ray,
    calculate_paraxial_image_position,
)
from optics.analysis import effective_focal_length, analyze_system


class TestSphericalSurfacePower:
    """Tests for spherical_surface_power."""

    def test_air_to_glass_convex(self):
        """Air to glass, R=100mm => power = 5 diopters."""
        power = spherical_surface_power(0.1, 1.0, 1.5)
        assert power == pytest.approx(5.0)

    def test_air_to_glass_concave(self):
        """Air to glass, R=-100mm => power = -5 diopters."""
        power = spherical_surface_power(-0.1, 1.0, 1.5)
        assert power == pytest.approx(-5.0)

    def test_zero_radius_raises(self):
        """Zero radius should raise ValueError."""
        with pytest.raises(ValueError):
            spherical_surface_power(0.0, 1.0, 1.5)


class TestSphericalSurfaceImageDistance:
    """Tests for spherical_surface_image_distance."""

    def test_air_to_glass(self):
        """Air to glass, R=100mm, object at 300mm => image at 900mm."""
        # inv_s' = (1.5-1.0)/0.1 - 1.0/0.3 = 5.0 - 3.333 = 1.667
        # s' = n2 / inv_s' = 1.5 / 1.667 = 0.9
        s_prime = spherical_surface_image_distance(0.1, 1.0, 1.5, 0.3)
        assert s_prime == pytest.approx(0.9, rel=1e-9)


class TestSphericalSurfaceRefract:
    """Tests for spherical_surface_refract."""

    def test_flat_surface(self):
        """Flat surface (R=inf) should only change angle by index ratio."""
        y, theta = spherical_surface_refract(0.01, 0.02, 1e15, 1.0, 1.5)
        assert y == pytest.approx(0.01)
        assert theta == pytest.approx(0.02 * (1.0 / 1.5))


class TestLensmakerFocalLength:
    """Tests for lensmaker_focal_length."""

    def test_symmetric_biconvex(self):
        """Symmetric biconvex lens: R1=100mm, R2=-100mm, t=10mm, n=1.5."""
        f = lensmaker_focal_length(0.1, -0.1, 0.01, 1.5)
        assert f == pytest.approx(0.1017, rel=1e-3)

    def test_thin_lens_limit(self):
        """As thickness -> 0, thick lens approaches thin lens formula."""
        f_thick = lensmaker_focal_length(0.1, -0.1, 1e-6, 1.5)
        assert f_thick == pytest.approx(0.1, rel=1e-3)

    def test_zero_radii_raises(self):
        """Both radii zero should raise ValueError."""
        with pytest.raises(ValueError):
            lensmaker_focal_length(0.0, 0.0, 0.01, 1.5)


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


class TestThickLensTracing:
    """Tests for tracing rays through a thick lens."""

    def test_trace_ray_thick_lens(self):
        """A ray should refract at both surfaces of a thick lens."""
        system = make_thick_lens_system()
        ray = generate_rays(system, num_rays=1)[0]
        path = trace_ray(system, ray)

        assert len(path.points) >= 4
        assert path.points[0][0] == pytest.approx(0.0)
        assert path.points[-1][0] == pytest.approx(0.250)

    def test_thick_lens_effective_focal_length(self):
        """The EFL of a thick lens should match the lensmaker's equation."""
        system = make_thick_lens_system()
        f_eff = effective_focal_length(system)
        expected = lensmaker_focal_length(0.1, -0.1, 0.01, 1.5168)
        assert f_eff == pytest.approx(expected, rel=1e-6)

    def test_thick_lens_paraxial_image_position(self):
        """The paraxial image position should be computable."""
        system = make_thick_lens_system()
        img_pos = calculate_paraxial_image_position(system)
        assert img_pos > 0.100

    def test_thick_lens_analysis(self):
        """Full analysis should work with a thick lens."""
        system = make_thick_lens_system()
        result = analyze_system(system)
        assert result.effective_focal_length > 0
        assert result.magnification != 0