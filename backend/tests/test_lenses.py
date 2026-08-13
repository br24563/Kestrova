"""
Tests for thin lens calculations.

These tests verify the fundamental thin lens equations against
known physical cases. All values are in SI base units (meters).

Sign convention (optics):
    - Object distance (s): NEGATIVE if object is to the LEFT of the lens.
    - Image distance (s'): NEGATIVE if image is to the LEFT of the lens.
    - Image distance (s'): POSITIVE if image is to the RIGHT of the lens.
"""

import math
import pytest
import numpy as np
from optics.lenses import (
    image_distance, object_distance, focal_length,
    magnification, magnification_from_f,
    two_lens_effective_focal_length, two_lens_back_focal_length,
    two_lens_front_focal_length, two_lens_system_image,
    RayVector, propagation_matrix, thin_lens_matrix,
    apply_matrix, system_matrix,
    f_number, numerical_aperture, half_angle_from_na,
)


# ---------------------------------------------------------------------------
# Thin Lens Equation: 1/f = 1/s' - 1/s
# ---------------------------------------------------------------------------

class TestImageDistance:
    """Tests for the image_distance function."""

    def test_object_at_2f_produces_image_at_2f(self):
        """Object at 2f to the left should produce image at 2f to the right."""
        f = 0.050  # 50 mm
        s = -0.100  # -100 mm = -2f (object to the left)
        s_prime = image_distance(f, s)
        assert s_prime == pytest.approx(0.100, rel=1e-10)

    def test_object_at_infinity_produces_image_at_focal_plane(self):
        """Object at infinity should produce image at the focal plane."""
        f = 0.050  # 50 mm
        s = float('-inf')
        s_prime = image_distance(f, s)
        assert s_prime == pytest.approx(0.050, rel=1e-10)

    def test_object_at_f_produces_image_at_infinity(self):
        """Object at focal point to the left should produce image at infinity."""
        f = 0.050  # 50 mm
        s = -0.050  # -f (object at focal point to the left)
        with pytest.raises(ValueError, match="infinity"):
            image_distance(f, s)

    def test_object_inside_f_produces_virtual_image(self):
        """Object inside focal length should produce a virtual image."""
        f = 0.050  # 50 mm
        s = -0.025  # -f/2 (object between lens and focal point)
        s_prime = image_distance(f, s)
        assert s_prime < 0  # Virtual image (to the left, negative)
        assert s_prime == pytest.approx(-0.050, rel=1e-10)

    def test_diverging_lens(self):
        """Diverging lens (f < 0) should produce virtual image."""
        f = -0.050  # -50 mm
        s = -0.100  # -100 mm (object to the left)
        s_prime = image_distance(f, s)
        assert s_prime < 0  # Virtual image (to the left)
        assert s_prime == pytest.approx(-0.033333, rel=1e-4)

    def test_object_at_3f_produces_image_at_1_5f(self):
        """Object at 3f to the left should produce image at 1.5f to the right."""
        f = 0.050  # 50 mm
        s = -0.150  # -150 mm = -3f (object to the left)
        s_prime = image_distance(f, s)
        assert s_prime == pytest.approx(0.075, rel=1e-10)  # 1.5f


class TestObjectDistance:
    """Tests for the object_distance function."""

    def test_image_at_2f_produces_object_at_2f(self):
        """Image at 2f to the right => object at 2f to the left."""
        f = 0.050
        s_prime = 0.100
        s = object_distance(f, s_prime)
        assert s == pytest.approx(-0.100, rel=1e-10)

    def test_image_at_f_produces_object_at_infinity(self):
        """Image at focal point => object at infinity."""
        f = 0.050
        s_prime = 0.050
        with pytest.raises(ValueError, match="infinity"):
            object_distance(f, s_prime)


class TestFocalLength:
    """Tests for the focal_length function."""

    def test_focal_length_from_2f_distances(self):
        """Object at 2f to the left, image at 2f to the right => f = s/2."""
        s = -0.100
        s_prime = 0.100
        f = focal_length(s, s_prime)
        assert f == pytest.approx(0.050, rel=1e-10)

    def test_focal_length_from_3f_and_1_5f(self):
        """Object at 3f to the left, image at 1.5f to the right => f = 50mm."""
        s = -0.150
        s_prime = 0.075
        f = focal_length(s, s_prime)
        assert f == pytest.approx(0.050, rel=1e-10)


# ---------------------------------------------------------------------------
# Magnification
# ---------------------------------------------------------------------------

