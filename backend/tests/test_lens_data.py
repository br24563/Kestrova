"""
Tests for the surface-by-surface prescription (optics.lens_data).

Expected values come from closed-form optics, not from the module:
- thick-lens back focal length (lensmaker): BFL = f (1 - (n-1) t c1 / n);
- an F-number solve must give working F-number N = 1 / (2 |u'|);
- Cassegrain image distance from the mirror equation 1/s' + 1/s = 2/R;
- the entrance pupil of a front stop equals the stop.
"""

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import app
from optics import lens_data as ld
from optics import raytrace as rt
from optics.analysis import real_spot
from optics.illumination import vignetting_at_field
from optics.lens_data import LensData, LensSurface, Pickup, Solve
from optics.materials import refractive_index
from optics.presets import get_presets

WL = 587.56e-9


def singlet(r1=0.05, r2=-0.08, t=0.006, stop_gap=0.0, **extra) -> LensData:
    """Front stop, N-BK7 singlet, object at infinity, 5 degree field."""
    back = extra.pop("back", {})
    return LensData(
        surfaces=[
            LensSurface(label="STO", is_stop=True, semi_diameter=0.008, thickness=stop_gap),
            LensSurface(element="L1", radius=r1, thickness=t, material="N-BK7"),
            LensSurface(element="L1", radius=r2, thickness=0.1, **back),
        ],
        object_distance=None, field_angle=math.radians(5), wavelengths=[WL],
        analysis_settings={"wavelength": WL}, **extra,
    )


def lensmaker(r1, r2, t):
    n = refractive_index("N-BK7", WL)
    c1, c2 = 1 / r1, 1 / r2
    f = 1 / ((n - 1) * (c1 - c2 + (n - 1) * t * c1 * c2 / n))
    return f, f * (1 - (n - 1) * t * c1 / n)


class TestRoundTrip:

    @pytest.mark.parametrize("preset", get_presets(), ids=lambda p: p["id"])
    def test_every_preset_round_trips_exactly(self, preset):
        system = preset["system"]
        back = ld.to_system(ld.from_system(system))
        assert [(c.type, c.id) for c in back.components] == [(c.type, c.id) for c in system.components]
        for a, b in zip(system.components, back.components):
            assert b.position == pytest.approx(a.position, abs=1e-12)
        assert back.image_plane.position == pytest.approx(system.image_plane.position, abs=1e-12)
        fa, fb = rt.first_order(system), rt.first_order(back)
        if math.isfinite(fa.image_z):
            assert fb.image_z == pytest.approx(fa.image_z, abs=1e-12)

    def test_real_rays_are_unchanged(self):
        system = next(p for p in get_presets() if p["id"] == "thick_lens")["system"]
        back = ld.to_system(ld.from_system(system))
        assert real_spot(back, 1.0)[1] == pytest.approx(real_spot(system, 1.0)[1], rel=1e-12)

    def test_thicknesses_are_vertex_separations(self):
        lens = ld.from_system(next(p for p in get_presets() if p["id"] == "achromat")["system"])
        system = ld.to_system(lens)
        zs = np.cumsum([lens.first_surface_position] + [s.thickness for s in lens.surfaces])
        assert zs[-1] == pytest.approx(system.image_plane.position)


class TestThickness:

    def test_changing_a_thickness_moves_everything_after_it(self):
        lens = singlet(stop_gap=0.002)
        moved = ld.to_system(ld.set_parameter(lens, 0, "thickness", 0.005))
        base = ld.to_system(lens)
        lens_before = next(c for c in base.components if c.id == "L1")
        lens_after = next(c for c in moved.components if c.id == "L1")
        assert lens_after.position - lens_before.position == pytest.approx(0.003)
        assert moved.image_plane.position - base.image_plane.position == pytest.approx(0.003)


