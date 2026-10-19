"""
Tests for Zernike polynomials (optics.zernike) and wavefront analysis
(optics.wavefront) against independent references:

- Noll (1976), JOSA 66, 207, Table 1: index order and closed forms;
- the Fringe (University of Arizona / Wyant) table;
- orthonormality over the unit disk and over an annulus, integrated here
  with Gauss-Legendre quadrature in rho and uniform sampling in theta;
- Mahajan (1981), JOSA 71, 75: annular defocus and spherical aberration;
- pure defocus W = a rho^2: RMS a / sqrt(12) and exact Strehl
  [sin(phi/2) / (phi/2)]^2 with phi = 2 pi a / lambda;
- a spherical mirror (object at infinity, stop at the mirror) has
  W040 = h^4 / (4 R^3) in magnitude, and for W = W040 rho^4 the Noll
  spherical coefficient is W040 / (6 sqrt 5).
"""

import math

import numpy as np
import pytest

from optics import lens_data as ld
from optics import raytrace as rt
from optics.lens_data import LensData, LensSurface
from optics.wavefront import (
    compute_seidel_from_wavefront,
    compute_wavefront_map,
    full_wavefront_analysis,
    simulate_interferogram,
    zernike_decompose,
)
from optics.zernike.zernike import (
    wavefront_to_zernike,
    zernike_annular,
    zernike_coeffs,
    zernike_evaluate,
    zernike_fit,
    zernike_fringe,
    zernike_names,
    zernike_radial,
    zernike_standard,
    zernike_to_wavefront,
)

WL = 587.56e-9


def disk_quadrature(eps=0.0, n_r=40, n_t=64):
    """Points and weights averaging over eps <= rho <= 1 (weights sum to 1)."""
    x, w = np.polynomial.legendre.leggauss(n_r)
    r = eps + (1 - eps) * (x + 1) / 2
    wr = w * (1 - eps) / 2 * r
    t = np.linspace(0, 2 * math.pi, n_t, endpoint=False)
    R, T = np.meshgrid(r, t)
    W = np.meshgrid(wr, t)[0] / n_t
    return R.ravel(), T.ravel(), (W / W.sum()).ravel()


