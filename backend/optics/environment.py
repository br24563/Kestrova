"""
Temperature and pressure (Code V's environmental analysis) on the lens
prescription.

Catalogue indices are relative to air at 20 C and 101 325 Pa. At
temperature T and pressure P:

- every glass index becomes n_rel(T, P) = (n_cat n_air(20 C, 1 atm) +
  dn_abs(T)) / n_air(T, P), with dn_abs from the vendor's Schott dn/dT
  constants (:func:`optics.thermal.material.index_change`) and the air
  index from Edlen's formula (B. Edlen, Metrologia 2, 71 (1966), in the
  form of K. P. Birch and M. J. Downs, Metrologia 30, 155 (1993));
- every glass element grows with its glass's CTE: radii, aspheric terms,
  clear apertures and its centre thickness scale by (1 + alpha dT), a
  surface taking the CTE of the glass after it (or, at an element's back,
  the glass before it);
- with a housing CTE, every air space (and the image distance) grows by
  (1 + alpha_housing dT); without one the spacings are kept.

The traced system carries the environment, so every analysis (MTF, PSF,
spot, polarization...) runs at that temperature and pressure. Mirrors keep
their shape (their substrate CTE is not known).
"""

from __future__ import annotations

import math
from typing import Optional

from .lens_data import LensData, configured, resolve, to_system
from .materials import parse_model_glass, refractive_index
from .models import Environment, OpticalSystem
from .thermal.material import get_thermal_properties, index_change

REFERENCE_TEMPERATURE = 20.0  # C
REFERENCE_PRESSURE = 101325.0  # Pa


def air_index(wavelength: float, temperature: float, pressure: float) -> float:
    """Refractive index of dry air (Edlen 1966, Birch and Downs 1993):
    wavelength in m, temperature in C, pressure in Pa."""
    s2 = (1e-6 / wavelength) ** 2  # (1 / lambda[um])^2
    ns = 1e-8 * (8342.54 + 2406147.0 / (130.0 - s2) + 15998.0 / (38.9 - s2))
    t, p = temperature, pressure
    return 1.0 + ns * p * (1.0 + p * (0.601 - 0.00972 * t) * 1e-8) / (
        96095.43 * (1.0 + 0.003661 * t)
    )


def glass_index(
    material: str, wavelength: float, temperature: float, pressure: float
) -> float:
    """A glass's index relative to air at temperature and pressure."""
    n_cat = refractive_index(material, wavelength)
    if temperature == REFERENCE_TEMPERATURE and pressure == REFERENCE_PRESSURE:
        return n_cat
    n_abs = n_cat * air_index(wavelength, REFERENCE_TEMPERATURE, REFERENCE_PRESSURE)
    if temperature != REFERENCE_TEMPERATURE:
        if parse_model_glass(material) is not None:
            raise ValueError(
                f"A model glass ({material}) has no dn/dT data; snap it to a "
                "catalogue glass first"
            )
        n_abs += index_change(material, wavelength, temperature, REFERENCE_TEMPERATURE)
    return n_abs / air_index(wavelength, temperature, pressure)


def _is_glass(material: Optional[str]) -> bool:
    return bool(material) and material != "MIRROR" and str(material).lower() != "air"


def _cte(material: str) -> float:
    if parse_model_glass(material) is not None:
        raise ValueError(f"A model glass ({material}) has no CTE; snap it first")
    props = get_thermal_properties(material)
    if props is None or props.CTE is None:
        raise ValueError(f"No published CTE for '{material}'")
    return props.CTE * 1e-6


