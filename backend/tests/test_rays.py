"""
Tests for the ray tracing engine.

These tests verify that rays are traced correctly through optical
systems, and that the paraxial image position and spot diagram
calculations are accurate.
"""

import math
import pytest
from optics.models import (
    OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings,
)
from optics.rays import (
    propagate, refract_at_thin_lens,
    generate_rays, trace_ray, trace_system,
    calculate_paraxial_image_position, calculate_paraxial_image_height,
    calculate_spot_diagram,
)
from optics.systems import create_default_system


# ---------------------------------------------------------------------------
# Ray Propagation
# ---------------------------------------------------------------------------

class TestPropagate:
    """Tests for the propagate function."""

    def test_propagate_zero_distance(self):
        """Propagating zero distance should not change the ray."""
        y, theta = propagate(0.01, 0.01, 0.0)
        assert y == pytest.approx(0.01)
        assert theta == pytest.approx(0.01)

    def test_propagate_positive_distance(self):
        """Propagating should shift the ray height."""
        y, theta = propagate(0.0, 0.01, 0.1)
        assert y == pytest.approx(0.001)  # 0 + 0.1 * 0.01
        assert theta == pytest.approx(0.01)

    def test_propagate_negative_angle(self):
        """Negative angle should decrease ray height."""
        y, theta = propagate(0.01, -0.01, 0.1)
        assert y == pytest.approx(0.009)  # 0.01 - 0.1 * 0.01 = 0.009
        assert theta == pytest.approx(-0.01)


class TestRefractAtThinLens:
    """Tests for the refract_at_thin_lens function."""

    def test_refract_parallel_ray(self):
        """A parallel ray should bend toward the focal point."""
        y, theta = refract_at_thin_lens(0.01, 0.0, 0.050)
        assert y == pytest.approx(0.01)  # Height unchanged
        assert theta == pytest.approx(-0.2)  # 0 - 0.01/0.05

    def test_refract_ray_through_center(self):
        """A ray through the center (y=0) should not change angle."""
        y, theta = refract_at_thin_lens(0.0, 0.01, 0.050)
        assert y == pytest.approx(0.0)
        assert theta == pytest.approx(0.01)

    def test_refract_diverging_lens(self):
        """A diverging lens should bend rays away from the axis."""
        y, theta = refract_at_thin_lens(0.01, 0.0, -0.050)
        assert theta == pytest.approx(0.2)  # 0 - 0.01/(-0.05) = +0.2


# ---------------------------------------------------------------------------
# Ray Generation
# ---------------------------------------------------------------------------

class TestGenerateRays:
    """Tests for ray generation."""

    def test_generate_rays_count(self):
        """Should generate the correct number of rays."""
        system = create_default_system()
        rays = generate_rays(system, num_rays=11)
        assert len(rays) == 11

    def test_generate_rays_has_chief_ray(self):
        """Should include a chief ray (through center of aperture)."""
        system = create_default_system()
        rays = generate_rays(system, num_rays=11)
        chief_rays = [r for r in rays if r.ray_type == "chief"]
        assert len(chief_rays) == 1

    def test_generate_rays_has_marginal_rays(self):
        """Should include marginal rays (at edge of aperture)."""
        system = create_default_system()
        rays = generate_rays(system, num_rays=11)
        marginal_rays = [r for r in rays if r.ray_type == "marginal"]
        assert len(marginal_rays) == 2  # Top and bottom

    def test_generate_rays_start_at_object(self):
        """All rays should start at the object position."""
        system = create_default_system()
        rays = generate_rays(system, num_rays=5)
        for ray in rays:
            assert ray.z == pytest.approx(system.object.position)
            assert ray.y == pytest.approx(system.object.height)


# ---------------------------------------------------------------------------
# Ray Tracing Through a System
# ---------------------------------------------------------------------------

