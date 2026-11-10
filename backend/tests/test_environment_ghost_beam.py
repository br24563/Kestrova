"""
Environment, ghosts and Gaussian beams on the prescription, against closed
forms:

- the air index of Edlen / Birch and Downs: n - 1 = 2.718e-4 at 633 nm,
  20 C, 101 325 Pa (dry air), dn/dT = -0.93e-6 /K and dn/dP = 2.7e-9 /Pa;
- a thin singlet's focal length scales as k (n0 - 1) / (n_T - 1) with its
  glass growth k = 1 + alpha dT and relative index n_T, and a housing whose
  CTE equals the lens's thermal focal coefficient keeps it in focus;
- in vacuum the relative index becomes n_cat n_air: f_vac / f_air =
  (n_cat - 1) / (n_cat n_air - 1);
- a plate of thickness t in a converging beam puts its ghost 2 t / n before
  the focus (the extra 2 t of glass uses up 2 t / n of the convergence),
  with power R^2 (bare, near normal incidence) or R_coat R_bare;
- a Gaussian beam through a thin lens (S. A. Self, Appl. Opt. 22, 658
  (1983)): s' = f + (s - f) f^2 / ((s - f)^2 + z_R^2) and
  w0' = w0 f / sqrt((s - f)^2 + z_R^2).
"""

import math

import numpy as np
import pytest

from optics import raytrace as rt
from optics.beam_lens import beam_through, system_matrix
from optics.coating_spec import CoatingSpec
from optics.environment import (
    air_index,
    environment_lens,
    environment_system,
    environment_table,
    glass_index,
)
from optics.ghost_trace import ghost_analysis
from optics.lens_data import LensData, LensSurface, to_system
from optics.materials import refractive_index
from optics.models import AnalysisSettings
from optics.physical.gaussian import ABCDMatrix
from optics.thermal.material import get_thermal_properties

WL = 587.56e-9


def singlet(r=0.1, t=0.001, back=0.0985, glass="N-BK7", semi=0.0025) -> LensData:
    return LensData(
        surfaces=[
            LensSurface(radius=r, thickness=t, material=glass, semi_diameter=semi, is_stop=True),
            LensSurface(radius=-r, thickness=back, semi_diameter=semi),
        ],
        object_distance=None, wavelengths=[WL],
        analysis_settings=AnalysisSettings(wavelength=WL),
    )


class TestAir:
    def test_edlen_values(self):
        n = air_index(633e-9, 20.0, 101325.0)
        assert n - 1 == pytest.approx(2.718e-4, abs=3e-7)
        dT = (air_index(633e-9, 21.0, 101325.0) - air_index(633e-9, 19.0, 101325.0)) / 2
        assert dT == pytest.approx(-0.93e-6, rel=0.03)
        dP = (air_index(633e-9, 20.0, 102325.0) - air_index(633e-9, 20.0, 100325.0)) / 2000
        assert dP == pytest.approx(2.7e-9, rel=0.03)
        assert air_index(633e-9, 20.0, 0.0) == 1.0


