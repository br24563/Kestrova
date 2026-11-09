"""
Multi-configuration lenses (zoom, focus and field configurations).

Expected values come from closed-form optics, not from the engine:

- two ideal lenses f1, f2 separated by d have
  EFL = f1 f2 / (f1 + f2 - d) and BFL = f2 (f1 - d) / (f1 + f2 - d);
- so a two-group zoom reaches focal length F at d = f1 + f2 - f1 f2 / F,
  which the multi-configuration optimizer must find from per-configuration
  focal-length constraints;
- every configuration equals the same lens built on its own with that
  configuration's values.
"""

import math

import numpy as np
import pytest

from optics import raytrace as rt
from optics.io.lensfile import write_codev, write_zemax
from optics.lens_data import (
    Constraint,
    LensData,
    LensSurface,
    Solve,
    ZoomRow,
    configuration_system,
    configured,
    optimize,
    resolve,
    to_system,
)
from optics.lens_optimize import evaluate_constraints
from optics.models import AnalysisSettings, FieldPoint
from optics.reference_lenses import SASIAN_TRIPLET

WL = 550e-9
F1, F2 = 0.1, 0.05


def two_group(separations, image_solve=False, **extra) -> LensData:
    """Two ideal lenses (f1 = 100 mm, stop, then f2 = 50 mm) whose
    separation zooms through ``separations``."""
    n = len(separations)
    back = LensSurface(
        surface_type="paraxial", focal_length=F2, thickness=0.05, semi_diameter=0.01
    )
    if image_solve:
        back.solves = {"thickness": Solve(kind="marginal_height", target=0.0)}
    return LensData(
        surfaces=[
            LensSurface(
                surface_type="paraxial",
                focal_length=F1,
                thickness=separations[0],
                semi_diameter=0.01,
                is_stop=True,
            ),
            back,
        ],
        object_distance=None,
        field_angle=math.radians(1),
        wavelengths=[WL],
        analysis_settings=AnalysisSettings(wavelength=WL),
        configuration_names=[f"Z{k + 1}" for k in range(n)],
        zoom=[ZoomRow(surface=0, parameter="thickness", values=list(separations))],
        **extra,
    )


def efl(d):
    return F1 * F2 / (F1 + F2 - d)


def bfl(d):
    return F2 * (F1 - d) / (F1 + F2 - d)


class TestModel:
    def test_surface_table_shows_configuration_1(self):
        lens = two_group([0.02, 0.03, 0.04])
        assert lens.num_configurations == 3
        assert lens.surfaces[0].thickness == 0.02
        edited = lens.model_copy(deep=True)
        edited.zoom[0].values[0] = 0.025
        assert LensData.model_validate(edited.model_dump()).surfaces[0].thickness == 0.025

    def test_configured_applies_each_value(self):
        lens = two_group([0.02, 0.03, 0.04])
        for k, d in enumerate([0.02, 0.03, 0.04]):
            one = configured(lens, k)
            assert one.surfaces[0].thickness == d
            assert one.zoom == [] and one.num_configurations == 1
            assert one.name.endswith(f"[Z{k + 1}]")
        with pytest.raises(ValueError, match="does not exist"):
            configured(lens, 3)

    def test_validation(self):
        with pytest.raises(ValueError, match="at least two configurations"):
            LensData(surfaces=[LensSurface(is_stop=True, semi_diameter=0.01)],
                     zoom=[ZoomRow(surface=0, parameter="thickness", values=[0.1])])
        with pytest.raises(ValueError, match="one value per configuration"):
            two_group([0.02, 0.03]).model_copy(
                update={"configuration_names": ["a", "b", "c"]}
            ).model_validate(
                {**two_group([0.02, 0.03]).model_dump(), "configuration_names": ["a", "b", "c"]}
            )
        base = two_group([0.02, 0.03]).model_dump()
        bad_param = {**base, "zoom": [{"surface": 0, "parameter": "radius_x",
                                       "values": [1, 2]}]}
        with pytest.raises(ValueError, match="not a parameter"):
            LensData.model_validate(bad_param)
        bad_sys = {**base, "zoom": [{"surface": None, "parameter": "wavelength",
                                     "values": [1, 2]}]}
        with pytest.raises(ValueError, match="system parameter"):
            LensData.model_validate(bad_sys)
        flagged = {**base}
        flagged["surfaces"] = [dict(base["surfaces"][0], variables=["thickness"]),
                               base["surfaces"][1]]
        with pytest.raises(ValueError, match="zoomed"):
            LensData.model_validate(flagged)
        with pytest.raises(ValueError, match="configuration 5"):
            LensData.model_validate({**base, "constraints": [
                {"kind": "efl", "target": 0.05, "configuration": 5}]})
        with pytest.raises(ValueError, match="one weight"):
            LensData.model_validate({**base, "configuration_weights": [1.0]})


