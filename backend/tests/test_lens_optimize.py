"""
Tests for the constrained optimizer, model glasses and glass snapping
(optics.lens_optimize, optics.materials model glasses).

Expected values come from independent references, not from the optimizer:
- the EFL-constrained singlet optimum is found by a 1-D search along the
  constraint, with R2 from the thick-lens lensmaker equation;
- edge thickness from the sphere sag formula z = R - sqrt(R^2 - h^2);
- model-glass dispersion against the N-BK7 catalog (Sellmeier) indices and
  the Schott normal line P_gF = 0.6438 - 0.001682 Vd (TIE-29).
"""

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from scipy.optimize import minimize_scalar

from api.main import app
from optics import lens_data as ld
from optics import lens_optimize as lo
from optics import raytrace as rt
from optics.advanced_optimization import ray_aberration_residuals
from optics.lens_data import Constraint, LensData, LensSurface, Solve
from optics.materials import (
    C_LINE,
    D_LINE,
    F_LINE,
    G_LINE,
    MATERIALS,
    get_material,
    model_glass_name,
    parse_model_glass,
    refractive_index,
)

WL = 587.56e-9
T = 0.006
EFL = 0.1


def singlet(
    r1=0.08,
    r2=-0.2,
    constraints=(),
    material="N-BK7",
    variables=("radius",),
    wavelengths=(WL,),
) -> LensData:
    return LensData(
        surfaces=[
            LensSurface(
                label="STO", is_stop=True, semi_diameter=0.0125, thickness=0.002
            ),
            LensSurface(
                element="L1",
                radius=r1,
                thickness=T,
                material=material,
                variables=list(variables),
            ),
            LensSurface(
                element="L1",
                radius=r2,
                thickness=0.1,
                variables=["radius"],
                solves={"thickness": Solve(kind="marginal_height")},
            ),
        ],
        object_distance=None,
        field_angle=math.radians(2),
        wavelengths=list(wavelengths),
        analysis_settings={"wavelength": WL},
        constraints=list(constraints),
    )


def r2_for_efl(r1, f=EFL):
    """Lensmaker: 1/f = (n-1)(c1 - c2 + (n-1) t c1 c2 / n), solved for R2."""
    n = refractive_index("N-BK7", WL)
    c1 = 1 / r1
    c2 = (1 / (f * (n - 1)) - c1) / ((n - 1) * T * c1 / n - 1)
    return 1 / c2


def merit_along_constraint(r1):
    lens = singlet(r1, r2_for_efl(r1))
    system = ld.to_system(ld.resolve(lens))
    return float(
        np.sum(
            ray_aberration_residuals(system, wavelengths=[WL], vignetting=False) ** 2
        )
    )


