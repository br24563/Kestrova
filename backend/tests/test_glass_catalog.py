"""
Tests for glass availability, price and compliance data
(optics.glass_catalog).

References:
- blank mass of a cylinder, m = pi r^2 t rho (computed here by hand);
- cost = mass x relative price x reference price, or a recorded quote;
- availability follows the vendor's own fields (Schott preferred/inquiry,
  CDGM melt frequency "MA" = stocked), checked on real catalog entries;
- lead is flagged only for Schott's legacy lead-silicate families (F, LF,
  LLF, SF without "N-"), whose "N-" versions are the lead-free equivalents;
- a thin lens is costed as the equiconvex lens of the same focal length
  with zero edge thickness: R = 2 (n - 1) f, t = 2 (R - sqrt(R^2 - a^2)).
"""

import json
import math

import pytest

from optics import glass_catalog as gc
from optics.materials import refractive_index
from optics.materials_expanded import ALL_MATERIALS
from optics.models import (
    AnalysisSettings,
    ApertureStop,
    ImagePlane,
    Object,
    OpticalSystem,
    ThickLens,
    ThinLens,
)


@pytest.fixture(autouse=True)
def clean_state():
    yield
    gc.clear_vendor_quotes()
    gc.clear_vendor_data()
    gc.set_reference_price(None)


def first(pred):
    return next(k for k, p in ALL_MATERIALS.items() if pred(p))


def system(*components):
    return OpticalSystem(
        components=list(components), wavelengths=[587.6e-9],
        object=Object(position=0.0, height=0.001), image_plane=ImagePlane(position=0.5),
        analysis_settings=AnalysisSettings(wavelength=587.6e-9),
    )


class TestVendorClassification:

    def test_availability_from_vendor_fields(self):
        preferred = first(lambda p: p.manufacturer == "Schott" and p.status == "preferred")
        inquiry = first(lambda p: p.manufacturer == "Schott" and p.status == "inquiry")
        stocked = first(lambda p: p.melt_frequency == "MA")
        rare = first(lambda p: p.melt_frequency not in (None, "", "MA"))
        assert gc.get_glass_data(preferred).availability is gc.Availability.STANDARD
        assert gc.get_glass_data(inquiry).availability is gc.Availability.MADE_TO_ORDER
        assert gc.get_glass_data(stocked).availability is gc.Availability.IN_STOCK
        assert gc.get_glass_data(rare).availability is gc.Availability.MADE_TO_ORDER
        assert gc.get_glass_data(preferred).suppliers == ("Schott",)

    def test_lead_flints_and_their_equivalents(self):
        sf11 = gc.get_glass_data("SF11")
        assert sf11.substances == ("Pb",) and not sf11.is_compliant
        assert gc.get_glass_data("N-SF11").is_compliant
        assert gc.LEAD_FREE_EQUIVALENTS["SF11"] == "N-SF11"
        flagged = gc.restricted_glasses()
        assert flagged and all(
            ALL_MATERIALS[r["glass"]].manufacturer == "Schott"
            and not r["glass"].startswith("N-") for r in flagged
        )
        assert any(r["glass"] == "SF11" and r["lead_free_equivalent"] == "N-SF11"
                   for r in flagged)

    def test_restriction_classes(self):
        assert gc.RestrictionClass.DECLARABLE.is_compliant
        assert not gc.RestrictionClass.PROHIBITED.is_compliant

    def test_legacy_names_and_unknown_glasses(self):
        assert gc.resolve_glass_name("BK7") == "N-BK7"
        assert gc.get_glass_data("BK7").name == "N-BK7"
        assert gc.get_glass_data("UNOBTAINIUM") is None
        status = gc.availability_status("UNOBTAINIUM")
        assert not status["known"] and not status["sourcable"]


