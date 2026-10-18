"""
Tests for the optical analysis module.

These tests verify that the analysis calculations (effective focal
length, magnification, F-number, numerical aperture, etc.) produce
correct results for known optical systems.
"""

import math
import pytest
from optics.models import (
    OpticalSystem, ThinLens, Object, ImagePlane, AnalysisSettings,
)
from optics.analysis import (
    build_system_matrix, effective_focal_length,
    back_focal_length, front_focal_length,
    system_magnification, object_distance, image_distance,
    working_distance, system_f_number, system_numerical_aperture,
    analyze_system,
)
from optics.systems import create_default_system


# ---------------------------------------------------------------------------
# Helper to create test systems
# ---------------------------------------------------------------------------

def make_single_lens_system(
    f: float = 0.050,
    aperture: float = 0.025,
    obj_pos: float = 0.0,
    obj_height: float = 0.010,
    lens_pos: float = 0.100,
    image_pos: float = 0.200,
) -> OpticalSystem:
    """Create a simple single-lens system for testing."""
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1",
                position=lens_pos,
                focal_length=f,
                aperture_diameter=aperture,
            ),
        ],
        object=Object(position=obj_pos, height=obj_height),
        image_plane=ImagePlane(position=image_pos),
        analysis_settings=AnalysisSettings(num_rays=11),
    )


def make_two_lens_system(
    f1: float = 0.050,
    f2: float = 0.050,
    d: float = 0.050,
    aperture: float = 0.025,
    obj_pos: float = 0.0,
    obj_height: float = 0.010,
    lens1_pos: float = 0.100,
    lens2_pos: float = 0.150,
    image_pos: float = 0.200,
) -> OpticalSystem:
    """Create a simple two-lens system for testing."""
    return OpticalSystem(
        components=[
            ThinLens(
                id="lens_1",
                position=lens1_pos,
                focal_length=f1,
                aperture_diameter=aperture,
            ),
            ThinLens(
                id="lens_2",
                position=lens2_pos,
                focal_length=f2,
                aperture_diameter=aperture,
            ),
        ],
        object=Object(position=obj_pos, height=obj_height),
        image_plane=ImagePlane(position=image_pos),
        analysis_settings=AnalysisSettings(num_rays=11),
    )


# ---------------------------------------------------------------------------
# Effective Focal Length
# ---------------------------------------------------------------------------

class TestEffectiveFocalLength:
    """Tests for effective focal length calculation."""

    def test_single_lens_efl(self):
        """EFL of a single lens should equal its focal length."""
        system = make_single_lens_system(f=0.050)
        efl = effective_focal_length(system)
        assert efl == pytest.approx(0.050, rel=1e-10)

    def test_two_lenses_touching(self):
        """Two 50mm lenses touching => EFL = 25mm."""
        system = make_two_lens_system(f1=0.050, f2=0.050, d=0.050,
                                       lens1_pos=0.100, lens2_pos=0.100)
        efl = effective_focal_length(system)
        assert efl == pytest.approx(0.025, rel=1e-10)

    def test_two_lenses_separated_by_f(self):
        """Two 50mm lenses separated by 50mm => EFL = 50mm."""
        system = make_two_lens_system(f1=0.050, f2=0.050, d=0.050)
        efl = effective_focal_length(system)
        assert efl == pytest.approx(0.050, rel=1e-10)

    def test_system_matrix_single_lens(self):
        """System matrix for a single lens should have C = -1/f."""
        system = make_single_lens_system(f=0.050)
        M = build_system_matrix(system)
        assert M[1, 0] == pytest.approx(-1.0 / 0.050, rel=1e-10)


# ---------------------------------------------------------------------------
# Magnification
# ---------------------------------------------------------------------------

class TestMagnification:
    """Tests for magnification calculation."""

    def test_magnification_at_2f(self):
        """Object at 2f => m = -1 (inverted, same size)."""
        system = make_single_lens_system(
            f=0.050, obj_pos=0.0, lens_pos=0.100,
        )
        m = system_magnification(system)
        assert m == pytest.approx(-1.0, rel=1e-10)

    def test_magnification_at_3f(self):
        """Object at 3f => m = -0.5 (inverted, half size)."""
        system = make_single_lens_system(
            f=0.050, obj_pos=0.0, lens_pos=0.150,
        )
        m = system_magnification(system)
        assert m == pytest.approx(-0.5, rel=1e-10)

    def test_magnification_sign(self):
        """Real image should have negative magnification."""
        system = make_single_lens_system(f=0.050, obj_pos=0.0, lens_pos=0.100)
        m = system_magnification(system)
        assert m < 0


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------