class TestConstrainedOptimum:

    def test_singlet_matches_independent_1d_optimum(self):
        result = ld.optimize(singlet(constraints=[Constraint(kind="efl", target=EFL)]))
        ref = minimize_scalar(
            merit_along_constraint,
            bounds=(0.04, 0.2),
            method="bounded",
            options={"xatol": 1e-9},
        )
        assert result["success"]
        assert result["variables"]["1.radius"] == pytest.approx(ref.x, rel=1e-4)
        assert result["variables"]["2.radius"] == pytest.approx(
            r2_for_efl(ref.x), rel=1e-4
        )
        assert result["merit_after"] == pytest.approx(ref.fun, rel=1e-6)

    def test_equality_constraint_is_met_exactly(self):
        result = ld.optimize(singlet(constraints=[Constraint(kind="efl", target=EFL)]))
        assert rt.first_order(result["system"]).efl == pytest.approx(EFL, rel=1e-12)
        assert result["constraints"][0]["satisfied"]

    def test_inequality_limits_hold(self):
        # unconstrained, the singlet's EFL wanders; hold it within limits
        result = ld.optimize(
            singlet(
                constraints=[
                    Constraint(kind="efl", minimum=0.099, maximum=0.1005),
                    Constraint(kind="edge_thickness", surface=1, minimum=0.003),
                ]
            )
        )
        efl = rt.first_order(result["system"]).efl
        assert 0.099 - 1e-12 <= efl <= 0.1005 + 1e-12
        assert (
            lo.edge_thickness(ld.resolve(result["lens"], fill_apertures=True), 1)
            >= 0.003 - 1e-12
        )
        assert result["success"]

    def test_history_and_report(self):
        result = ld.optimize(singlet(constraints=[Constraint(kind="efl", target=EFL)]))
        # the start violates the EFL target: the violation falls to zero
        # (the merit may rise on the way to the constrained optimum)
        violations = [h["violation"] for h in result["history"]]
        assert violations[0] > 0 and violations[-1] < 1e-18
        assert {"merit", "violation", "damping"} <= set(result["history"][0])

    def test_variable_bounds_hold(self):
        result = ld.optimize(singlet(), bounds={"1.radius": (0.07, 0.09)})
        assert 0.07 - 1e-12 <= result["variables"]["1.radius"] <= 0.09 + 1e-12

    def test_radius_bounds_spanning_flat_are_rejected(self):
        with pytest.raises(ValueError, match="flat"):
            ld.optimize(singlet(), bounds={"1.radius": (-1.0, 1.0)})


class TestEdgeThickness:

    def test_matches_sphere_sag(self):
        lens = ld.resolve(singlet(r1=0.05, r2=-0.08), fill_apertures=True)
        h = min(lens.surfaces[1].semi_diameter, lens.surfaces[2].semi_diameter)
        sag1 = 0.05 - math.sqrt(0.05**2 - h**2)
        sag2 = -(0.08 - math.sqrt(0.08**2 - h**2))
        assert lo.edge_thickness(lens, 1) == pytest.approx(T - sag1 + sag2, rel=1e-12)

    def test_constraint_validation(self):
        with pytest.raises(ValidationError):
            Constraint(kind="edge_thickness", minimum=0.001)  # needs a surface
        with pytest.raises(ValidationError):
            Constraint(kind="efl", target=0.1, minimum=0.09)
        with pytest.raises(ValidationError):
            Constraint(kind="efl")
        with pytest.raises(ValidationError):
            singlet(
                constraints=[
                    Constraint(kind="edge_thickness", surface=2, minimum=0.001)
                ]
            )


class TestModelGlass:

    def test_name_round_trip(self):
        assert parse_model_glass(model_glass_name(1.62, 36.4)) == pytest.approx(
            (1.62, 36.4)
        )
        assert parse_model_glass("N-BK7") is None
        with pytest.raises(ValueError):
            parse_model_glass("MODEL:0.9:40")

    def test_matches_n_bk7(self):
        bk7 = MATERIALS["N-BK7"]
        model = model_glass_name(bk7.nd, bk7.vd)
        for wl in (486.13e-9, 587.56e-9, 656.27e-9):
            assert refractive_index(model, wl) == pytest.approx(
                refractive_index("N-BK7", wl), abs=5e-5
            )

    @pytest.mark.parametrize("nd,vd", [(1.5168, 64.17), (1.6, 40.0), (1.8, 25.0)])
    def test_nd_vd_and_normal_line(self, nd, vd):
        n = {
            k: refractive_index(model_glass_name(nd, vd), wl)
            for k, wl in {"g": G_LINE, "F": F_LINE, "d": D_LINE, "C": C_LINE}.items()
        }
        assert n["d"] == pytest.approx(nd, abs=1e-9)
        assert (n["d"] - 1) / (n["F"] - n["C"]) == pytest.approx(vd, rel=1e-9)
        p_gf = (n["g"] - n["F"]) / (n["F"] - n["C"])
        assert p_gf == pytest.approx(0.6438 - 0.001682 * vd, abs=1e-9)

    def test_glass_variables_need_a_model_glass(self):
        with pytest.raises(ValidationError):
            singlet(variables=("radius", "glass_nd"))

    def test_glass_stays_inside_the_glass_map(self):
        # pushing nd up for power: the hull of catalog glasses must hold it
        lens = singlet(
            material="MODEL:1.75:50",
            variables=("radius", "glass_nd", "glass_vd"),
            wavelengths=(F_LINE, D_LINE, C_LINE),
            constraints=[Constraint(kind="efl", target=EFL)],
        )
        result = ld.optimize(lens, max_evaluations=400)
        nd, vd = parse_model_glass(result["lens"].surfaces[1].material)
        normals, offsets = lo.glass_map_hull()
        assert np.all(normals @ np.array([nd, vd]) <= offsets + 1e-9)
        assert result["success"]