class TestTraceRay:
    """Tests for tracing a single ray through a system."""

    def test_trace_ray_single_lens(self):
        """Trace a ray through a single lens system."""
        system = OpticalSystem(
            components=[
                ThinLens(
                    id="lens_1",
                    position=0.100,
                    focal_length=0.050,
                    aperture_diameter=0.025,
                ),
            ],
            object=Object(position=0.0, height=0.010),
            image_plane=ImagePlane(position=0.200),
            analysis_settings=AnalysisSettings(num_rays=1),
        )

        # Chief ray: from object (0, 0.01) through center of lens
        ray = generate_rays(system, num_rays=1)[0]
        path = trace_ray(system, ray)

        # Path should have at least 3 points: object, lens, image plane
        assert len(path.points) >= 3

        # First point should be at the object
        assert path.points[0][0] == pytest.approx(0.0)
        assert path.points[0][1] == pytest.approx(0.010)

        # Last point should be at the image plane
        assert path.points[-1][0] == pytest.approx(0.200)

    def test_trace_ray_parallel_ray_converges_at_focal_point(self):
        """A parallel ray should converge at the focal point after a lens."""
        f = 0.050
        system = OpticalSystem(
            components=[
                ThinLens(
                    id="lens_1",
                    position=0.100,
                    focal_length=f,
                    aperture_diameter=0.025,
                ),
            ],
            object=Object(position=0.0, height=0.0),
            image_plane=ImagePlane(position=0.100 + f),
            analysis_settings=AnalysisSettings(num_rays=1),
        )

        # Parallel ray at height 0.01
        from optics.models import Ray
        ray = Ray(y=0.01, theta=0.0, z=0.0, wavelength=550e-9, ray_type="fill")
        path = trace_ray(system, ray)

        # At the focal point (z = 0.150), the ray should be at height 0
        # Find the point closest to the focal plane
        focal_z = 0.100 + f
        for point in path.points:
            if abs(point[0] - focal_z) < 1e-10:
                assert point[1] == pytest.approx(0.0, abs=1e-10)


class TestTraceSystem:
    """Tests for tracing all rays through a system."""

    def test_trace_system_default(self):
        """Trace the default two-lens system."""
        system = create_default_system()
        result = trace_system(system, num_rays=11)

        assert len(result.ray_paths) == 11
        assert result.image_position > 0
        assert result.paraxial_image_height != 0

    def test_trace_system_image_position(self):
        """The calculated image position should match the paraxial formula."""
        system = create_default_system()
        result = trace_system(system, num_rays=11)

        # Calculate expected image position
        expected = calculate_paraxial_image_position(system)
        assert result.image_position == pytest.approx(expected, rel=1e-10)

    def test_trace_system_all_rays_converge(self):
        """For a paraxial system, all rays should converge to the same point."""
        system = create_default_system()
        result = trace_system(system, num_rays=11)

        # All rays should have the same final y (paraxial approximation)
        final_ys = [path.final_y for path in result.ray_paths]
        if len(final_ys) > 1:
            # All final y values should be approximately equal
            for y in final_ys[1:]:
                assert y == pytest.approx(final_ys[0], abs=1e-10)


class TestParaxialImage:
    """Tests for paraxial image position calculation."""

    def test_single_lens_image_position(self):
        """Image position for a single lens should match thin lens equation."""
        f = 0.050
        # Object at 2f to the left of the lens (s = -2f = -0.100)
        system = OpticalSystem(
            components=[
                ThinLens(
                    id="lens_1",
                    position=0.100,
                    focal_length=f,
                    aperture_diameter=0.025,
                ),
            ],
            object=Object(position=0.0, height=0.010),
            image_plane=ImagePlane(position=0.200),
            analysis_settings=AnalysisSettings(num_rays=1),
        )

        img_pos = calculate_paraxial_image_position(system)
        # Image should be at 0.100 + 0.100 = 0.200
        assert img_pos == pytest.approx(0.200, rel=1e-10)

    def test_single_lens_image_height(self):
        """Image height should match magnification * object height."""
        f = 0.050
        # Object at 2f to the left of the lens => m = -1
        system = OpticalSystem(
            components=[
                ThinLens(
                    id="lens_1",
                    position=0.100,
                    focal_length=f,
                    aperture_diameter=0.025,
                ),
            ],
            object=Object(position=0.0, height=0.010),
            image_plane=ImagePlane(position=0.200),
            analysis_settings=AnalysisSettings(num_rays=1),
        )

        img_height = calculate_paraxial_image_height(system)
        # m = -1, so image height = -0.010 (inverted)
        assert img_height == pytest.approx(-0.010, rel=1e-10)


class TestSpotDiagram:
    """Tests for spot diagram calculation."""

    def test_spot_diagram_perfect_system(self):
        """For a paraxial system, RMS spot radius should be ~0."""
        system = create_default_system()
        result = trace_system(system, num_rays=11)
        spot_heights, rms = calculate_spot_diagram(
            result.ray_paths, result.image_position
        )

        # All rays should converge to the same point (paraxial)
        assert rms == pytest.approx(0.0, abs=1e-10)

    def test_spot_diagram_symmetric_rays(self):
        """Symmetric rays should produce symmetric spot distributions."""
        system = create_default_system()
        result = trace_system(system, num_rays=11)
        spot_heights, rms = calculate_spot_diagram(
            result.ray_paths, result.image_position
        )

        # The spot heights should be symmetric around the mean
        mean_y = sum(spot_heights) / len(spot_heights)
        for y in spot_heights:
            # For a perfect paraxial system, all y should equal the mean
            assert y == pytest.approx(mean_y, abs=1e-10)