class TestDistances:
    """Tests for distance calculations."""

    def test_object_distance(self):
        """Object distance should be negative when object is to the left."""
        system = make_single_lens_system(
            f=0.050, obj_pos=0.0, lens_pos=0.100,
        )
        s = object_distance(system)
        # Object is to the LEFT of the lens => s < 0 (optics convention)
        assert s == pytest.approx(-0.100, rel=1e-10)

    def test_image_distance(self):
        """Image distance should be image_pos - lens_pos."""
        system = make_single_lens_system(
            f=0.050, obj_pos=0.0, lens_pos=0.100, image_pos=0.200,
        )
        s_prime = image_distance(system)
        assert s_prime == pytest.approx(0.100, rel=1e-10)

    def test_working_distance(self):
        """Working distance should be image_plane_pos - last_lens_pos."""
        system = make_single_lens_system(
            f=0.050, obj_pos=0.0, lens_pos=0.100, image_pos=0.200,
        )
        wd = working_distance(system)
        assert wd == pytest.approx(0.100, rel=1e-10)


# ---------------------------------------------------------------------------
# F-number and Numerical Aperture
# ---------------------------------------------------------------------------

class TestFOnumber:
    """Tests for F-number calculation."""

    def test_f_number_single_lens(self):
        """F/2 lens: f=50mm, D=25mm."""
        system = make_single_lens_system(f=0.050, aperture=0.025)
        fn = system_f_number(system)
        assert fn == pytest.approx(2.0, rel=1e-10)

    def test_f_number_two_lenses(self):
        """F-number uses EFL and first lens aperture."""
        system = make_two_lens_system(
            f1=0.050, f2=0.050, d=0.050, aperture=0.025,
        )
        fn = system_f_number(system)
        # EFL = 50mm, D = 25mm => F/2
        assert fn == pytest.approx(2.0, rel=1e-10)


class TestNumericalAperture:
    """Tests for numerical aperture calculation."""

    def test_na_basic(self):
        """NA should be n * sin(theta) where theta = arctan(D/2 / s)."""
        system = make_single_lens_system(
            f=0.050, aperture=0.025, obj_pos=0.0, lens_pos=0.100,
        )
        na = system_numerical_aperture(system)
        # s = 0.100, D = 0.025
        # theta = arctan(0.0125 / 0.100) = arctan(0.125)
        expected_theta = math.atan(0.0125 / 0.100)
        expected_na = 1.0 * math.sin(expected_theta)
        assert na == pytest.approx(expected_na, rel=1e-10)


# ---------------------------------------------------------------------------
# Full Analysis
# ---------------------------------------------------------------------------

class TestAnalyzeSystem:
    """Tests for the full analysis function."""

    def test_analyze_single_lens(self):
        """Full analysis of a single lens system."""
        system = make_single_lens_system(
            f=0.050, aperture=0.025, obj_pos=0.0, obj_height=0.010,
            lens_pos=0.100, image_pos=0.200,
        )
        result = analyze_system(system, num_rays=11)

        assert result.effective_focal_length == pytest.approx(0.050, rel=1e-10)
        assert result.magnification == pytest.approx(-1.0, rel=1e-10)
        # Object is to the LEFT of the lens => s < 0 (optics convention)
        assert result.object_distance == pytest.approx(-0.100, rel=1e-10)
        assert result.image_distance == pytest.approx(0.100, rel=1e-10)
        assert result.f_number == pytest.approx(2.0, rel=1e-10)
        assert result.aperture_diameter == pytest.approx(0.025, rel=1e-10)
        assert result.is_image_real is True
        assert result.is_image_inverted is True

    def test_analyze_two_lens_default(self):
        """Full analysis of the default two-lens system."""
        system = create_default_system()
        result = analyze_system(system, num_rays=11)

        # EFL should be 50mm (two 50mm lenses, 50mm apart)
        assert result.effective_focal_length == pytest.approx(0.050, rel=1e-10)
        # Magnification should be -0.5 (object at 2f of first lens,
        #  image from lens 1 at 2f becomes virtual object for lens 2)
        assert result.magnification == pytest.approx(-0.5, rel=1e-10)
        assert result.is_image_real is True
        assert result.is_image_inverted is True

    def test_analyze_returns_spot_points(self):
        """Analysis should return spot diagram points."""
        system = create_default_system()
        result = analyze_system(system, num_rays=11)
        # one 2D point per ray of an 11 x 11 pupil grid inside the unit circle
        g = [-1 + 0.2 * k for k in range(11)]
        expected = sum(1 for x in g for y in g if x * x + y * y <= 1 + 1e-12)
        assert len(result.spot_points) == expected
        assert all(len(p) == 2 for p in result.spot_points)

    def test_analyze_rms_spot_near_zero(self):
        """For a paraxial system, RMS spot radius should be ~0."""
        system = create_default_system()
        result = analyze_system(system, num_rays=11)
        assert result.rms_spot_radius == pytest.approx(0.0, abs=1e-10)
