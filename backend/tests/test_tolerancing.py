"""
Tests for fast tolerancing of a prescription (optics.tolerancing) and for
perturbed glasses (optics.materials), against independent references:

- a perturbed glass has nd and Vd shifted exactly by dn and dVd and the
  base glass's partial dispersion P_g,F;
- DLF of N fringes changes the exact conic sag at the test radius by
  N lambda / 2;
- a plane-parallel plate tilted by th shifts the axial ray by
  t sin th (1 - cos th / sqrt(n^2 - sin^2 th));
- an ideal lens decentered by d moves the image of an object at infinity by
  d; a fold mirror tilted by th deviates the reflected ray by 2 th;
- the fast (model) prediction agrees with an exact Monte Carlo that traces
  and refocuses every trial; the model reproduces the traced wavefront at
  the analysed limits exactly;
- sampled distributions have their stated moments.
"""

import math

import numpy as np
import pytest
from pydantic import ValidationError

from optics import lens_data as ld
from optics import raytrace as rt
from optics import tolerancing as tl
from optics.lens_data import LensData, LensSurface, Solve
from optics.materials import (
    C_LINE,
    D_LINE,
    F_LINE,
    G_LINE,
    abbe_number,
    get_material,
    parse_perturbed_glass,
    perturbed_glass_name,
    refractive_index,
)

WL = 587.56e-9


def doublet():
    """Cemented N-BK7 / N-SF5 achromat, f ~ 100 mm, f/5, +-1 degree."""
    return LensData(
        surfaces=[
            LensSurface(label="STO", is_stop=True, semi_diameter=0.01, thickness=0.002),
            LensSurface(element="D", radius=0.06131, thickness=0.006, material="N-BK7"),
            LensSurface(element="D", radius=-0.04385, thickness=0.0025, material="N-SF5"),
            LensSurface(element="D", radius=-0.12886, thickness=0.095,
                        solves={"thickness": Solve(kind="marginal_height")}),
        ],
        object_distance=None, field_angle=math.radians(1),
        wavelengths=[F_LINE, D_LINE, C_LINE], analysis_settings={"wavelength": D_LINE},
    )


def chief_image(lens):
    s = ld._merit_system(lens)
    b, _, _ = rt.trace_field_rays(s, 0.0, 0.0, np.zeros(1), np.zeros(1))
    assert b.valid[0]
    return b.image[0]


def ideal_then(*rest, f=0.1, gap=0.05):
    return tl.freeze(LensData(
        surfaces=[LensSurface(label="L", surface_type="paraxial", focal_length=f,
                              is_stop=True, semi_diameter=0.005, thickness=gap), *rest],
        object_distance=None, field_angle=0.01, wavelengths=[WL],
        analysis_settings={"wavelength": WL},
    ))


class TestPerturbedGlass:

    @pytest.mark.parametrize("base", ["N-BK7", "N-SF6", "MODEL:1.6:40"])
    def test_exact_nd_vd_and_partial_dispersion(self, base):
        name = perturbed_glass_name(base, 4e-4, -0.7)
        assert parse_perturbed_glass(name) == (base, 4e-4, -0.7)
        assert refractive_index(name, D_LINE) - refractive_index(base, D_LINE) == \
            pytest.approx(4e-4, abs=1e-12)
        assert abbe_number(name) - abbe_number(base) == pytest.approx(-0.7, abs=1e-9)

        def pgf(m):
            return (refractive_index(m, G_LINE) - refractive_index(m, F_LINE)) / (
                refractive_index(m, F_LINE) - refractive_index(m, C_LINE))

        assert pgf(name) == pytest.approx(pgf(base), abs=1e-12)
        rec = get_material(name)
        assert rec.nd == pytest.approx(refractive_index(base, D_LINE) + 4e-4)

    def test_malformed(self):
        assert parse_perturbed_glass("N-BK7") is None
        with pytest.raises(ValueError):
            parse_perturbed_glass("PERTURB:N-BK7:x")
        with pytest.raises(ValueError):
            refractive_index(perturbed_glass_name("N-BK7", 0.0, -100.0))