class TestSolves:

    def test_image_solve_is_the_back_focal_length(self):
        lens = singlet(back={"solves": {"thickness": Solve(kind="marginal_height")}})
        resolved = ld.resolve(lens)
        _, bfl = lensmaker(0.05, -0.08, 0.006)
        assert resolved.surfaces[2].thickness == pytest.approx(bfl, rel=1e-12)

    def test_height_solve_reaches_its_target(self):
        lens = singlet(back={"solves": {"thickness": Solve(kind="marginal_height", target=-0.001)}})
        system = ld.to_system(lens)
        fo = rt.first_order(system)
        assert fo.marginal.y[-1] + fo.marginal.u_after[-1] * (system.image_plane.position
                                                              - rt.build_sequence(system).surfaces[-1].z) \
            == pytest.approx(-0.001, abs=1e-12)

    @pytest.mark.parametrize("n", [2.0, 4.0, 8.0])
    def test_f_number_solve(self, n):
        lens = singlet(back={"solves": {"radius": Solve(kind="f_number", target=n),
                                        "thickness": Solve(kind="marginal_height")}})
        fo = rt.first_order(ld.to_system(lens))
        assert fo.working_f_number == pytest.approx(n, rel=1e-9)

    def test_cassegrain_image_solve_matches_mirror_equation(self):
        # Primary R = -1 m (f = 0.5 m); secondary R = -0.4 m, 0.35 m inside the
        # focus. Virtual object 0.15 m behind the secondary: 1/s' + 1/s = 2/R
        # with s = -0.15 gives s' = 0.6 m; EFL = 0.5 * (0.6 / 0.15) = 2 m.
        lens = LensData(
            surfaces=[
                LensSurface(label="M1", radius=-1.0, material="MIRROR", is_stop=True,
                            semi_diameter=0.05, thickness=-0.35),
                LensSurface(label="M2", radius=-0.4, material="MIRROR", thickness=0.5,
                            solves={"thickness": Solve(kind="marginal_height")}),
            ],
            object_distance=None, field_angle=math.radians(0.1), wavelengths=[WL],
            analysis_settings={"wavelength": WL},
        )
        resolved = ld.resolve(lens)
        assert resolved.surfaces[1].thickness == pytest.approx(0.6, rel=1e-9)
        assert rt.first_order(ld.to_system(lens)).efl == pytest.approx(2.0, rel=1e-9)

    def test_solve_through_a_parallel_ray_is_rejected(self):
        # An afocal pair leaves the marginal ray parallel: no image solve.
        lens = LensData(
            surfaces=[
                LensSurface(surface_type="paraxial", focal_length=0.1, is_stop=True,
                            semi_diameter=0.01, thickness=0.15),
                LensSurface(surface_type="paraxial", focal_length=0.05, thickness=0.1,
                            solves={"thickness": Solve(kind="marginal_height")}),
            ],
            object_distance=None, wavelengths=[WL], analysis_settings={"wavelength": WL},
        )
        with pytest.raises(ValueError, match="parallel"):
            ld.resolve(lens)


class TestPickups:

    def test_symmetric_lens_by_pickup(self):
        lens = singlet(back={"pickups": {"radius": Pickup(source=1, scale=-1.0)}})
        resolved = ld.resolve(ld.set_parameter(lens, 1, "radius", 0.07))
        assert resolved.surfaces[2].radius == pytest.approx(-0.07)

    def test_pickup_then_solve(self):
        # thickness picked up, then the image solve uses the new thickness
        lens = singlet(stop_gap=0.003, back={"solves": {"thickness": Solve(kind="marginal_height")}})
        lens.surfaces[1].pickups = {"thickness": Pickup(source=0, scale=2.0)}
        resolved = ld.resolve(lens)
        assert resolved.surfaces[1].thickness == pytest.approx(0.006)
        _, bfl = lensmaker(0.05, -0.08, 0.006)
        assert resolved.surfaces[2].thickness == pytest.approx(bfl, rel=1e-12)