class TestMagnification:
    """Tests for magnification calculations."""

    def test_magnification_at_2f_is_negative_one(self):
        """Object at 2f to the left, image at 2f to the right => m = -1."""
        s = -0.100
        s_prime = 0.100
        m = magnification(s, s_prime)
        assert m == pytest.approx(-1.0, rel=1e-10)

    def test_magnification_sign_is_negative_for_real_image(self):
        """Real image should have negative magnification (inverted)."""
        f = 0.050
        s = -0.100  # -2f (object to the left)
        s_prime = image_distance(f, s)
        m = magnification(s, s_prime)
        assert m < 0

    def test_magnification_sign_is_positive_for_virtual_image(self):
        """Virtual image (object inside f) should have positive magnification."""
        f = 0.050
        s = -0.025  # -f/2 (object between lens and focal point)
        s_prime = image_distance(f, s)
        m = magnification(s, s_prime)
        assert m > 0

    def test_magnification_from_f_at_2f(self):
        """Object at 2f to the left => m = -1."""
        f = 0.050
        s = -0.100
        m = magnification_from_f(f, s)
        assert m == pytest.approx(-1.0, rel=1e-10)

    def test_magnification_at_3f(self):
        """Object at 3f to the left => m = -0.5 (inverted, half size)."""
        f = 0.050
        s = -0.150  # -3f (object to the left)
        s_prime = image_distance(f, s)
        m = magnification(s, s_prime)
        assert m == pytest.approx(-0.5, rel=1e-10)


# ---------------------------------------------------------------------------
# Two-Lens System
# ---------------------------------------------------------------------------

class TestTwoLensSystem:
    """Tests for two-lens system calculations."""

    def test_two_lenses_touching(self):
        """Two 50mm lenses touching => f_eff = 25mm."""
        f1 = 0.050
        f2 = 0.050
        d = 0.0
        f_eff = two_lens_effective_focal_length(f1, f2, d)
        assert f_eff == pytest.approx(0.025, rel=1e-10)

    def test_two_lenses_separated_by_f(self):
        """Two 50mm lenses separated by 50mm => f_eff = 50mm (telescope)."""
        f1 = 0.050
        f2 = 0.050
        d = 0.050
        f_eff = two_lens_effective_focal_length(f1, f2, d)
        assert f_eff == pytest.approx(0.050, rel=1e-10)

    def test_two_lenses_separated_by_2f(self):
        """Two 50mm lenses separated by 100mm => f_eff = infinity (afocal)."""
        f1 = 0.050
        f2 = 0.050
        d = 0.100
        with pytest.raises(ValueError, match="afocal"):
            two_lens_effective_focal_length(f1, f2, d)

    def test_back_focal_length_single_lens(self):
        """Back focal length of a single lens equals its focal length."""
        f1 = 0.050
        f2 = 0.050
        d = 0.0
        bfl = two_lens_back_focal_length(f1, f2, d)
        assert bfl == pytest.approx(0.025, rel=1e-10)

    def test_front_focal_length_single_lens(self):
        """Front focal length of a single lens equals its focal length."""
        f1 = 0.050
        f2 = 0.050
        d = 0.0
        ffl = two_lens_front_focal_length(f1, f2, d)
        assert ffl == pytest.approx(0.025, rel=1e-10)

    def test_two_lens_system_image(self):
        """Test image formation in a two-lens system."""
        f1 = 0.050
        f2 = 0.050
        d = 0.050  # 50mm apart
        s = -0.100  # Object at 100mm to the left of first lens
        s_prime, m = two_lens_system_image(f1, f2, d, s)
        # Image should be at 25mm from second lens
        # (object at 2f of lens 1 => image at 2f, which is 50mm past lens 2,
        #  so virtual object for lens 2 at +50mm, image at 25mm)
        assert s_prime == pytest.approx(0.025, rel=1e-10)
        # Magnification: m1=-1, m2=0.5, m_total=-0.5
        assert m == pytest.approx(-0.5, rel=1e-10)


# ---------------------------------------------------------------------------
# Ray Transfer Matrix (ABCD Matrix) Method
# ---------------------------------------------------------------------------

