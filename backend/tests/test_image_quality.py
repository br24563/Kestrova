"""
Tests for the polychromatic PSF, encircled / ensquared energy and the field
plots (optics.image_quality) against independent references:

- an aberration-free circular pupil (a parabola on axis) has encircled
  energy 1 - J0(v)^2 - J1(v)^2, v = 2 pi NA' r / lambda (Rayleigh);
- a square of half-width a contains the circle of radius a, so ensquared
  energy >= encircled energy at the same size;
- an ideal (paraxial) lens maps y' = f tan(theta): zero paraxial distortion
  and F-theta distortion (tan theta - theta) / theta exactly;
- a mirror has no lateral colour; for a refracting lens at a small field the
  real-ray F - C lateral colour approaches the paraxial value of
  optics.aberration.lateral_chromatic_aberration (at full field the real
  value also holds higher orders);
- relative illumination equals optics.illumination.relative_illumination.
"""

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.optimize import brentq
from scipy.special import j0, j1

from optics import image_quality as IQ
from optics import lens_data as ld
from optics.aberration import lateral_chromatic_aberration
from optics.illumination import relative_illumination
from optics.lens_data import LensData, LensSurface
from optics.materials import C_LINE, D_LINE, F_LINE
from optics.presets import get_preset_by_id

WL = 587.56e-9


def parabola(field_deg=0.05, wavelengths=(WL,)):
    return ld.to_system(LensData(
        surfaces=[LensSurface(label="M", radius=-1.0, conic=-1.0, material="MIRROR",
                              is_stop=True, semi_diameter=0.05, thickness=-0.5)],
        object_distance=None, field_angle=math.radians(field_deg),
        wavelengths=list(wavelengths), analysis_settings={"wavelength": WL},
    ))


def ideal_lens(field_deg=20.0):
    return ld.to_system(LensData(
        surfaces=[LensSurface(label="L", surface_type="paraxial", focal_length=0.1,
                              is_stop=True, semi_diameter=0.005, thickness=0.1)],
        object_distance=None, field_angle=math.radians(field_deg),
        wavelengths=[WL], analysis_settings={"wavelength": WL},
    ))


class TestPsf:

    def test_diffraction_limited_energy(self):
        p = IQ.field_psf(parabola(), 0)
        ee = np.array(p["encircled"])
        rayleigh = np.array(p["diffraction_limited_encircled"])
        assert p["energy_total"] == pytest.approx(1.0, abs=1e-6)
        # the square pupil grid approximates the circle: about 1.5 % bias
        np.testing.assert_allclose(ee, rayleigh, atol=0.02)
        v80 = brentq(lambda v: 1 - j0(v) ** 2 - j1(v) ** 2 - 0.8, 1.0, 3.8)
        assert p["radius_80_mm"] / p["airy_radius_mm"] == pytest.approx(
            v80 / 3.8317, rel=0.03)
        assert np.all(np.array(p["ensquared"]) >= ee - 1e-12)
        assert p["centroid_mm"] == pytest.approx([0.0, 0.0], abs=1e-9)
        psf = np.array(p["psf"])
        assert psf.max() == pytest.approx(1.0) and psf.shape == (65, 65)
        assert p["strehl"][0]["strehl"] == pytest.approx(1.0, abs=1e-6)

    def test_polychromatic_mirror_is_diffraction_limited(self):
        p = IQ.field_psf(parabola(wavelengths=(486.13e-9, WL, 656.27e-9)), 0)
        assert all(s["strehl"] == pytest.approx(1.0, abs=1e-6) for s in p["strehl"])
        np.testing.assert_allclose(p["encircled"], p["diffraction_limited_encircled"],
                                   atol=0.02)

    def test_aberrations_spread_the_energy(self):
        p = IQ.field_psf(get_preset_by_id("thick_lens")["system"], 0)
        assert p["encircled"][10] < p["diffraction_limited_encircled"][10] - 0.1
        # its spot (about 0.39 mm RMS) is wider than the diffraction window:
        # reported rather than silently wrapped around
        assert p["exceeds_window"]
        assert not IQ.field_psf(parabola(), 0)["exceeds_window"]

    def test_view_fits_the_energy_unless_fixed(self):
        auto = IQ.field_psf(parabola(), 0)
        assert auto["axis_mm"][-1] == pytest.approx(8 * auto["airy_radius_mm"])
        fixed = IQ.field_psf(parabola(), 0, extent_airy=3.0)
        assert fixed["axis_mm"][-1] == pytest.approx(3 * fixed["airy_radius_mm"])

    def test_missing_field(self):
        with pytest.raises(ValueError):
            IQ.field_psf(parabola(), 5)


class TestFieldPlots:

    def test_ideal_lens_ftheta_distortion(self):
        out = IQ.field_plots(ideal_lens(), 5)
        theta = np.radians(out["field_angle_deg"])
        expected = [(math.tan(t) - t) / t if t > 0 else 0.0 for t in theta]
        np.testing.assert_allclose(out["distortion"], 0.0, atol=1e-9)
        np.testing.assert_allclose(out["ftheta_distortion"], expected, rtol=1e-9,
                                   atol=1e-12)

    def test_mirror_has_no_lateral_colour(self):
        out = IQ.field_plots(parabola(field_deg=0.5,
                                      wavelengths=(486.13e-9, WL, 656.27e-9)), 3)
        for row in out["lateral_colour_mm"]:
            np.testing.assert_allclose(row["offset_mm"], 0.0, atol=1e-12)

    def test_lateral_colour_matches_the_chromatic_analysis(self):
        s = get_preset_by_id("thick_lens")["system"]
        s = s.model_copy(update={
            "object": s.object.model_copy(update={"height": s.object.height * 1e-3}),
            "wavelengths": [F_LINE, D_LINE, C_LINE],
            "analysis_settings": s.analysis_settings.model_copy(
                update={"wavelength": D_LINE}),
        })
        out = IQ.field_plots(s, 3)
        by_wl = {row["wavelength"]: row["offset_mm"] for row in out["lateral_colour_mm"]}
        tca = (by_wl[F_LINE][-1] - by_wl[C_LINE][-1]) * 1e-3
        assert tca == pytest.approx(lateral_chromatic_aberration(s), rel=1e-5)
        assert out["ftheta_distortion"] is None  # finite object

    def test_relative_illumination_matches(self):
        s = get_preset_by_id("thick_lens")["system"]
        out = IQ.field_plots(s, 5)
        np.testing.assert_allclose(out["relative_illumination"],
                                   relative_illumination(s, 5)["relative_illumination"])


def test_endpoints():
    from api.main import app

    client = TestClient(app)
    system = parabola(field_deg=0.5).model_dump()
    r = client.post("/api/analyze/psf", json={"system": system, "field": 0,
                                              "image_size": 33})
    assert r.status_code == 200 and len(r.json()["psf"]) == 33
    r = client.post("/api/analyze/field-plots", json={"system": system, "points": 3})
    assert r.status_code == 200 and len(r.json()["distortion"]) == 3
    assert client.post("/api/analyze/psf", json={"system": system, "field": 9}
                       ).status_code == 400