class TestAperture:

    def test_entrance_pupil_diameter(self):
        lens = singlet(entrance_pupil_diameter=0.01)
        lens.surfaces[0].semi_diameter = None
        fo = rt.first_order(ld.to_system(lens))
        assert 2 * fo.entrance_pupil_semi_diameter == pytest.approx(0.01, rel=1e-12)

    def test_automatic_semi_diameters_do_not_vignette(self):
        system = ld.to_system(singlet(stop_gap=0.002))
        for field in (0.0, 0.5, 1.0):
            assert vignetting_at_field(system, field, 21).throughput == pytest.approx(1.0)

    def test_automatic_semi_diameter_is_the_real_ray_height(self):
        resolved = ld.resolve(singlet(stop_gap=0.002))
        s1 = resolved.surfaces[1]
        assert s1.semi_diameter_auto
        # the axial edge ray alone already reaches the stop height there
        assert s1.semi_diameter > 0.008


class TestValidation:

    def test_exactly_one_stop(self):
        with pytest.raises(ValidationError):
            LensData(surfaces=[LensSurface(radius=0.1)])

    def test_unknown_variable(self):
        with pytest.raises(ValidationError):
            LensSurface(variables=["focal_length"])

    def test_variable_cannot_also_be_solved(self):
        with pytest.raises(ValidationError):
            LensSurface(variables=["thickness"], solves={"thickness": Solve(kind="marginal_height")})

    def test_solve_kind_must_suit_the_parameter(self):
        with pytest.raises(ValidationError):
            LensSurface(solves={"thickness": Solve(kind="f_number", target=4)})


class TestOptimize:

    def test_bending_reduces_the_spot_with_solves_held(self):
        lens = singlet(r1=0.2, stop_gap=0.002,
                       back={"solves": {"radius": Solve(kind="f_number", target=4.0),
                                        "thickness": Solve(kind="marginal_height")}})
        lens.surfaces[1].variables = ["radius"]
        result = ld.optimize(lens)
        assert result["merit_after"] < 0.5 * result["merit_before"]
        fo = rt.first_order(result["system"])
        assert fo.working_f_number == pytest.approx(4.0, rel=1e-9)
        # the solved image plane is at the paraxial focus of the result
        assert result["system"].image_plane.position == pytest.approx(fo.image_z, abs=1e-12)

    def test_requires_variables(self):
        with pytest.raises(ValueError, match="variable"):
            ld.optimize(singlet())


class TestApi:

    client = TestClient(app)

    def test_from_system_resolve_and_analyze(self):
        system = self.client.get("/api/presets/thick_lens").json()["system"]
        lens = self.client.post("/api/lens/from-system", json={"system": system}).json()["lens"]
        lens["surfaces"][1]["solves"] = {"thickness": {"kind": "marginal_height"}}
        r = self.client.post("/api/lens/resolve", json={"lens": lens})
        assert r.status_code == 200
        body = r.json()
        assert body["first_order"]["image_z"] == pytest.approx(body["system"]["image_plane"]["position"])
        # the resolved system works with the existing analysis endpoints
        assert self.client.post("/api/analyze", json={"system": body["system"]}).status_code == 200

    def test_optimize_endpoint(self):
        lens = singlet(r1=0.2, stop_gap=0.002,
                       back={"solves": {"thickness": Solve(kind="marginal_height")}})
        lens.surfaces[1].variables = ["radius"]
        r = self.client.post("/api/lens/optimize", json={"lens": lens.model_dump(),
                                                          "bounds": {"1.radius": [0.02, 1.0]}})
        assert r.status_code == 200
        body = r.json()
        assert body["rms_spot_after"] < body["rms_spot_before"]

    def test_invalid_lens_is_a_client_error(self):
        r = self.client.post("/api/lens/resolve", json={"lens": {"surfaces": [{"radius": 0.1}]}})
        assert r.status_code == 422
