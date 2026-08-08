"""
Tests for the unit handling system.

These tests verify that unit conversions are correct and consistent.
"""

import math
import pytest
from optics.units import (
    Quantity, to_meters, from_meters, to_radians, from_radians,
    convert, is_length_unit, is_angle_unit,
    LENGTH_UNITS, ANGLE_UNITS,
)


class TestLengthConversions:
    """Tests for length unit conversions."""

    def test_mm_to_meters(self):
        assert to_meters(5, "mm") == pytest.approx(0.005)

    def test_meters_to_mm(self):
        assert from_meters(0.005, "mm") == pytest.approx(5.0)

    def test_cm_to_meters(self):
        assert to_meters(10, "cm") == pytest.approx(0.1)

    def test_meters_to_cm(self):
        assert from_meters(0.1, "cm") == pytest.approx(10.0)

    def test_um_to_meters(self):
        assert to_meters(500, "um") == pytest.approx(0.0005)

    def test_nm_to_meters(self):
        assert to_meters(550, "nm") == pytest.approx(550e-9)

    def test_km_to_meters(self):
        assert to_meters(1, "km") == pytest.approx(1000.0)

    def test_round_trip_mm(self):
        """Converting to meters and back should give the original value."""
        original = 42.5
        meters = to_meters(original, "mm")
        result = from_meters(meters, "mm")
        assert result == pytest.approx(original)

    def test_round_trip_um(self):
        original = 123.456
        meters = to_meters(original, "um")
        result = from_meters(meters, "um")
        assert result == pytest.approx(original)


class TestAngleConversions:
    """Tests for angle unit conversions."""

    def test_degrees_to_radians(self):
        assert to_radians(90, "deg") == pytest.approx(math.pi / 2)

    def test_radians_to_degrees(self):
        assert from_radians(math.pi / 2, "deg") == pytest.approx(90.0)

    def test_180_degrees_to_radians(self):
        assert to_radians(180, "deg") == pytest.approx(math.pi)

    def test_360_degrees_to_radians(self):
        assert to_radians(360, "deg") == pytest.approx(2 * math.pi)

    def test_round_trip_degrees(self):
        original = 45.0
        radians = to_radians(original, "deg")
        result = from_radians(radians, "deg")
        assert result == pytest.approx(original)


class TestConvert:
    """Tests for the generic convert function."""

    def test_convert_mm_to_m(self):
        assert convert(5, "mm", "m") == pytest.approx(0.005)

    def test_convert_m_to_mm(self):
        assert convert(0.005, "m", "mm") == pytest.approx(5.0)

    def test_convert_deg_to_rad(self):
        assert convert(90, "deg", "rad") == pytest.approx(math.pi / 2)

    def test_convert_rad_to_deg(self):
        assert convert(math.pi / 2, "rad", "deg") == pytest.approx(90.0)

    def test_convert_um_to_nm(self):
        assert convert(1, "um", "nm") == pytest.approx(1000.0)

    def test_convert_incompatible_units(self):
        with pytest.raises(ValueError):
            convert(5, "mm", "deg")


class TestQuantity:
    """Tests for the Quantity class."""

    def test_quantity_to_base(self):
        q = Quantity(5, "mm")
        assert q.to_base() == pytest.approx(0.005)

    def test_quantity_to_unit(self):
        q = Quantity(0.005, "m")
        assert q.to_unit("mm") == pytest.approx(5.0)

    def test_quantity_angle(self):
        q = Quantity(90, "deg")
        assert q.to_base() == pytest.approx(math.pi / 2)

    def test_quantity_repr(self):
        q = Quantity(5, "mm")
        assert "5" in repr(q)
        assert "mm" in repr(q)


class TestUnitValidation:
    """Tests for unit validation functions."""

    def test_is_length_unit(self):
        assert is_length_unit("mm") is True
        assert is_length_unit("m") is True
        assert is_length_unit("nm") is True

    def test_is_not_length_unit(self):
        assert is_length_unit("deg") is False
        assert is_length_unit("rad") is False

    def test_is_angle_unit(self):
        assert is_angle_unit("deg") is True
        assert is_angle_unit("rad") is True

    def test_is_not_angle_unit(self):
        assert is_angle_unit("mm") is False
        assert is_angle_unit("m") is False