class TestTwoGroupZoom:
    @pytest.mark.parametrize("k, d", list(enumerate([0.02, 0.035, 0.05])))
    def test_first_order_matches_closed_form(self, k, d):
        lens = two_group([0.02, 0.035, 0.05])
        fo = rt.first_order(configuration_system(lens, k))
        assert fo.efl == pytest.approx(efl(d), rel=1e-10)
        assert fo.bfl == pytest.approx(bfl(d), rel=1e-10)

    def test_image_solve_refocuses_each_configuration(self):
        lens = two_group([0.02, 0.035, 0.05], image_solve=True)
        for k, d in enumerate([0.02, 0.035, 0.05]):
            r = resolve(configured(lens, k))
            assert r.surfaces[1].thickness == pytest.approx(bfl(d), rel=1e-10)

    def test_optimizer_finds_the_zoom_separations(self):
        # targets 40, 60, 80 mm: d = f1 + f2 - f1 f2 / F
        targets = [0.04, 0.06, 0.08]
        lens = two_group([0.03, 0.03, 0.03], image_solve=True).model_copy(deep=True)
        lens.zoom[0].variable = True
        lens.constraints = [
            Constraint(kind="efl", target=F, configuration=k) for k, F in enumerate(targets)
        ]
        lens = LensData.model_validate(lens.model_dump())
        result = optimize(lens, max_evaluations=400)
        assert result["success"], result["message"]
        found = result["lens"].zoom[0].values
        expected = [F1 + F2 - F1 * F2 / F for F in targets]
        np.testing.assert_allclose(found, expected, rtol=1e-6)
        assert set(result["variables"]) == {"0.thickness@1", "0.thickness@2", "0.thickness@3"}
        report = evaluate_constraints(result["lens"])
        assert [r["configuration"] for r in report] == [0, 1, 2]
        assert all(r["satisfied"] for r in report)


class TestRealLens:
    def focus_lens(self):
        """The Geiser triplet focused at infinity and at 1 m (back focus zoomed)."""
        # fields by object distance: the 20 degree angle at infinity, the
        # matching object height at 1 m
        lens = SASIAN_TRIPLET.build()
        bf = lens.surfaces[-1].thickness
        h = math.tan(math.radians(20))
        return LensData.model_validate({
            **lens.model_dump(),
            "fields": None,
            "field_type": None,
            "configuration_names": ["Infinity", "1 m"],
            "zoom": [
                {"surface": None, "parameter": "object_distance", "values": [None, 1.0]},
                {"surface": None, "parameter": "object_height", "values": [h, h]},
                {"surface": 5, "parameter": "thickness", "values": [bf, bf + 0.0026]},
            ],
        })

    def test_each_configuration_equals_the_single_lens(self):
        lens = self.focus_lens()
        single = SASIAN_TRIPLET.build().model_copy(deep=True)
        single.fields, single.field_type = None, None
        single.object_distance = 1.0
        single.object_height = math.tan(math.radians(20))
        single.surfaces[-1].thickness += 0.0026
        a = rt.first_order(configuration_system(lens, 1))
        b = rt.first_order(to_system(single))
        assert a.efl == pytest.approx(b.efl, rel=1e-12)
        assert a.image_z == pytest.approx(b.image_z, rel=1e-12)
        assert a.magnification == pytest.approx(b.magnification, rel=1e-12)

    def test_apertures_cover_every_configuration(self):
        lens = self.focus_lens()
        for s in lens.surfaces:
            s.semi_diameter = None if not s.is_stop else s.semi_diameter
        r = resolve(lens)
        per = [resolve(configured(lens, k)) for k in range(2)]
        for i, s in enumerate(r.surfaces):
            if s.semi_diameter_auto:
                assert s.semi_diameter == pytest.approx(
                    max(p.surfaces[i].semi_diameter for p in per)
                )

    def test_multi_configuration_optimum_matches_separate_ones(self):
        # with only each configuration's own back focus varying, the summed
        # merit separates: each optimum equals that configuration's alone
        lens = self.focus_lens().model_copy(deep=True)
        lens.zoom[2].variable = True
        lens = LensData.model_validate(lens.model_dump())
        multi = optimize(lens, max_evaluations=200)["lens"].zoom[2].values
        for k in range(2):
            one = configured(lens, k).model_copy(deep=True)
            one.surfaces[5].variables = ["thickness"]
            alone = optimize(one, max_evaluations=200)["lens"].surfaces[5].thickness
            assert multi[k] == pytest.approx(alone, abs=2e-8)

    def test_field_zoom_scales_the_field_table(self):
        lens = SASIAN_TRIPLET.build()
        data = {**lens.model_dump(), "configuration_names": ["20", "10"],
                "zoom": [{"surface": None, "parameter": "field_angle",
                          "values": [math.radians(20), math.radians(10)]}]}
        z = LensData.model_validate(data)
        one = configured(z, 1)
        assert one.field_angle == pytest.approx(math.radians(10))
        tans = [math.tan(f.y) for f in one.fields]
        np.testing.assert_allclose(
            tans, [r * math.tan(math.radians(10)) for r in (0.0, 0.7071, 1.0)], rtol=1e-12
        )
        assert isinstance(one.fields[0], FieldPoint)


def test_lens_files_write_configuration_1_with_a_warning():
    lens = two_group([0.02, 0.03], image_solve=False)
    _, warnings = write_zemax(lens)
    assert any("Only configuration 1 of 2" in w for w in warnings)
    real = TestRealLens().focus_lens()
    _, warnings = write_codev(real)
    assert any("Only configuration 1 of 2" in w for w in warnings)


def test_configuration_api():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    lens = two_group([0.02, 0.035, 0.05]).model_dump()
    r = client.post("/api/lens/configurations", json={"lens": lens})
    assert r.status_code == 200
    rows = r.json()["configurations"]
    assert [row["name"] for row in rows] == ["Z1", "Z2", "Z3"]
    for row, d in zip(rows, [0.02, 0.035, 0.05]):
        assert row["first_order"]["efl"] == pytest.approx(efl(d), rel=1e-9)
    r = client.post("/api/lens/resolve", json={"lens": lens, "configuration": 2})
    assert r.status_code == 200
    assert r.json()["configuration"] == 2
    assert r.json()["first_order"]["efl"] == pytest.approx(efl(0.05), rel=1e-9)
    assert r.json()["lens"]["zoom"][0]["values"] == [0.02, 0.035, 0.05]
    bad = client.post("/api/lens/resolve", json={"lens": lens, "configuration": 7})
    assert bad.status_code == 400