class TestPricing:

    def test_blank_mass_is_a_cylinder(self):
        # 25 mm x 5 mm at 2.51 g/cm^3: pi 12.5^2 5 mm^3 = 2454.37 mm^3 -> 6.1605 g
        assert gc.element_blank_mass(0.025, 0.005, 2.51) == pytest.approx(6.16046e-3,
                                                                          rel=1e-5)
        assert gc.element_blank_mass(0.025, 0.005, 2.51, blank_factor=1.5) == pytest.approx(
            1.5 * 6.16046e-3, rel=1e-5)
        assert gc.element_blank_mass(-1, 0.005, 2.51) == 0.0

    def test_price_needs_a_basis(self):
        assert gc.unit_price_per_kg("N-BK7") is None
        assert gc.element_material_cost(0.025, 0.005, "N-BK7") is None
        gc.set_reference_price(80.0)
        rel = ALL_MATERIALS["N-BK7"].relative_price
        assert gc.unit_price_per_kg("N-BK7") == pytest.approx(rel * 80.0)
        gc.set_vendor_quote("N-BK7", 120.0, supplier="Schott", lead_time_days=10,
                            minimum_order_kg=2)
        assert gc.unit_price_per_kg("BK7") == 120.0
        mass = math.pi * 0.0125**2 * 0.005 * ALL_MATERIALS["N-BK7"].density * 1000
        assert gc.element_material_cost(0.025, 0.005, "N-BK7") == pytest.approx(mass * 120)
        assert gc.get_vendor_quote("N-BK7")["minimum_order_kg"] == 2.0

    def test_vendor_data_overrides_the_catalog(self):
        n = gc.load_vendor_data(json.dumps({"glasses": {
            "N-BK7": {"availability": "in_stock", "lead_time_days": 3,
                      "suppliers": ["Schott", "Distributor"], "price_per_kg": 99.0},
        }}))
        assert n == 1
        data = gc.get_glass_data("N-BK7")
        assert data.availability is gc.Availability.IN_STOCK
        assert data.supplier_count == 2
        assert gc.unit_price_per_kg("N-BK7") == 99.0
        status = gc.availability_status("N-BK7")
        assert status["lead_time_days"] == 3 and status["sourcable"]
        gc.load_vendor_data({"N-SF11": {"availability": "limited"}}, replace=True)
        assert gc.get_glass_data("N-BK7").availability is gc.Availability.STANDARD

    @pytest.mark.parametrize("bad", ["[1, 2]", {"glasses": [1]}, {"glasses": {"X": 3}}])
    def test_malformed_vendor_data(self, bad):
        with pytest.raises(ValueError):
            gc.load_vendor_data(bad)


class TestSystemSummaries:

    def test_cost_of_a_system(self):
        gc.set_reference_price(50.0)
        lens = ThickLens(id="L1", position=0.1, radius1=0.05, radius2=-0.05,
                         thickness=0.004, aperture_diameter=0.02, material="N-BK7")
        thin = ThinLens(id="T1", position=0.2, focal_length=0.1, aperture_diameter=0.02,
                        material="N-SF11")
        out = gc.system_glass_cost(
            system(ApertureStop(id="S", position=0.05, diameter=0.02), lens, thin,
                   ThickLens(id="X", position=0.3, radius1=0.05, radius2=-0.05,
                             thickness=0.004, aperture_diameter=0.02,
                             material="MADE-UP")),
            quantity=3,
        )
        assert out["element_count"] == 2 and out["unknown_glasses"] == ["MADE-UP"]
        # thin lens: equiconvex with zero edge thickness
        n = refractive_index("N-SF11")
        R = 2 * (n - 1) * 0.1
        t_thin = 2 * (R - math.sqrt(R * R - 0.01**2))
        assert out["elements"][1]["thickness_mm"] == pytest.approx(t_thin * 1e3)
        cost = sum(
            math.pi * 0.01**2 * t * ALL_MATERIALS[g].density * 1000
            * ALL_MATERIALS[g].relative_price * 50.0
            for g, t in (("N-BK7", 0.004), ("N-SF11", t_thin))
        )
        assert out["material_cost_per_unit"] == pytest.approx(cost)
        assert out["total_material_cost"] == pytest.approx(3 * cost)
        assert out["is_compliant"]

    def test_unpriced_and_restricted(self):
        lens = ThickLens(id="L1", position=0.1, radius1=0.05, radius2=-0.05,
                         thickness=0.004, aperture_diameter=0.02, material="SF11")
        out = gc.system_glass_cost(system(lens))
        assert out["material_cost_per_unit"] is None and out["total_material_cost"] is None
        assert out["restricted_glasses"] == ["SF11"] and not out["is_compliant"]
        report = gc.compliance_report(system(lens))
        assert report["non_compliant_glasses"] == ["SF11"]
        assert "Lead (Pb)" in report["elements"][0]["warning"]
        assert report["elements"][0]["regulation"] == [
            gc.RESTRICTED_SUBSTANCES["Pb"].regulation]