class TestZernikePolynomials:

    def test_noll_order_and_closed_forms(self):
        rho = np.array([0.0, 0.3, 0.7, 1.0])
        th = np.array([0.2, 1.1, -2.0, 3.0])
        expected = {
            1: np.ones_like(rho),
            2: 2 * rho * np.cos(th),
            3: 2 * rho * np.sin(th),
            4: math.sqrt(3) * (2 * rho**2 - 1),
            5: math.sqrt(6) * rho**2 * np.sin(2 * th),
            6: math.sqrt(6) * rho**2 * np.cos(2 * th),
            7: math.sqrt(8) * (3 * rho**3 - 2 * rho) * np.sin(th),
            8: math.sqrt(8) * (3 * rho**3 - 2 * rho) * np.cos(th),
            9: math.sqrt(8) * rho**3 * np.sin(3 * th),
            10: math.sqrt(8) * rho**3 * np.cos(3 * th),
            11: math.sqrt(5) * (6 * rho**4 - 6 * rho**2 + 1),
            22: math.sqrt(7) * (20 * rho**6 - 30 * rho**4 + 12 * rho**2 - 1),
        }
        for j, z in expected.items():
            np.testing.assert_allclose(zernike_standard(j, rho, th), z, atol=1e-12)

    def test_fringe_order(self):
        rho = np.array([0.2, 0.6, 0.9])
        th = np.array([0.4, -1.3, 2.2])
        expected = {
            1: np.ones_like(rho),
            2: rho * np.cos(th),
            3: rho * np.sin(th),
            4: 2 * rho**2 - 1,
            5: rho**2 * np.cos(2 * th),
            6: rho**2 * np.sin(2 * th),
            7: (3 * rho**2 - 2) * rho * np.cos(th),
            8: (3 * rho**2 - 2) * rho * np.sin(th),
            9: 6 * rho**4 - 6 * rho**2 + 1,
            10: rho**3 * np.cos(3 * th),
            11: rho**3 * np.sin(3 * th),
            12: (4 * rho**2 - 3) * rho**2 * np.cos(2 * th),
            16: 20 * rho**6 - 30 * rho**4 + 12 * rho**2 - 1,
        }
        for j, z in expected.items():
            np.testing.assert_allclose(zernike_fringe(j, rho, th), z, atol=1e-12)

    def test_standard_set_is_orthonormal_over_the_disk(self):
        r, t, w = disk_quadrature()
        Z = np.array([zernike_standard(j, r, t) for j in range(1, 29)])
        gram = (Z * w) @ Z.T
        np.testing.assert_allclose(gram, np.eye(28), atol=1e-12)

    def test_radial_polynomial_is_zero_for_odd_n_minus_m(self):
        assert np.all(zernike_radial(3, 0, np.array([0.5, 1.0])) == 0)
        assert np.all(zernike_radial(2, 4, np.array([0.5])) == 0)

    @pytest.mark.parametrize("eps", [0.25, 0.5])
    def test_annular_set_is_orthonormal_over_the_annulus(self, eps):
        r, t, w = disk_quadrature(eps)
        Z = np.array([zernike_annular(j, r, t, eps) for j in range(1, 23)])
        gram = (Z * w) @ Z.T
        np.testing.assert_allclose(gram, np.eye(22), atol=1e-9)

    @pytest.mark.parametrize("eps", [0.2, 0.5])
    def test_annular_matches_mahajan(self, eps):
        rho = np.linspace(eps, 1.0, 7)
        th = np.zeros_like(rho)
        e2 = eps * eps
        defocus = math.sqrt(3) * (2 * rho**2 - 1 - e2) / (1 - e2)
        spherical = math.sqrt(5) * (
            6 * rho**4 - 6 * (1 + e2) * rho**2 + 1 + 4 * e2 + e2 * e2
        ) / (1 - e2) ** 2
        np.testing.assert_allclose(zernike_annular(4, rho, th, eps), defocus, atol=1e-9)
        np.testing.assert_allclose(zernike_annular(11, rho, th, eps), spherical, atol=1e-9)

    def test_annular_reduces_to_standard_without_obscuration(self):
        rho, th = np.array([0.1, 0.8]), np.array([0.3, 2.0])
        for j in (4, 8, 11):
            np.testing.assert_allclose(zernike_annular(j, rho, th, 0.0),
                                       zernike_standard(j, rho, th))

    def test_invalid_arguments(self):
        with pytest.raises(ValueError):
            zernike_standard(0, np.array([0.5]), np.array([0.0]))
        with pytest.raises(ValueError):
            zernike_fringe(0, np.array([0.5]), np.array([0.0]))
        with pytest.raises(ValueError):
            zernike_annular(4, np.array([0.5]), np.array([0.0]), 1.0)
        with pytest.raises(ValueError):
            zernike_fit(np.zeros(3), np.zeros(3), np.zeros(3), 3, "hexagonal")


class TestFitting:

    @pytest.mark.parametrize("kind", ["standard", "fringe"])
    def test_fit_recovers_known_coefficients(self, kind):
        rng = np.random.default_rng(3)
        c = rng.normal(0, 1e-7, 15)
        x, y = rng.uniform(-1, 1, (2, 3000))
        rho, th = np.hypot(x, y), np.arctan2(y, x)
        w = zernike_evaluate(c, rho, th, kind)
        w[rho > 1] = 5.0  # outside the pupil: ignored
        w[:10] = np.nan  # missing samples: ignored
        np.testing.assert_allclose(zernike_fit(w, x, y, 15, kind), c, atol=1e-18)

    def test_wavefront_summary(self):
        c = np.zeros(11)
        c[3], c[7], c[10] = 2e-7, -1e-7, 5e-8  # defocus, coma x, spherical
        W, X, Y = zernike_to_wavefront(c, grid_size=101)
        inside = np.hypot(X, Y) <= 1
        assert np.all(W[~inside] == 0)
        out = wavefront_to_zernike(W, X, Y, num_terms=11)
        np.testing.assert_allclose(out["coefficients"], c, atol=1e-15)
        assert out["rms_wavefront"] == pytest.approx(math.sqrt(2e-7**2 + 1e-7**2 + 5e-8**2))
        assert out["pv_wavefront"] == pytest.approx(np.ptp(W[inside]))
        assert out["primary_aberrations"]["defocus"] == pytest.approx(2e-7)
        assert out["primary_aberrations"]["coma_x"] == pytest.approx(-1e-7)
        assert out["primary_aberrations"]["spherical_primary"] == pytest.approx(5e-8)

    def test_names_and_index_table(self):
        names = zernike_names(11)
        assert names[3] == "Defocus" and names[10] == "Spherical Primary"
        assert zernike_names(9, "fringe")[8] == "Spherical Primary"
        table = zernike_coeffs(22)
        assert (table[21]["n"], table[21]["m"]) == (6, 0)
        assert table[21]["name"] == "Secondary Spherical"
        assert zernike_names(40)[36].startswith("Z(n=")