def _scale_surface(s, k: float) -> None:
    """Grow a surface's shape uniformly by k (a sag z(r) -> k z(r / k))."""
    s.radius *= k
    s.radius_x *= k
    if s.semi_diameter is not None:
        s.semi_diameter *= k
    if s.norm_radius is not None:
        s.norm_radius *= k
    s.aspheric_coefficients = [
        a * k ** (1 - n) for a, n in zip(s.aspheric_coefficients, range(4, 22, 2))
    ]
    s.odd_coefficients = [
        a * k ** (1 - n) for a, n in zip(s.odd_coefficients, range(3, 21, 2))
    ]
    # Q, Zernike and XY terms are lengths over a normalisation radius
    s.q_coefficients = [a * k for a in s.q_coefficients]
    s.zernike_coefficients = [a * k for a in s.zernike_coefficients]
    s.xy_coefficients = {key: a * k for key, a in s.xy_coefficients.items()}
    # a phase c r^n keeps its value at the scaled radius
    s.phase_coefficients = [
        a * k ** (-n) for a, n in zip(s.phase_coefficients, range(2, 22, 2))
    ]
    if s.obscuration_semi:
        s.obscuration_semi *= k
    if s.aperture_half_x:
        s.aperture_half_x *= k
    if s.aperture_half_y:
        s.aperture_half_y *= k


def environment_lens(
    lens: LensData,
    temperature: float,
    mount_cte: Optional[float] = None,
) -> LensData:
    """
    The prescription's geometry at ``temperature`` (C): glass elements grown
    by their CTE, air spaces by ``mount_cte`` (1e-6/K) when given. Solves
    and pickups are resolved first and kept as values. The glass indices
    change in the traced system (see :func:`environment_system`).
    """
    dT = temperature - REFERENCE_TEMPERATURE
    out = resolve(lens)
    for s in out.surfaces:
        s.solves, s.pickups, s.semi_diameter_auto = {}, {}, False
    if dT == 0:
        return out
    before: Optional[str] = None
    for s in out.surfaces:
        if s.surface_type in ("coordinate_break", "component", "paraxial"):
            if s.surface_type == "paraxial" and mount_cte:
                s.thickness *= 1 + mount_cte * 1e-6 * dT
            continue
        after = s.material
        if _is_glass(after):
            _scale_surface(s, 1 + _cte(str(after)) * dT)
        elif _is_glass(before):
            _scale_surface(s, 1 + _cte(str(before)) * dT)
        if _is_glass(after):
            s.thickness *= 1 + _cte(str(after)) * dT
        elif mount_cte:
            s.thickness *= 1 + mount_cte * 1e-6 * dT
        if after != "MIRROR":
            before = after
    return LensData.model_validate(out.model_dump())


def environment_system(
    lens: LensData,
    temperature: float = REFERENCE_TEMPERATURE,
    pressure: float = REFERENCE_PRESSURE,
    mount_cte: Optional[float] = None,
    configuration: int = 0,
) -> OpticalSystem:
    """The traced system of a configuration at temperature and pressure."""
    one = configured(lens, configuration) if lens.num_configurations > 1 else lens
    hot = environment_lens(one, temperature, mount_cte)
    system = to_system(hot)
    return system.model_copy(
        update={"environment": Environment(temperature=temperature, pressure=pressure)}
    )


def environment_table(
    lens: LensData,
    temperatures: list[float],
    pressure: float = REFERENCE_PRESSURE,
    mount_cte: Optional[float] = None,
    configuration: int = 0,
) -> list[dict]:
    """First-order data, focus shift (paraxial image minus image plane),
    RMS wavefront at the image plane and the quarter-wave depth of focus
    at each temperature."""
    from . import raytrace as rt
    from .merit import wavefront_residuals

    rows = []
    for T in temperatures:
        system = environment_system(lens, T, pressure, mount_cte, configuration)
        fo = rt.first_order(system)
        seq = rt.build_sequence(system)
        shift = (fo.image_z - seq.image_z) * seq.image_direction
        wl = system.analysis_settings.wavelength
        r = wavefront_residuals(system, rings=4, clip=True)
        n = fo.working_f_number
        rows.append(
            {
                "temperature": T,
                "pressure": pressure,
                "efl": fo.efl,
                "bfl": fo.bfl,
                "focus_shift": shift,
                "rms_wavefront": float(math.sqrt((r**2).sum())),
                "depth_of_focus": 2 * wl * n * n,
            }
        )
    return rows
