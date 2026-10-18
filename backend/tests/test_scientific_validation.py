"""
Scientific validation against results computed independently of the engine.

Every expected value here comes from a closed-form textbook result or from
a direct geometric calculation written out in the test, never from the
module under test.

References:
- Thick-lens (lensmaker) power and back focal length: Hecht, Optics, 5th ed., 6.2.
- Airy pattern: first dark ring 0.61 lambda / NA, 83.8 % encircled energy
  inside it; MTF of a circular pupil 2/pi (acos v - v sqrt(1 - v^2)),
  0.391 at half the cutoff 2 NA / lambda (Born & Wolf 8.5; Goodman,
  Introduction to Fourier Optics, 6.3).
"""

import math

import numpy as np
import pytest

from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Mirror, Object, ImagePlane, AnalysisSettings,
)
from optics.materials import refractive_index
from optics.raytrace import first_order
from optics import pupil as pp
from optics.diffraction import airy_disk_radius, encircled_energy, mtf

WL = 550e-9


def settings():
    return AnalysisSettings(num_rays=11, ray_types=["chief", "marginal", "fill"],
                            aperture_fraction=1.0, wavelength=WL)


def thick_lens(r1=0.1, r2=-0.1, t=0.01):
    far = 1.0e5
    return OpticalSystem(
        components=[ThickLens(id="L1", position=far, radius1=r1, radius2=r2, thickness=t,
                              aperture_diameter=0.02, material="N-BK7")],
        wavelengths=[WL], object=Object(position=0.0, height=1.0),
        image_plane=ImagePlane(position=far + 0.1), analysis_settings=settings())


def ideal_lens_at_infinity(f=0.1, diameter=0.02, defocus=0.0):
    far = 1.0e5
    return OpticalSystem(
        components=[ThinLens(id="L1", position=far, focal_length=f, aperture_diameter=diameter)],
        wavelengths=[WL], object=Object(position=0.0, height=1.0),
        image_plane=ImagePlane(position=far + f + defocus), analysis_settings=settings())


class TestThickLensFirstOrder:

    @pytest.mark.parametrize("r1, r2, t", [(0.1, -0.1, 0.01), (0.05, 1e12, 0.005),
                                           (0.05, 0.1, 0.004), (-0.2, -0.08, 0.006)])
    def test_efl_and_bfl_match_lensmaker(self, r1, r2, t):
        n = refractive_index("N-BK7", WL)
        c1, c2 = 1.0 / r1, 1.0 / r2
        phi = (n - 1.0) * (c1 - c2 + (n - 1.0) * t * c1 * c2 / n)
        efl = 1.0 / phi
        bfl = efl * (1.0 - (n - 1.0) * t * c1 / n)
        fo = first_order(thick_lens(r1, r2, t))
        assert fo.efl == pytest.approx(efl, rel=1e-9)
        assert fo.bfl == pytest.approx(bfl, rel=1e-9)


class TestConjugates:

    def test_two_lens_relay(self):
        # L1 (f 50 mm) at 100 mm images the object at 0 to 200 mm; L2 (f 50
        # mm) at 150 mm sees a virtual object 50 mm behind it:
        # 1/s' = 1/50 + 1/50 -> s' = 25 mm, image at 175 mm, m = (-1)(-0.5).
        system = OpticalSystem(
            components=[ThinLens(id="L1", position=0.1, focal_length=0.05, aperture_diameter=0.025),
                        ThinLens(id="L2", position=0.15, focal_length=0.05, aperture_diameter=0.025)],
            wavelengths=[WL], object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.175), analysis_settings=settings())
        fo = first_order(system)
        assert fo.image_z == pytest.approx(0.175, rel=1e-12)
        assert fo.image_height == pytest.approx(-0.005, rel=1e-12)


class TestWavefront:

    def test_ideal_lens_is_aberration_free(self):
        g = pp.wavefront_grid(ideal_lens_at_infinity(), 0.0, 32)
        assert g.rms / WL < 1e-6     # round-off at 1e5 m coordinates
        assert pp.strehl_ratio(g) == pytest.approx(1.0, abs=1e-9)

    def test_paraboloid_on_axis_is_aberration_free(self):
        far = 1.0e5
        system = OpticalSystem(
            components=[Mirror(id="M1", position=0.5, angle=0.0, width=0.1, radius=-1.0, conic=-1.0)],
            wavelengths=[WL], object=Object(position=-far, height=1.0),
            image_plane=ImagePlane(position=0.0), analysis_settings=settings())
        g = pp.wavefront_grid(system, 0.0, 32)
        assert g.rms / WL < 1e-6

    def test_defocus_matches_exact_geometry(self):
        """
        A perfect converging wave (focus F at distance f behind the lens) seen
        from an image plane moved by delta: the OPD is the difference in
        distance from each pupil point X to F and to the reference point
        Q = F + delta, relative to the chief ray, with the reference sphere
        through the pupil centre. Exactly: W(X) = (|X - Q| - |Q|) - (|X - F| - |F|)
        to first order in the path along the ray; it is evaluated here
        directly, with the pupil uniform in lens-plane coordinates.
        """
        f, a, delta = 0.1, 0.01, 50e-6
        g = pp.wavefront_grid(ideal_lens_at_infinity(f, 2 * a, delta), 0.0, 33)

        x = np.linspace(-a, a, 33)
        X, Y = np.meshgrid(x, x)
        inside = X ** 2 + Y ** 2 <= a * a * (1 + 1e-12)
        r = np.hypot(X, Y)
        # sign: W = OPL(chief) - OPL(ray) to the reference sphere about Q
        W = -((np.hypot(r, f + delta) - (f + delta)) - (np.hypot(r, f) - f))
        W = np.where(inside, W, np.nan)
        rms_exact = np.nanstd(W)
        assert g.rms == pytest.approx(rms_exact, rel=0.02)


class TestDiffractionConstants:

    def test_airy_radius(self):
        assert airy_disk_radius(na=0.1, wavelength=WL) == pytest.approx(0.61 * WL / 0.1, rel=1e-3)

    def test_energy_inside_first_dark_ring(self):
        na = 0.1
        # first zero of J1 is 3.8317; r = 3.8317 lambda / (2 pi NA)
        r0 = 3.8317 * WL / (2 * math.pi * na)
        ee = encircled_energy(None, na, WL, radius=r0)["energy"][0]
        assert ee == pytest.approx(0.838, abs=1e-3)

    def test_mtf_at_half_cutoff(self):
        na = 0.1
        fc = 2 * na / WL
        res = mtf(None, frequencies=np.array([0.5 * fc]), wavelength=WL, na=na)
        assert res["f_c"] == pytest.approx(fc, rel=1e-12)
        assert float(res["mtf"][0]) == pytest.approx(0.391, abs=1e-3)

    def test_fft_mtf_of_a_perfect_lens_matches_the_analytic_curve(self):
        g = pp.wavefront_grid(ideal_lens_at_infinity(), 0.0, 64)
        m = pp.mtf(g)
        fc = 2 * g.na_image / WL
        for v in (0.1, 0.3, 0.5, 0.7):
            analytic = 2 / math.pi * (math.acos(v) - v * math.sqrt(1 - v * v))
            assert pp.mtf_at(m, v * fc, "tangential") == pytest.approx(analytic, abs=0.01)
