"""
Global optimization (optics.global_lens).

The test problem has two separate optima known independently of the
search: a cemented achromat (N-BK7 / N-F2, f = 100 mm, f/10) with its
focal length and axial colour held has one degree of freedom, its bending,
and along that family the Seidel spherical sum S-I crosses zero twice.
The expected designs are found here by following the family (solving the
two constraints at each front curvature) and bracketing both zeros of S-I;
the global search, minimising S-I^2, must return both.
"""

import math

import numpy as np
import pytest
from scipy.optimize import brentq, fsolve

from optics import raytrace as rt
from optics.global_lens import global_optimize, sampling_ranges
from optics.lens_data import (
    Constraint,
    LensData,
    LensSurface,
    MeritSpec,
    Operand,
    optimize,
    to_system,
)
from optics.merit import axial_color
from optics.models import AnalysisSettings

F_, D_, C_ = 486.1327e-9, 587.5618e-9, 656.2725e-9


def doublet(c1, c2, c3, variables=False) -> LensData:
    def r(c):
        return 1 / c if c else 0.0

    var = ["radius"] if variables else []
    return LensData(
        surfaces=[
            LensSurface(radius=r(c1), thickness=0.004, material="N-BK7",
                        semi_diameter=0.005, is_stop=True, variables=var),
            LensSurface(radius=r(c2), thickness=0.002, material="N-F2", variables=var),
            LensSurface(radius=r(c3), thickness=0.095, variables=var),
        ],
        object_distance=None, wavelengths=[F_, D_, C_],
        analysis_settings=AnalysisSettings(wavelength=D_),
        constraints=[Constraint(kind="efl", target=0.1),
                     Constraint(kind="axial_color", target=0.0)],
        merit=MeritSpec(image_weight=0.0, operands=[Operand(kind="seidel_S1", weight=1e3)]),
    )


def family(c1, guess):
    """(c2, c3) meeting EFL = 100 mm and zero axial colour at front curvature c1."""
    def eqs(v):
        s = to_system(doublet(c1, v[0], v[1]))
        return [rt.first_order(s).efl - 0.1, axial_color(s) * 1e3]

    sol, _, ier, _ = fsolve(eqs, guess, full_output=True, xtol=1e-13)
    assert ier == 1
    return sol


@pytest.fixture(scope="module")
def expected():
    """Both zero-spherical designs, as front curvatures (1/m)."""
    guess = np.array([-1 / 0.044, -1 / 0.13])

    def s1(c1):
        nonlocal guess
        guess = family(c1, guess)
        return rt.seidel_sums(to_system(doublet(c1, *guess))).S1

    roots = [brentq(s1, a, b, xtol=1e-10) for a, b in ((8.0, 14.0), (18.0, 26.0))]
    return roots


def test_local_optimization_finds_only_the_nearer_design(expected):
    # from a start near the weakly bent design, local DLS stays there
    c2, c3 = family(11.0, np.array([-1 / 0.044, -1 / 0.13]))
    out = optimize(doublet(11.0, c2, c3, variables=True), max_evaluations=200)
    assert out["success"]
    c1 = 1 / out["variables"]["0.radius"]
    assert c1 == pytest.approx(expected[0], rel=1e-5)


def test_global_search_finds_both_designs(expected):
    c2, c3 = family(11.0, np.array([-1 / 0.044, -1 / 0.13]))
    lens = doublet(11.0, c2, c3, variables=True)
    out = global_optimize(
        lens, starts=12, max_evaluations=150, seed=1,
        ranges={"0.radius": (2.0, 40.0), "1.radius": (-60.0, 0.0), "2.radius": (-30.0, 10.0)},
    )
    c1s = sorted(1 / s["lens"].surfaces[0].radius for s in out["solutions"][:2])
    assert out["distinct"] >= 2
    np.testing.assert_allclose(c1s, expected, rtol=1e-5)
    for s in out["solutions"][:2]:
        # both meet the constraints and zero the spherical sum
        sys_ = to_system(s["lens"])
        assert rt.first_order(sys_).efl == pytest.approx(0.1, rel=1e-9)
        assert abs(axial_color(sys_)) < 1e-12
        assert abs(rt.seidel_sums(sys_).S1) < 1e-10
    merits = [s["merit"] for s in out["solutions"]]
    assert merits == sorted(merits)
    assert out["starts"] == 13 and out["feasible"] >= out["distinct"]


def test_sampling_ranges():
    c2, c3 = family(11.0, np.array([-1 / 0.044, -1 / 0.13]))
    lens = doublet(11.0, c2, c3, variables=True)
    lens.surfaces[0].variables = ["radius", "thickness"]
    rng = sampling_ranges(LensData.model_validate(lens.model_dump()))
    space, lo, hi = rng["0.radius"]
    assert space == "curvature" and lo < 11.0 < hi
    assert rng["0.thickness"] == ("value", 0.002, 0.006)
    with pytest.raises(ValueError, match="not a variable"):
        sampling_ranges(lens, {"5.radius": (0, 1)})


def test_no_variables_is_an_error():
    lens = doublet(11.0, -20.0, -8.0)
    with pytest.raises(ValueError, match="No surface parameter"):
        global_optimize(lens, starts=2)


def test_global_api():
    from fastapi.testclient import TestClient

    from api.main import app

    c2, c3 = family(11.0, np.array([-1 / 0.044, -1 / 0.13]))
    lens = doublet(11.0, c2, c3, variables=True).model_dump()
    r = TestClient(app).post(
        "/api/lens/global-optimize",
        json={"lens": lens, "starts": 4, "max_evaluations": 80, "keep": 3,
              "ranges": {"0.radius": [2.0, 40.0], "1.radius": [-60.0, 0.0],
                         "2.radius": [-30.0, 10.0]}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["starts"] == 5
    assert 1 <= len(body["solutions"]) <= 3
    s0 = body["solutions"][0]
    assert {"lens", "merit", "variables", "start", "first_order"} <= set(s0)
    assert math.isfinite(s0["first_order"]["efl"])


def test_parallel_workers_give_the_same_designs():
    c2, c3 = family(11.0, np.array([-1 / 0.044, -1 / 0.13]))
    lens = doublet(11.0, c2, c3, variables=True)
    kw = dict(starts=3, max_evaluations=80, seed=2,
              ranges={"0.radius": (2.0, 40.0), "1.radius": (-60.0, 0.0),
                      "2.radius": (-30.0, 10.0)})
    serial = global_optimize(lens, workers=1, **kw)
    parallel = global_optimize(lens, workers=2, **kw)
    assert [s["start"] for s in serial["solutions"]] == [s["start"] for s in parallel["solutions"]]
    for a, b in zip(serial["solutions"], parallel["solutions"]):
        assert a["merit"] == pytest.approx(b["merit"], rel=1e-9, abs=1e-30)
