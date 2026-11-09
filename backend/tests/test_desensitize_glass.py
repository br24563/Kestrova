"""
Desensitized optimization and glass substitution.

- The desensitizing term equals what the fast tolerancing (validated
  against exact Monte Carlo in test_tolerancing.py) predicts, and adding it
  to the merit trades as the mathematics requires: if A minimises f and B
  minimises f + g, then g(B) <= g(A) and f(B) >= f(A).
- Glass substitution: a thin achromat designed in closed form for
  N-BK7 / N-SF2 (phi1 = phi V1 / (V1 - V2), phi2 = -phi V2 / (V1 - V2)) but
  given N-F2 as its flint finds N-SF2 (or Schott's identical lead glass
  SF2) among the flint's neighbours.
"""

import math

import numpy as np
import pytest

from optics.glass_expert import substitute_glasses
from optics.lens_data import (
    LensData,
    LensSurface,
    MeritSpec,
    Operand,
    optimize,
)
from optics.lens_optimize import merit_report, nearest_catalog_glasses
from optics.materials import MATERIALS, refractive_index
from optics.models import AnalysisSettings
from optics.reference_lenses import SASIAN_TRIPLET
from optics.tolerancing import Tolerance, analyze, sensitivity_residuals

F_, D_, C_ = 486.1327e-9, 587.5618e-9, 656.2725e-9

TOLS = [
    Tolerance(kind="TRX", surface=2, limit=4e-3),
    Tolerance(kind="TRX", surface=3, limit=4e-3),
    Tolerance(kind="DSY", surface=2, limit=1.5e-4),
    Tolerance(kind="DLR", surface=0, limit=5e-5),
]


def triplet(**merit) -> LensData:
    lens = SASIAN_TRIPLET.build().model_copy(deep=True)
    lens.surfaces[2].variables = ["radius"]
    lens.surfaces[5].variables = ["thickness"]
    lens.merit = MeritSpec(kind="wavefront", **merit)
    return LensData.model_validate(lens.model_dump())


class TestDesensitize:
    def test_term_matches_the_fast_tolerancing(self):
        lens = SASIAN_TRIPLET.build()
        s = sensitivity_residuals(lens, TOLS)
        a = analyze(lens, TOLS, rings=4, trials=200)
        base = a.nominal_rms
        for row, v in zip(a.sensitivities, s):
            expected = 0.5 * (row["rms_plus"] ** 2 + row["rms_minus"] ** 2) - base**2
            assert v == pytest.approx(math.sqrt(max(expected, 0.0)), rel=1e-6, abs=1e-9)

    def test_report_shows_the_term(self):
        lens = triplet(desensitize={"weight": 2.0, "tolerances": [t.model_dump() for t in TOLS]})
        rep = merit_report(lens)["configurations"][0]
        d = rep["desensitize"]
        s = sensitivity_residuals(lens, TOLS)
        np.testing.assert_allclose([t["rms_increase"] for t in d["tolerances"]], s, rtol=1e-9)
        assert d["contribution"] == pytest.approx(4.0 * np.sum(s**2), rel=1e-9)
        assert rep["merit"] == pytest.approx(
            rep["image_contribution"] + d["contribution"], rel=1e-12
        )

    def test_desensitizing_trades_nominal_for_sensitivity(self):
        plain = optimize(triplet(), max_evaluations=200)["lens"]
        desens = optimize(
            triplet(desensitize={"weight": 1.0, "tolerances": [t.model_dump() for t in TOLS]}),
            max_evaluations=200,
        )["lens"]

        def f(lens):  # nominal mean-square wavefront
            plain_merit = lens.model_copy(update={"merit": MeritSpec(kind="wavefront")})
            return merit_report(plain_merit)["configurations"][0]["image_contribution"]

        def g(lens):  # predicted mean-square degradation
            return float(np.sum(sensitivity_residuals(lens, TOLS) ** 2))

        assert g(desens) < g(plain)
        assert f(desens) >= f(plain) * (1 - 1e-9)
        assert f(desens) + g(desens) <= f(plain) + g(plain) * (1 + 1e-9)

    def test_needs_the_wavefront_merit(self):
        with pytest.raises(ValueError, match="wavefront merit"):
            MeritSpec(kind="transverse", desensitize={"weight": 1.0})
        with pytest.raises(ValueError, match="no such surface"):
            triplet(desensitize={"tolerances": [{"kind": "DLR", "surface": 9, "limit": 1e-5}]})

    def test_default_tolerances_are_used_when_none_are_given(self):
        lens = triplet(desensitize={"weight": 1.0})
        d = merit_report(lens)["configurations"][0]["desensitize"]
        assert len(d["tolerances"]) > 5