class TestSnapping:

    def test_picks_nearest_catalog_glass(self):
        bk7 = MATERIALS["N-BK7"]
        assert lo.nearest_catalog_glass(bk7.nd, bk7.vd, vendors=["Schott"]) == "N-BK7"
        nd, vd = 1.6, 40.0
        name = lo.nearest_catalog_glass(nd, vd)
        d = math.hypot((MATERIALS[name].nd - nd) / 0.01, MATERIALS[name].vd - vd)
        for m in MATERIALS.values():
            if (
                m.manufacturer in ("Schott", "Ohara", "Hoya", "CDGM")
                and m.nd
                and m.vd
                and m.status != "inquiry"
            ):
                assert math.hypot((m.nd - nd) / 0.01, m.vd - vd) >= d - 1e-12

    def test_inquiry_glasses_skipped_by_default(self):
        inquiry = [
            k
            for k, m in MATERIALS.items()
            if m.manufacturer == "Schott" and m.status == "inquiry" and m.nd and m.vd
        ]
        if not inquiry:
            pytest.skip("no inquiry glasses in the catalog")
        m = MATERIALS[inquiry[0]]
        assert lo.nearest_catalog_glass(m.nd, m.vd, vendors=["Schott"]) != inquiry[0]
        assert (
            lo.nearest_catalog_glass(
                m.nd, m.vd, vendors=["Schott"], include_inquiry=True
            )
            == inquiry[0]
        )

    def test_snap_replaces_model_and_drops_glass_variables(self):
        lens = singlet(material="MODEL:1.5168:64.17", variables=("radius", "glass_nd"))
        snapped, subs = lo.snap_glasses(lens, vendors=["Schott"])
        assert subs == [{"surface": 1, "model": "MODEL:1.5168:64.17", "glass": "N-BK7"}]
        assert snapped.surfaces[1].material == "N-BK7"
        assert snapped.surfaces[1].variables == ["radius"]
        assert get_material("N-BK7") is not None


class TestApi:

    client = TestClient(app)

    def test_optimize_returns_constraint_report(self):
        lens = singlet(constraints=[Constraint(kind="efl", target=EFL)])
        r = self.client.post("/api/lens/optimize", json={"lens": lens.model_dump()})
        assert r.status_code == 200
        body = r.json()
        assert body["constraints"][0]["satisfied"]
        assert body["constraints"][0]["value"] == pytest.approx(EFL, rel=1e-12)

    def test_constraints_endpoint(self):
        lens = singlet(constraints=[Constraint(kind="efl", target=EFL)])
        r = self.client.post("/api/lens/constraints", json={"lens": lens.model_dump()})
        assert r.status_code == 200
        c = r.json()["constraints"][0]
        assert c["value"] == pytest.approx(
            rt.first_order(ld.to_system(lens)).efl, rel=1e-12
        )
        assert not c["satisfied"]

    def test_snap_endpoint(self):
        lens = singlet(material="MODEL:1.5168:64.17")
        r = self.client.post(
            "/api/lens/snap-glasses",
            json={"lens": lens.model_dump(), "vendors": ["SCHOTT"]},
        )
        assert r.status_code == 200
        assert r.json()["substitutions"][0]["glass"] == "N-BK7"
