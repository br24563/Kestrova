"""
Tests for the diffraction MTF by FFT and by Hopkins direct integration,
through focus and across field (optics.mtf_analysis), against independent
references:

- an aberration-free circular pupil (a parabolic mirror on axis) has
  MTF = (2/pi)(acos x - x sqrt(1 - x^2)), x = nu / nu_c, nu_c = 2 NA'/lambda;
- pure defocus W = W020 rho^2: the overlap integral reduces to
  OTF(d) = (1/pi) integral 2 h(u) cos(4 pi W020 d u) du over the overlap,
  h(u) = sqrt(1 - (|u| + d/2)^2), d the shift in pupil radii, integrated
  here with scipy (W020 measured from the traced wavefront by least squares);
- FFT and Hopkins are independent numerical methods and must agree;
- through focus, a parabola's MTF peaks at its paraxial focus with the
  diffraction-limited value, nearly symmetric (moving the image adds a small
  rho^4 term whose sign follows the defocus, so +-dz differ slightly);
  across field, a parabola's coma lowers the MTF.
"""

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.integrate import quad

from optics import lens_data as ld
from optics import mtf_analysis as M
from optics import pupil as pp
from optics.lens_data import LensData, LensSurface

WL = 587.56e-9


def parabola(dz=0.0, field_deg=0.05, wavelengths=(WL,)):
    """f/5 parabolic mirror (f = 0.5 m), image moved by dz."""
    return ld.to_system(LensData(
        surfaces=[LensSurface(label="M", radius=-1.0, conic=-1.0, material="MIRROR",
                              is_stop=True, semi_diameter=0.05, thickness=-0.5 - dz)],
        object_distance=None, field_angle=math.radians(field_deg),
        wavelengths=list(wavelengths), analysis_settings={"wavelength": WL},
    ))


def cutoff(system, wl=WL):
    return 2 * pp.image_space_na(system, wl) / wl


def defocus_otf(d, w020):
    half = 1 - d / 2
    val = quad(lambda u: 2 * math.sqrt(max(0.0, 1 - (abs(u) + d / 2) ** 2))
               * math.cos(4 * math.pi * w020 * d * u), -half, half, limit=200)[0]
    return val / math.pi


class TestHopkins:

    def test_diffraction_limited_closed_form(self):
        s = parabola()
        f = np.linspace(0, 0.98, 12) * cutoff(s)
        ref = M.diffraction_limited_mtf(f / cutoff(s))
        h = M.hopkins_otf(s, f, WL, quadrature=48)
        np.testing.assert_allclose(np.abs(h["tangential"]), ref, atol=1e-4)
        np.testing.assert_allclose(np.abs(h["sagittal"]), ref, atol=1e-4)
        # the FFT method agrees, less precisely on its 64-sample grid
        g = M._fft_otf(s, f, WL, 0, 0, 0, None, 64)
        np.testing.assert_allclose(np.abs(g["tangential"]), ref, atol=4e-3)

    def test_converges_with_quadrature_order(self):
        s = parabola()
        f = np.linspace(0.1, 0.9, 5) * cutoff(s)
        ref = M.diffraction_limited_mtf(f / cutoff(s))
        errs = [np.max(np.abs(np.abs(M.hopkins_otf(s, f, WL, quadrature=q)["tangential"])
                              - ref)) for q in (12, 24, 48)]
        assert errs[2] < errs[1] < errs[0]

    def test_defocus_matches_the_analytic_integral(self):
        s = parabola(30e-6)
        g = pp.wavefront_grid(s, 0, 65, WL)
        r2 = (g.px ** 2 + g.py ** 2)[g.mask]
        coef = np.linalg.lstsq(np.stack([np.ones_like(r2), r2, r2 ** 2], 1),
                               g.W[g.mask] / WL, rcond=None)[0]
        w020 = coef[1]
        assert 0.2 < w020 < 0.3  # about a quarter wave
        f = np.linspace(0, 0.95, 10) * cutoff(s)
        ref = np.array([abs(defocus_otf(2 * x / cutoff(s), w020)) for x in f])
        h = np.abs(M.hopkins_otf(s, f, WL)["tangential"])
        fft = np.abs(M._fft_otf(s, f, WL, 0, 0, 0, None, 256)["tangential"])
        np.testing.assert_allclose(h, ref, atol=1.5e-3)
        np.testing.assert_allclose(h, fft, atol=1.5e-3)

    def test_beyond_cutoff_is_zero(self):
        s = parabola()
        h = M.hopkins_otf(s, [1.2 * cutoff(s)], WL)
        assert h["tangential"][0] == 0 and h["sagittal"][0] == 0