class TestPerturbations:

    @pytest.mark.parametrize("deg", [2.0, -5.0])
    def test_element_tilt_of_a_plate(self, deg):
        lens = ideal_then(
            LensSurface(label="P1", radius=0, thickness=0.01, material="N-BK7", element="P"),
            LensSurface(label="P2", radius=0, thickness=0.04),
        )
        th = math.radians(deg)
        p = chief_image(tl.apply(lens, [(tl.Tolerance(kind="BTX", surface=1, limit=1), th)]))
        n = refractive_index("N-BK7", WL)
        shift = 0.01 * math.sin(th) * (1 - math.cos(th) / math.sqrt(n * n - math.sin(th) ** 2))
        assert abs(p[1] - chief_image(lens)[1]) == pytest.approx(abs(shift), rel=1e-9)

    def test_combined_tilts_restore_the_axis(self):
        # tilting a plate about x and y and decentering it: after the inverse
        # breaks a ray far behind leaves along the original axis
        lens = ideal_then(
            LensSurface(label="P1", radius=0, thickness=0.01, material="N-BK7", element="P"),
            LensSurface(label="P2", radius=0, thickness=0.04),
        )
        tols = [(tl.Tolerance(kind="BTX", surface=1, limit=1), 0.03),
                (tl.Tolerance(kind="BTY", surface=1, limit=1), -0.02),
                (tl.Tolerance(kind="DLX", surface=1, limit=1), 1e-4),
                (tl.Tolerance(kind="DSY", surface=2, limit=1), 2e-4)]
        moved = tl.apply(lens, tols)
        seq = rt.build_sequence(ld._merit_system(moved))
        np.testing.assert_allclose(seq.image_rotation, np.eye(3), atol=1e-12)
        assert seq.image_origin[0] == pytest.approx(0.0, abs=1e-15)
        assert seq.image_origin[1] == pytest.approx(0.0, abs=1e-15)
        assert sum(s.thickness for s in moved.surfaces) == pytest.approx(
            sum(s.thickness for s in lens.surfaces))

    @pytest.mark.parametrize("d", [1e-4, -3e-4])
    def test_element_decenter_of_an_ideal_lens(self, d):
        lens = ideal_then(LensSurface(label="I", radius=0, thickness=0.0))
        p = chief_image(tl.apply(lens, [(tl.Tolerance(kind="DLY", surface=0, last_surface=0,
                                                      limit=1), d)]))
        assert p[1] - chief_image(lens)[1] == pytest.approx(d, rel=1e-9)

    def test_fold_mirror_tilt_deviates_by_twice_the_angle(self):
        lens = ideal_then(LensSurface(label="M", radius=0, material="MIRROR", thickness=-0.1),
                          f=0.2, gap=0.1)
        th = math.radians(0.5)
        q = chief_image(tl.apply(lens, [(tl.Tolerance(kind="TRX", surface=1, limit=1), th)]))
        assert abs(q[1] - chief_image(lens)[1]) == pytest.approx(0.1 * math.tan(2 * th),
                                                                rel=1e-9)

    @pytest.mark.parametrize("conic", [0.0, -0.6])
    def test_dlf_changes_the_exact_sag_by_n_half_waves(self, conic):
        lens = tl.freeze(doublet())
        lens.surfaces[1].conic = conic
        semi = 0.01
        t = tl.Tolerance(kind="DLF", surface=1, limit=1, test_diameter=2 * semi)
        R0 = lens.surfaces[1].radius
        R = tl.apply(lens, [(t, -2.5)]).surfaces[1].radius

        def sag(R):
            c = 1 / R
            return c * semi**2 / (1 + math.sqrt(1 - (1 + conic) * c * c * semi**2))

        assert sag(R) - sag(R0) == pytest.approx(-2.5 * 546.07e-9 / 2, rel=1e-9)

    def test_scalar_tolerances(self):
        lens = tl.freeze(doublet())
        out = tl.apply(lens, [(tl.Tolerance(kind="DLT", surface=1, limit=1), 1e-4),
                              (tl.Tolerance(kind="DLR", surface=3, limit=1), 2e-3),
                              (tl.Tolerance(kind="DLN", surface=2, limit=1), 3e-4),
                              (tl.Tolerance(kind="DLV", surface=2, limit=1), 0.5),
                              (tl.Tolerance(kind="DLN", surface=2, limit=1), 1e-4)],
                       [(tl.Compensator(), -2e-4)])
        assert out.surfaces[1].thickness == pytest.approx(0.0061)
        assert out.surfaces[3].radius == pytest.approx(-0.12686)
        base, dn, dvd = parse_perturbed_glass(out.surfaces[2].material)
        assert (base, dn, dvd) == ("N-SF5", pytest.approx(4e-4), pytest.approx(0.5))
        assert out.surfaces[3].thickness == pytest.approx(lens.surfaces[3].thickness - 2e-4)

    def test_invalid_tolerances(self):
        lens = tl.freeze(doublet())
        with pytest.raises(ValueError):
            tl.apply(lens, [(tl.Tolerance(kind="DLN", surface=0, limit=1), 1e-4)])
        with pytest.raises(ValueError):
            tl.apply(lens, [(tl.Tolerance(kind="DLR", surface=0, limit=1), 1e-4)])
        with pytest.raises(ValueError):
            tl.apply(lens, [(tl.Tolerance(kind="DLT", surface=9, limit=1), 1e-4)])
        with pytest.raises(ValidationError):
            tl.Tolerance(kind="DLF", surface=1, last_surface=2, limit=1)
        with pytest.raises(ValidationError):
            tl.Tolerance(kind="DLX", surface=2, last_surface=1, limit=1)
        with pytest.raises(ValidationError):
            tl.Compensator(kind="thickness")


@pytest.fixture(scope="module")
def setup():
    """The doublet with 5x the default tolerances, analysed once."""
    lens = doublet()
    tols = [t.model_copy(update={"limit": 5 * t.limit})
            for t in tl.default_tolerances(lens)]
    return lens, tols, tl.analyze(lens, tols, rings=4, trials=20000)