class TestEnvironment:
    def test_reference_conditions_change_nothing(self):
        lens = singlet()
        a = rt.first_order(to_system(lens)).efl
        b = rt.first_order(environment_system(lens)).efl
        assert b == a

    def test_thin_singlet_focal_length_follows_the_glass(self):
        lens = singlet()
        T = 60.0
        k = 1 + get_thermal_properties("N-BK7").CTE * 1e-6 * (T - 20)
        n0 = refractive_index("N-BK7", WL)
        nT = glass_index("N-BK7", WL, T, 101325.0)
        f0 = rt.first_order(to_system(lens)).efl
        fT = rt.first_order(environment_system(lens, T)).efl
        assert fT / f0 == pytest.approx(k * (n0 - 1) / (nT - 1), rel=2e-6)

    def test_matched_housing_keeps_focus(self):
        # image plane at focus: then a housing growing like the focal length
        # keeps it there
        lens = singlet()
        lens.surfaces[1].thickness = rt.first_order(to_system(lens)).bfl
        # the back focal distance's thermal coefficient (per K, over 1 K)
        b0 = rt.first_order(to_system(lens)).bfl
        b1 = rt.first_order(environment_system(lens, 21.0)).bfl
        beta = (b1 - b0) / b0
        # focus shift is measured from the image plane: compare with 20 C
        def change(**kw):
            # first order in dT: the air index is not linear in T over tens of K
            rows = environment_table(lens, [20.0, 21.0], **kw)
            return rows[1]["focus_shift"] - rows[0]["focus_shift"]

        rigid = change()
        matched = change(mount_cte=beta * 1e6)
        assert abs(rigid) > 1e-8
        assert abs(matched) < 0.02 * abs(rigid)

    def test_vacuum(self):
        lens = singlet()
        n = refractive_index("N-BK7", WL)
        na = air_index(WL, 20.0, 101325.0)
        fa = rt.first_order(to_system(lens)).efl
        fv = rt.first_order(environment_system(lens, 20.0, 0.0)).efl
        assert fv / fa - 1 == pytest.approx((n - 1) / (n * na - 1) - 1, rel=2e-3)

    def test_geometry_scales_with_the_glass(self):
        lens = singlet()
        hot = environment_lens(lens, 70.0)
        k = 1 + get_thermal_properties("N-BK7").CTE * 1e-6 * 50
        assert hot.surfaces[0].radius == pytest.approx(0.1 * k)
        assert hot.surfaces[1].radius == pytest.approx(-0.1 * k)
        assert hot.surfaces[0].thickness == pytest.approx(0.001 * k)
        assert hot.surfaces[1].thickness == pytest.approx(0.0985)  # rigid mount

    def test_model_glass_needs_thermal_data(self):
        lens = singlet(glass="MODEL:1.5168:64.17")
        with pytest.raises(ValueError, match="no CTE|dn/dT"):
            environment_system(lens, 40.0)


def plate_in_beam(coat_back=None) -> LensData:
    """An f/20 singlet with a 5 mm plate 40 mm behind it; image at focus."""
    lens = singlet(back=0.04)
    rows = list(lens.surfaces) + [
        LensSurface(thickness=0.005, material="N-BK7", semi_diameter=0.01),
        LensSurface(thickness=0.05, semi_diameter=0.01, coating=coat_back),
    ]
    out = LensData(surfaces=rows, object_distance=None, wavelengths=[WL],
                   analysis_settings=AnalysisSettings(wavelength=WL))
    fo = rt.first_order(to_system(out))
    out.surfaces[-1].thickness += fo.image_z - rt.build_sequence(to_system(out)).image_z
    return out


class TestGhosts:
    def test_plate_ghost_focus_and_power(self):
        lens = plate_in_beam()
        out = ghost_analysis(to_system(lens), field=0, rings=6)
        n = refractive_index("N-BK7", WL)
        assert len(out["ghosts"]) == 6  # 4 surfaces: C(4, 2)
        g = next(g for g in out["ghosts"] if g["surfaces"] == [3, 2])
        assert g["focus_shift"] == pytest.approx(-2 * 0.005 / n, rel=0.02)
        R = ((n - 1) / (n + 1)) ** 2
        assert g["power"] == pytest.approx(R * R, rel=0.01)
        assert g["fraction"] == 1.0

    def test_coating_lowers_the_ghost(self):
        qw = CoatingSpec.quarter_wave("MgF2", WL)
        n = refractive_index("N-BK7", WL)
        n1 = refractive_index("MgF2", WL)
        out = ghost_analysis(to_system(plate_in_beam(qw)), field=0, rings=6)
        g = next(g for g in out["ghosts"] if g["surfaces"] == [3, 2])
        R_bare = ((n - 1) / (n + 1)) ** 2
        R_coat = ((n - n1**2) / (n + n1**2)) ** 2
        assert g["power"] == pytest.approx(R_coat * R_bare, rel=0.01)

    def test_ranked_and_refuses_ideal_lenses(self):
        out = ghost_analysis(to_system(plate_in_beam()), field=0, rings=4)
        rel = [g["relative_irradiance"] for g in out["ghosts"]]
        assert rel == sorted(rel, reverse=True)
        ideal = LensData(surfaces=[LensSurface(surface_type="paraxial", focal_length=0.1,
                                               thickness=0.1, semi_diameter=0.01, is_stop=True)],
                         object_distance=None, wavelengths=[WL])
        with pytest.raises(ValueError, match="real surfaces"):
            ghost_analysis(to_system(ideal))


