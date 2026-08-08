"""
Centralized unit handling for the optical design engine.

All internal calculations use SI base units:
    - Length: meters (m)
    - Angle: radians (rad)

The user interface and API accept convenient units (nm, um, mm, cm, m,
degrees) and convert them to base units before any calculation.

This module is the SINGLE source of truth for unit conversions.
No other module should perform unit conversions directly.
"""

import math
from dataclasses import dataclass
from typing import Union

# ---------------------------------------------------------------------------
# Base unit definitions
# ---------------------------------------------------------------------------

# The internal (base) unit for length is the meter.
# The internal (base) unit for angle is the radian.

# Each entry maps a unit name to its conversion factor TO the base unit.
# To convert a value FROM a unit TO the base unit, multiply by the factor.
# To convert a value FROM the base unit TO a unit, divide by the factor.

LENGTH_UNITS: dict[str, float] = {
    "nm": 1e-9,       # nanometer
    "um": 1e-6,       # micrometer (micron)
    "mm": 1e-3,       # millimeter
    "cm": 1e-2,       # centimeter
    "m": 1.0,         # meter (base unit)
    "km": 1e3,        # kilometer
}

ANGLE_UNITS: dict[str, float] = {
    "rad": 1.0,                   # radian (base unit)
    "deg": math.pi / 180.0,       # degree
    "mrad": 1e-3,                 # milliradian
}

# Wavelength units (same as length, but kept separate for clarity)
WAVELENGTH_UNITS: dict[str, float] = {
    "nm": 1e-9,
    "um": 1e-6,
    "mm": 1e-3,
    "m": 1.0,
}


# ---------------------------------------------------------------------------
# Quantity class
# ---------------------------------------------------------------------------

@dataclass
class Quantity:
    """
    A physical quantity with a numeric value and a unit.

    The value is stored in the given unit. Use ``to_base()`` to get the
    value in the SI base unit (meters for length, radians for angle).

    Examples:
        >>> q = Quantity(5, "mm")
        >>> q.to_base()
        0.005
        >>> q2 = Quantity(0.005, "m")
        >>> q2.to_unit("mm")
        5.0
    """

    value: float
    unit: str

    def to_base(self) -> float:
        """Convert the value to the SI base unit (meters or radians)."""
        if self.unit in LENGTH_UNITS:
            return self.value * LENGTH_UNITS[self.unit]
        if self.unit in ANGLE_UNITS:
            return self.value * ANGLE_UNITS[self.unit]
        if self.unit in WAVELENGTH_UNITS:
            return self.value * WAVELENGTH_UNITS[self.unit]
        raise ValueError(f"Unknown unit: {self.unit}")

    def to_unit(self, target_unit: str) -> float:
        """
        Convert the value to a different unit.

        The current unit must be known (length or angle).
        """
        base_value = self.to_base()
        if target_unit in LENGTH_UNITS:
            return base_value / LENGTH_UNITS[target_unit]
        if target_unit in ANGLE_UNITS:
            return base_value / ANGLE_UNITS[target_unit]
        if target_unit in WAVELENGTH_UNITS:
            return base_value / WAVELENGTH_UNITS[target_unit]
        raise ValueError(f"Unknown target unit: {target_unit}")

    def __repr__(self) -> str:
        return f"Quantity({self.value}, '{self.unit}')"


# ---------------------------------------------------------------------------
# Conversion functions
# ---------------------------------------------------------------------------

def to_meters(value: float, unit: str) -> float:
    """Convert a length value to meters (the base unit)."""
    if unit not in LENGTH_UNITS:
        raise ValueError(f"Unknown length unit: {unit}")
    return value * LENGTH_UNITS[unit]


def from_meters(value: float, unit: str) -> float:
    """Convert a length value from meters to the given unit."""
    if unit not in LENGTH_UNITS:
        raise ValueError(f"Unknown length unit: {unit}")
    return value / LENGTH_UNITS[unit]


def to_radians(value: float, unit: str) -> float:
    """Convert an angle value to radians (the base unit)."""
    if unit not in ANGLE_UNITS:
        raise ValueError(f"Unknown angle unit: {unit}")
    return value * ANGLE_UNITS[unit]


def from_radians(value: float, unit: str) -> float:
    """Convert an angle value from radians to the given unit."""
    if unit not in ANGLE_UNITS:
        raise ValueError(f"Unknown angle unit: {unit}")
    return value / ANGLE_UNITS[unit]


def to_meters_wavelength(value: float, unit: str) -> float:
    """Convert a wavelength value to meters."""
    if unit not in WAVELENGTH_UNITS:
        raise ValueError(f"Unknown wavelength unit: {unit}")
    return value * WAVELENGTH_UNITS[unit]


def from_meters_wavelength(value: float, unit: str) -> float:
    """Convert a wavelength value from meters to the given unit."""
    if unit not in WAVELENGTH_UNITS:
        raise ValueError(f"Unknown wavelength unit: {unit}")
    return value / WAVELENGTH_UNITS[unit]


# ---------------------------------------------------------------------------
# Convenience: auto-detect unit type
# ---------------------------------------------------------------------------

def convert(value: float, from_unit: str, to_unit: str) -> float:
    """
    Convert a value from one unit to another.

    Automatically detects whether the units are length or angle units.

    Examples:
        >>> convert(5, "mm", "m")
        0.005
        >>> convert(90, "deg", "rad")
        1.5707963267948966
    """
    # Try length first
    if from_unit in LENGTH_UNITS and to_unit in LENGTH_UNITS:
        return to_meters(value, from_unit) * (1.0 / LENGTH_UNITS[to_unit])
    # Try angle
    if from_unit in ANGLE_UNITS and to_unit in ANGLE_UNITS:
        return to_radians(value, from_unit) * (1.0 / ANGLE_UNITS[to_unit])
    # Try wavelength
    if from_unit in WAVELENGTH_UNITS and to_unit in WAVELENGTH_UNITS:
        return to_meters_wavelength(value, from_unit) * (1.0 / WAVELENGTH_UNITS[to_unit])
    raise ValueError(
        f"Cannot convert from '{from_unit}' to '{to_unit}': "
        f"units must be of the same type (length, angle, or wavelength)."
    )


# ---------------------------------------------------------------------------
# Unit validation
# ---------------------------------------------------------------------------

def is_length_unit(unit: str) -> bool:
    """Return True if the unit is a recognized length unit."""
    return unit in LENGTH_UNITS


def is_angle_unit(unit: str) -> bool:
    """Return True if the unit is a recognized angle unit."""
    return unit in ANGLE_UNITS


def is_wavelength_unit(unit: str) -> bool:
    """Return True if the unit is a recognized wavelength unit."""
    return unit in WAVELENGTH_UNITS


def all_length_units() -> list[str]:
    """Return a list of all recognized length unit names."""
    return list(LENGTH_UNITS.keys())


def all_angle_units() -> list[str]:
    """Return a list of all recognized angle unit names."""
    return list(ANGLE_UNITS.keys())


def all_wavelength_units() -> list[str]:
    """Return a list of all recognized wavelength unit names."""
    return list(WAVELENGTH_UNITS.keys())