class TestFastAnalysis:

    def test_model_reproduces_the_traced_limits(self, setup):
        lens, tols, a = setup
        nominal = tl.freeze(lens)
        probe = tl._probe(nominal, 4)
        apertures = [s.semi_diameter for s in ld.resolve(lens).surfaces]
        for k in (0, 5, len(tols) - 1):
            t = tols[k]
            traced = tl.residuals(tl.apply(nominal, [(t, t.limit)], apertures=apertures),
                                  probe)
            model = a._r0 + a._A[k] * t.limit + a._B[k] * t.limit**2
            np.testing.assert_allclose(model, traced, atol=1e-12)

    def test_prediction_agrees_with_exact_monte_carlo(self, setup):
        lens, tols, a = setup
        mc = tl.monte_carlo(lens, tols, trials=40, rings=4, seed=5)
        assert mc["failed_trials"] == 0
        # standard error of a 40-trial mean is std / sqrt(40)
        assert abs(mc["mean"] - a.predicted["mean"]) < 3 * a.predicted["std"] / math.sqrt(40)
        assert mc["std"] == pytest.approx(a.predicted["std"], rel=0.35)

    def test_report_is_consistent(self, setup):
        lens, tols, a = setup
        pct = [a.predicted["percentiles"][str(p)] for p in tl.PERCENTILES]
        assert pct == sorted(pct) and pct[0] >= a.nominal_rms * 0.9
        assert len(a.sensitivities) == len(tols)
        assert a.rss_increase == pytest.approx(math.sqrt(sum(
            max(abs(r["change_plus"]), abs(r["change_minus"])) ** 2 for r in a.sensitivities)))
        assert len(a.nominal_field_rms) == 3 and len(a.predicted_fields) == 3
        # composite = sqrt(mean of field mean squares) with equal weights
        assert a.nominal_rms == pytest.approx(
            math.sqrt(np.mean(np.square(a.nominal_field_rms))))
        assert a.compensators[0]["max_abs"] > 0

    def test_inverse_limits_meet_the_budget(self, setup):
        lens, tols, a = setup
        budget = 0.02
        share = budget / math.sqrt(len(tols))
        for k, row in enumerate(tl.inverse_limits(a, budget)[:4]):
            d = row["limit"]
            base = np.linalg.norm(tl._compensate(a._r0[None], a._G, a._limits)[0])

            def change(x):
                r = a._r0 + a._A[k] * x + a._B[k] * x * x
                return np.linalg.norm(tl._compensate(r[None], a._G, a._limits)[0]) - base

            assert max(change(d), change(-d)) == pytest.approx(share, rel=1e-6)

    def test_compensator_limit_is_respected(self):
        lens = doublet()
        tols = [tl.Tolerance(kind="DLT", surface=1, limit=5e-4)]
        a = tl.analyze(lens, tols, [tl.Compensator(limit=1e-5)], rings=3, trials=500)
        assert a.compensators[0]["max_abs"] <= 1e-5 + 1e-15


class TestDistributionsAndDefaults:

    @pytest.mark.parametrize("dist,std", [("uniform", 1 / math.sqrt(3)),
                                          ("end_point", 1.0), ("gaussian", 0.4403)])
    def test_moments(self, dist, std):
        # Gaussian sigma = L/2 truncated at L = 2 sigma: std = 0.8806 sigma
        t = tl.Tolerance(kind="DLT", surface=0, limit=1.0, distribution=dist)
        x = tl._draw(t, np.random.default_rng(1), 60000)
        assert np.max(np.abs(x)) <= 1.0
        assert x.std() == pytest.approx(std, rel=0.02)

    def test_elements_and_default_set(self):
        lens = doublet()
        assert tl.elements(lens) == [(1, 3)]
        kinds = [t.kind for t in tl.default_tolerances(lens)]
        assert kinds.count("DLF") == 3 and kinds.count("DLT") == 2
        assert {"DLX", "DLY", "BTX", "BTY"} <= set(kinds)


class TestApi:

    def test_endpoints(self):
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        lens = doublet().model_dump()
        d = client.post("/api/lens/tolerance/defaults", json={"lens": lens})
        assert d.status_code == 200 and len(d.json()["tolerances"]) == 17
        tols = [{"kind": "DLT", "surface": 1, "limit": 1e-4},
                {"kind": "BTX", "surface": 1, "last_surface": 3, "limit": 3e-4}]
        r = client.post("/api/lens/tolerance", json={"lens": lens, "tolerances": tols,
                                                     "trials": 500, "rings": 3,
                                                     "rss_budget": 0.01})
        assert r.status_code == 200
        body = r.json()
        assert body["units"] == "waves" and len(body["sensitivities"]) == 2
        assert len(body["inverse_limits"]) == 2
        mc = client.post("/api/lens/tolerance/monte-carlo",
                         json={"lens": lens, "tolerances": tols, "trials": 3, "rings": 3})
        assert mc.status_code == 200 and mc.json()["trials"] == 3
        bad = client.post("/api/lens/tolerance", json={
            "lens": lens, "tolerances": [{"kind": "DLN", "surface": 0, "limit": 1e-4}]})
        assert bad.status_code == 400