class TestCurvesFocusField:

    def test_polychromatic_curves_and_limit(self):
        s = parabola(wavelengths=(486.13e-9, WL, 656.27e-9))
        out = M.mtf_curves(s, 0, frequencies_mm=[0.0, 50.0, 150.0], method="hopkins")
        # a mirror has no colour: each wavelength is diffraction limited, so
        # the polychromatic MTF equals the weighted diffraction limit
        np.testing.assert_allclose(out["tangential"], out["diffraction_limit"], atol=2e-4)
        assert out["tangential"][0] == pytest.approx(1.0)
        assert out["cutoff_cyc_per_mm"] == pytest.approx(cutoff(s, 486.13e-9) / 1e3,
                                                         rel=1e-6)

    def test_both_methods_agree_on_field_curves(self):
        s = parabola(field_deg=0.6)
        fft = M.mtf_curves(s, 2, frequencies_mm=[20, 60, 100], method="fft", grid=128)
        hop = M.mtf_curves(s, 2, frequencies_mm=[20, 60, 100], method="hopkins")
        np.testing.assert_allclose(fft["tangential"], hop["tangential"], atol=5e-3)
        np.testing.assert_allclose(fft["sagittal"], hop["sagittal"], atol=5e-3)

    def test_through_focus_is_symmetric_about_paraxial_focus(self):
        s = parabola()
        out = M.through_focus_mtf(s, 100.0, 0, defocus_range=(-0.1e-3, 0.1e-3),
                                  points=9, method="hopkins")
        t = np.array(out["tangential"])
        assert out["best_focus_mm"]["mean"] == pytest.approx(0.0, abs=1e-9)
        np.testing.assert_allclose(t, t[::-1], atol=1e-3)
        assert t[4] == pytest.approx(
            float(M.diffraction_limited_mtf(100e3 / cutoff(s))), abs=1e-4)
        assert 0 < out["half_peak_range_mm"] < 0.2

    def test_default_scan_finds_the_peak_of_an_uncorrected_lens(self):
        # an uncorrected singlet: the best focus at a frequency is neither the
        # image plane nor the minimum-RMS focus; compare with a wide scan
        from optics.presets import get_preset_by_id

        s = get_preset_by_id("thick_lens")["system"]
        wide = M.through_focus_mtf(s, 50.0, 0, defocus_range=(-4e-3, 1e-3),
                                   points=101)
        z = np.array(wide["defocus_mm"])
        mean = 0.5 * (np.array(wide["tangential"]) + np.array(wide["sagittal"]))
        auto = M.through_focus_mtf(s, 50.0, 0)
        assert not auto["peak_at_scan_edge"]
        assert auto["best_focus_mm"]["mean"] == pytest.approx(z[np.argmax(mean)],
                                                              abs=0.1)
        best_auto = max(0.5 * (a + b) for a, b in zip(auto["tangential"],
                                                      auto["sagittal"]))
        assert best_auto == pytest.approx(mean.max(), rel=0.05)
        # far from the image plane (0) and from the minimum-RMS focus
        assert abs(auto["best_focus_mm"]["mean"]) > 0.5
        assert abs(auto["best_focus_mm"]["mean"] - M.best_focus_shift(s) * 1e3) > 0.5

    def test_mtf_falls_across_field_with_coma(self):
        s = parabola(field_deg=1.0)
        out = M.mtf_vs_field(s, frequencies_mm=[60.0], points=5, method="fft")
        t = np.array(out["tangential"][0])
        assert out["field_fraction"] == pytest.approx([0, 0.25, 0.5, 0.75, 1.0])
        # coma grows with field; MTF need not fall monotonically (contrast
        # can reverse and partly recover), but it falls far below the axis
        assert t[0] > 0.7 and t[1] < t[0] and np.max(t[2:]) < 0.25 * t[0]
        on_axis = M.mtf_curves(s, 0, frequencies_mm=[60.0], method="fft", grid=48)
        assert t[0] == pytest.approx(on_axis["tangential"][0], abs=2e-3)

    def test_invalid_input(self):
        with pytest.raises(ValueError):
            M.polychromatic_otf(parabola(), [1e3], method="magic")
        with pytest.raises(ValueError):
            M.mtf_curves(parabola(), 7)


def test_endpoints():
    from api.main import app

    client = TestClient(app)
    system = parabola(field_deg=0.5).model_dump()
    r = client.post("/api/analyze/mtf", json={"system": system, "field": 0,
                                              "method": "hopkins",
                                              "frequencies_mm": [0, 50]})
    assert r.status_code == 200 and r.json()["tangential"][0] == pytest.approx(1.0)
    r = client.post("/api/analyze/through-focus-mtf",
                    json={"system": system, "frequency_mm": 50, "points": 5})
    assert r.status_code == 200 and len(r.json()["tangential"]) == 5
    r = client.post("/api/analyze/mtf-vs-field",
                    json={"system": system, "frequencies_mm": [30], "points": 3})
    assert r.status_code == 200 and len(r.json()["tangential"][0]) == 3
    assert client.post("/api/analyze/mtf", json={"system": system, "field": 9}
                       ).status_code == 400