def achromat(flint: str) -> LensData:
    """Thin achromat f = 100 mm designed for N-BK7 / N-SF2, with ``flint``."""
    def nv(g):
        nd = refractive_index(g, D_)
        return nd, (nd - 1) / (refractive_index(g, F_) - refractive_index(g, C_))

    n1, v1 = nv("N-BK7")
    n2, v2 = nv("N-SF2")
    phi = 10.0
    p1, p2 = phi * v1 / (v1 - v2), -phi * v2 / (v1 - v2)
    c1 = p1 / (2 * (n1 - 1))
    c2 = -c1
    c3 = c2 - p2 / (n2 - 1)
    return LensData(
        surfaces=[
            LensSurface(radius=1 / c1, thickness=0.001, material="N-BK7",
                        semi_diameter=0.005, is_stop=True),
            LensSurface(radius=1 / c2, thickness=0.0005, material=flint),
            LensSurface(radius=1 / c3, thickness=0.098),
        ],
        object_distance=None, wavelengths=[F_, D_, C_],
        analysis_settings=AnalysisSettings(wavelength=D_),
        merit=MeritSpec(image_weight=0.0, operands=[
            Operand(kind="axial_color", weight=1e3), Operand(kind="efl", target=0.1, weight=10.0)]),
    )


class TestGlassSubstitution:
    def test_nearest_glasses(self):
        near = nearest_catalog_glasses(1.62005, 36.43, count=5, vendors=["Schott"],
                                       exclude={"N-F2"})
        assert "N-F2" not in near and len(near) == 5
        d = [math.hypot((MATERIALS[g].nd - 1.62005) / 0.01, MATERIALS[g].vd - 36.43) for g in near]
        assert d == sorted(d)

    def test_finds_the_glass_the_achromat_was_designed_for(self):
        out = substitute_glasses(achromat("N-F2"), surfaces=[1], candidates=12,
                                 vendors=["Schott"], passes=1)
        assert len(out["substitutions"]) == 1
        chosen = out["substitutions"][0]["to"]
        assert MATERIALS[chosen].nd == pytest.approx(1.64769, abs=5e-4)
        assert MATERIALS[chosen].vd == pytest.approx(33.82, abs=0.2)
        assert out["merit_after"] < 1e-2 * out["merit_before"]

    def test_model_glass_is_always_replaced_and_reoptimized(self):
        lens = achromat("MODEL:1.6477:33.8").model_copy(deep=True)
        lens.surfaces[2].variables = ["radius"]
        lens = LensData.model_validate(lens.model_dump())
        out = substitute_glasses(lens, surfaces=[1], candidates=4, vendors=["Schott"], passes=1)
        material = out["lens"].surfaces[1].material
        assert material in MATERIALS
        assert out["substitutions"][0]["from"] == "MODEL:1.6477:33.8"
        assert out["evaluations"] > 1

    def test_keeps_a_glass_when_nothing_is_better(self):
        out = substitute_glasses(achromat("N-SF2"), surfaces=[1], candidates=6,
                                 vendors=["Schott"], passes=1)
        # only a glass with the same constants (SF2) could match it
        for s in out["substitutions"]:
            assert MATERIALS[s["to"]].nd == pytest.approx(1.64769, abs=5e-4)
        assert out["merit_after"] <= out["merit_before"]


def test_glass_api():
    from fastapi.testclient import TestClient

    from api.main import app

    r = TestClient(app).post(
        "/api/lens/substitute-glasses",
        json={"lens": achromat("N-F2").model_dump(), "surfaces": [1], "candidates": 12,
              "vendors": ["Schott"], "passes": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["substitutions"][0]["surface"] == 1
    assert body["merit_after"] < body["merit_before"]
    assert math.isfinite(body["first_order"]["efl"])