def mirror(conic, semi, image_shift=0.0, radius=-1.0):
    """Mirror at the stop, object at infinity, image at the paraxial focus
    plus image_shift (m, along the reflected beam)."""
    return ld.to_system(LensData(
        surfaces=[LensSurface(label="M1", radius=radius, conic=conic, material="MIRROR",
                              is_stop=True, semi_diameter=semi,
                              thickness=radius / 2 - image_shift)],
        object_distance=None, field_angle=math.radians(0.05), wavelengths=[WL],
        analysis_settings={"wavelength": WL},
    ))


class TestWavefront:

    # f = 0.5 m, aperture semi-diameter 0.05 m: u ~ 0.1, W020 = dz u^2 / 2
    W020 = 0.25 * WL
    DZ = W020 / (0.1**2 / 2)

    def test_defocus_rms_pv_and_exact_strehl(self):
        wf = compute_wavefront_map(mirror(-1.0, 0.05, self.DZ), num_rays=41,
                                   field_fraction=0.0)
        assert wf.opd_rms == pytest.approx(self.W020 / math.sqrt(12), rel=0.01)
        assert wf.opd_pv == pytest.approx(self.W020, rel=0.01)
        phi = 2 * math.pi * self.W020 / WL
        assert wf.strehl == pytest.approx((math.sin(phi / 2) / (phi / 2)) ** 2, rel=0.01)
        assert wf.wavelength == WL

    def test_defocus_zernike_coefficient(self):
        z = zernike_decompose(mirror(-1.0, 0.05, self.DZ), num_rays=41, num_terms=16,
                              field_fraction=0.0)
        c = np.array(z.coefficients)
        # W020 rho^2 = W020 / (2 sqrt 3) Z4 + W020 / 2 Z1
        assert abs(c[3]) == pytest.approx(self.W020 / (2 * math.sqrt(3)), rel=0.01)
        assert np.max(np.abs(np.delete(c, [0, 3]))) < 0.01 * abs(c[3])
        assert z.fit_residual_rms < 1e-3 * z.rms_wavefront
        assert len(z.names) == 16

    def test_spherical_mirror_w040(self):
        h, R = 0.025, -1.0
        s = mirror(0.0, h, radius=R)
        w040 = h**4 / (4 * abs(R) ** 3)
        seidel = compute_seidel_from_wavefront(s)
        assert abs(seidel.spherical) == pytest.approx(w040, rel=1e-6)
        z = zernike_decompose(s, num_rays=41, num_terms=16, field_fraction=0.0)
        assert abs(z.coefficients[10]) == pytest.approx(w040 / (6 * math.sqrt(5)), rel=0.02)
        # W131 = S2 / 2 (Welford)
        sums = rt.seidel_sums(s)
        assert seidel.coma == pytest.approx(sums.S2 / 2)

    def test_interferogram_of_a_perfect_wavefront_is_the_tilt_fringes(self):
        s = mirror(-1.0, 0.05)
        ig = simulate_interferogram(s, num_rays=33, tilt_x=3.0, defocus=0.5)
        I = np.array(ig.intensity)
        g = np.linspace(-1, 1, ig.resolution)
        X, Y = np.meshgrid(g, g)
        inside = np.hypot(X, Y) < 0.95
        ref = 0.5 * (1 + np.cos(2 * math.pi * (3.0 * X + 0.5 * (X**2 + Y**2))))
        np.testing.assert_allclose(I[inside], ref[inside], atol=1e-6)
        assert ig.fringe_count >= 6

    def test_full_analysis_is_consistent(self):
        res = full_wavefront_analysis(mirror(-1.0, 0.05, self.DZ), num_rays=21,
                                      num_terms=11, field_fraction=0.0)
        assert res.rms_wavefront == res.wavefront_map.opd_rms
        assert res.strehl == res.wavefront_map.strehl
        assert res.is_diffraction_limited == (res.strehl >= 0.8)
        assert res.zernike is not None and res.interferogram is not None
