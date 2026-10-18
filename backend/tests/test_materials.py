"""
Material data tests against independently published values.

Reference values are taken from the sources themselves, not from this code:
- SCHOTT N-BK7 data sheet: nd 1.51680, nF 1.52238, nC 1.51432,
  n(1060 nm) 1.50669, vd 64.17.
- I. H. Malitson, J. Opt. Soc. Am. 55, 1205 (1965), fused silica:
  n(587.6 nm) 1.4585, n(1064 nm) 1.4496.
- I. H. Malitson, Appl. Opt. 2, 1103 (1963), CaF2: n(587.6 nm) 1.4338.
- Connolly/Tatian CVD ZnSe: n(10.6 um) 2.4028.
- H. H. Li (1980) Ge: n(10 um) 4.004.
"""

import pytest

from optics.materials import (
    MATERIALS, LITERATURE, refractive_index, refractive_index_sellmeier,
    abbe_number, get_material, D_LINE, F_LINE, C_LINE,
)

VENDORS = ("Schott", "Ohara", "Hoya", "CDGM")


@pytest.mark.parametrize("material, wavelength, expected, tol", [
    ("N-BK7", D_LINE, 1.51680, 5e-5),
    ("N-BK7", F_LINE, 1.52238, 5e-5),
    ("N-BK7", C_LINE, 1.51432, 5e-5),
    ("N-BK7", 1060e-9, 1.50669, 5e-5),
    ("FusedSilica", D_LINE, 1.4585, 1e-4),
    ("FusedSilica", 1064e-9, 1.4496, 1e-4),
    ("CaF2", D_LINE, 1.4338, 1e-4),
    ("ZnSe", 10.6e-6, 2.4028, 1e-4),
    ("Ge", 10e-6, 4.004, 1e-3),
])
def test_index_matches_published_value(material, wavelength, expected, tol):
    assert refractive_index(material, wavelength) == pytest.approx(expected, abs=tol)


def test_nbk7_abbe_number_matches_datasheet():
    assert abbe_number("N-BK7") == pytest.approx(64.17, abs=0.02)


def test_air_is_unity():
    assert refractive_index("air") == 1.0
    assert refractive_index("Air") == 1.0


def test_aliases():
    assert refractive_index("SiO2") == refractive_index("FusedSilica")
    assert get_material("Al2O3").name == get_material("Sapphire").name


def test_unknown_material_raises():
    with pytest.raises((ValueError, KeyError)):
        refractive_index("Unobtanium")


def test_outside_measured_range_raises():
    # SCHOTT tabulates N-BK7 to 2.5 um; 20 um is far outside.
    with pytest.raises(ValueError):
        refractive_index("N-BK7", 20e-6)
    with pytest.raises(ValueError):
        refractive_index("CaF2", 50e-6)


def test_legacy_name_is_same_function():
    assert refractive_index_sellmeier("N-BK7", D_LINE) == refractive_index("N-BK7", D_LINE)


def test_normal_dispersion_in_visible():
    for name in ("N-BK7", "N-SF11", "FusedSilica", "CaF2"):
        assert refractive_index(name, F_LINE) > refractive_index(name, D_LINE) > refractive_index(name, C_LINE)


def test_every_vendor_glass_reproduces_its_catalog_nd():
    """The stored formula must give the vendor's own nd at 587.56 nm."""
    bad = []
    for name, m in MATERIALS.items():
        if m.manufacturer in VENDORS:
            n = m.dispersion.n(D_LINE * 1e6)
            if abs(n - m.nd) > 2e-5:
                bad.append((name, n, m.nd))
    assert not bad, bad[:10]


def test_vendor_catalog_counts():
    counts = {v: 0 for v in VENDORS}
    for m in MATERIALS.values():
        if m.manufacturer in counts:
            counts[m.manufacturer] += 1
    assert all(c > 50 for c in counts.values()), counts


def test_literature_materials_cite_a_source_and_range():
    for name, entry in LITERATURE.items():
        m = get_material(name)
        assert m.source, name
        assert m.dispersion.range_um is not None, name