class TestRayTransferMatrix:
    """Tests for the ABCD matrix method."""

    def test_propagation_matrix(self):
        """Propagation matrix should be [[1, d], [0, 1]]."""
        d = 0.1
        M = propagation_matrix(d)
        assert M[0, 0] == pytest.approx(1.0)
        assert M[0, 1] == pytest.approx(d)
        assert M[1, 0] == pytest.approx(0.0)
        assert M[1, 1] == pytest.approx(1.0)

    def test_thin_lens_matrix(self):
        """Thin lens matrix should be [[1, 0], [-1/f, 1]]."""
        f = 0.050
        M = thin_lens_matrix(f)
        assert M[0, 0] == pytest.approx(1.0)
        assert M[0, 1] == pytest.approx(0.0)
        assert M[1, 0] == pytest.approx(-1.0 / f)
        assert M[1, 1] == pytest.approx(1.0)

    def test_apply_matrix_propagation(self):
        """Applying propagation matrix should shift ray height."""
        d = 0.1
        ray = RayVector(y=0.0, theta=0.01)
        M = propagation_matrix(d)
        result = apply_matrix(M, ray)
        assert result.y == pytest.approx(0.001, rel=1e-10)  # 0 + 0.1 * 0.01
        assert result.theta == pytest.approx(0.01, rel=1e-10)

    def test_apply_matrix_thin_lens(self):
        """Applying thin lens matrix should change ray angle."""
        f = 0.050
        ray = RayVector(y=0.01, theta=0.0)
        M = thin_lens_matrix(f)
        result = apply_matrix(M, ray)
        assert result.y == pytest.approx(0.01, rel=1e-10)  # Height unchanged
        assert result.theta == pytest.approx(-0.2, rel=1e-10)  # 0 - 0.01/0.05

    def test_system_matrix_single_lens(self):
        """System matrix for a single lens should match the lens matrix."""
        f = 0.050
        M = system_matrix([thin_lens_matrix(f)])
        assert M[1, 0] == pytest.approx(-1.0 / f, rel=1e-10)

    def test_system_matrix_two_lenses(self):
        """System matrix for two lenses should give correct EFL."""
        f1 = 0.050
        f2 = 0.050
        d = 0.0
        M = system_matrix([
            thin_lens_matrix(f1),
            propagation_matrix(d),
            thin_lens_matrix(f2),
        ])
        # EFL = -1 / M[1,0]
        efl = -1.0 / M[1, 0]
        assert efl == pytest.approx(0.025, rel=1e-10)

    def test_parallel_ray_through_lens(self):
        """A parallel ray (theta=0) should converge at the focal point."""
        f = 0.050
        # Ray at height 0.01, angle 0 (parallel to axis)
        ray = RayVector(y=0.01, theta=0.0)
        # Apply lens
        ray = apply_matrix(thin_lens_matrix(f), ray)
        # Propagate to focal point (distance = f)
        ray = apply_matrix(propagation_matrix(f), ray)
        # Ray should be at height 0 (converged to axis)
        assert ray.y == pytest.approx(0.0, abs=1e-10)

    def test_ray_through_center_of_lens(self):
        """A ray through the center of a lens should not change angle."""
        f = 0.050
        # Ray at height 0 (through center), angle 0.01
        ray = RayVector(y=0.0, theta=0.01)
        ray = apply_matrix(thin_lens_matrix(f), ray)
        # Angle should be unchanged (y=0 => no angle change)
        assert ray.theta == pytest.approx(0.01, rel=1e-10)


# ---------------------------------------------------------------------------
# F-number and Numerical Aperture
# ---------------------------------------------------------------------------

class TestFOnumber:
    """Tests for F-number calculations."""

    def test_f_number_basic(self):
        """F/2 lens: f=50mm, D=25mm."""
        f = 0.050
        d = 0.025
        assert f_number(f, d) == pytest.approx(2.0)

    def test_f_number_f1_4(self):
        """F/1.4 lens: f=50mm, D≈35.7mm."""
        f = 0.050
        d = 0.050 / 1.4
        assert f_number(f, d) == pytest.approx(1.4, rel=1e-4)

    def test_f_number_zero_aperture(self):
        """Zero aperture should raise an error."""
        with pytest.raises(ValueError):
            f_number(0.050, 0.0)


class TestNumericalAperture:
    """Tests for numerical aperture calculations."""

    def test_na_air_30_degrees(self):
        """NA = n * sin(theta) = 1 * sin(30°) = 0.5."""
        n = 1.0
        theta = math.radians(30)
        assert numerical_aperture(n, theta) == pytest.approx(0.5, rel=1e-10)

    def test_na_air_0_degrees(self):
        """NA at 0 degrees should be 0."""
        assert numerical_aperture(1.0, 0.0) == pytest.approx(0.0)

    def test_na_air_90_degrees(self):
        """NA at 90 degrees should be 1 (in air)."""
        assert numerical_aperture(1.0, math.radians(90)) == pytest.approx(1.0)

    def test_half_angle_from_na(self):
        """Half angle from NA=0.5 in air should be 30 degrees."""
        theta = half_angle_from_na(0.5, 1.0)
        assert theta == pytest.approx(math.radians(30), rel=1e-10)