class TestBeams:
    def ideal(self, L=0.15):
        return to_system(LensData(
            surfaces=[LensSurface(surface_type="paraxial", focal_length=0.1, thickness=L,
                                  semi_diameter=0.01, is_stop=True)],
            object_distance=None, wavelengths=[1064e-9],
            analysis_settings=AnalysisSettings(wavelength=1064e-9)))

    @pytest.mark.parametrize("s", [0.0, 0.05, 0.1, 0.3])
    def test_thin_lens_matches_self(self, s):
        f, w0, wl, L = 0.1, 0.5e-3, 1064e-9, 0.15
        zr = math.pi * w0**2 / wl
        out = beam_through(self.ideal(L), w0, s, wl)
        sp = f + (s - f) * f**2 / ((s - f) ** 2 + zr**2)
        w0p = w0 * f / math.sqrt((s - f) ** 2 + zr**2)
        assert out["waist_radius"] == pytest.approx(w0p, rel=1e-9)
        assert out["waist_position"] == pytest.approx(sp - L, rel=1e-9, abs=1e-12)

    def test_beam_quality_factor(self):
        f, w0, wl, s, m2 = 0.1, 0.5e-3, 1064e-9, 0.2, 1.8
        zr = math.pi * w0**2 / (m2 * wl)
        out = beam_through(self.ideal(), w0, s, wl, m2=m2)
        w0p = w0 * f / math.sqrt((s - f) ** 2 + zr**2)
        assert out["waist_radius"] == pytest.approx(w0p, rel=1e-9)
        assert out["divergence"] == pytest.approx(m2 * wl / (math.pi * w0p), rel=1e-9)

    def test_thick_lens_matrix_matches_the_gaussian_module(self):
        lens = singlet(r=0.05, t=0.006, back=0.08)
        system = to_system(lens)
        n = refractive_index("N-BK7", WL)
        m = ABCDMatrix.free_space(0.08) @ ABCDMatrix.thick_lens(0.05, -0.05, 0.006, n)
        np.testing.assert_allclose(system_matrix(system, WL), [m.A, m.B, m.C, m.D],
                                   rtol=1e-10, atol=1e-13)


def test_polychromatic_image_simulation():
    from optics.imaging import SensorConfig, simulate_image

    mono = to_system(singlet())
    poly = mono.model_copy(update={"wavelengths": [486e-9, 587.56e-9, 656e-9]})
    kw = dict(sensor=SensorConfig(resolution=32, pixel_pitch=5e-6), with_noise=False)
    a = simulate_image(mono, polychromatic=True, **kw).image
    b = simulate_image(poly, polychromatic=False, **kw).image
    c = simulate_image(poly, polychromatic=True, **kw).image
    np.testing.assert_allclose(a, b, atol=1e-12)  # one wavelength: no change
    assert not np.allclose(b, c)  # the singlet's colour blurs the image


def test_endpoints():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    lens = singlet().model_dump()
    r = client.post("/api/lens/environment",
                    json={"lens": lens, "temperatures": [0, 20, 40], "system_at": 40})
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert [row["temperature"] for row in rows] == [0, 20, 40]
    assert r.json()["system"]["environment"]["temperature"] == 40
    sys_ = to_system(plate_in_beam()).model_dump()
    g = client.post("/api/analyze/ghost-trace", json={"system": sys_, "rings": 3, "top": 2})
    assert g.status_code == 200 and len(g.json()["ghosts"]) == 2
    b = client.post("/api/analyze/gaussian-beam",
                    json={"system": sys_, "waist_radius": 1e-3, "waist_distance": 0.0})
    assert b.status_code == 200 and b.json()["waist_radius"] > 0
