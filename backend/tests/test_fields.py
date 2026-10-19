"""
Field tables, wavelength weights and field analyses (optics.fields).

Independent references:
- an ideal lens images a field angle theta at f tan(theta), with zero
  distortion;
- a rotationally symmetric lens gives identical results for the same field
  angle in any azimuth;
- Gaussian quadrature integrates polynomials in r^2 exactly, and the RMS
  spot converges to a dense polar integration written out here;
- Code V vignetting factors map the pupil onto -(1 - VL) .. (1 - VU).
"""

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import app
from optics import fields as F
from optics import lens_data as ld
from optics import raytrace as rt
from optics.advanced_optimization import ray_aberration_residuals
from optics.analysis import real_spot
from optics.lens_data import LensData, LensSurface, Solve
from optics.models import (
    AnalysisSettings, FieldPoint, ImagePlane, Object, OpticalSystem, ThinLens,
)
from optics.presets import get_preset_by_id

WL = 587.56e-9


def singlet(semi=0.008, wavelengths=(WL,)):
    lens = LensData(
        surfaces=[
            LensSurface(label="STO", is_stop=True, semi_diameter=semi, thickness=0.002),
            LensSurface(element="L1", radius=0.06, thickness=0.006, material="N-BK7"),
            LensSurface(element="L1", radius=-0.3, thickness=0.1,
                        solves={"thickness": Solve(kind="marginal_height")}),
        ],
        object_distance=None, field_angle=math.radians(5), wavelengths=list(wavelengths),
        analysis_settings={"wavelength": WL},
    )
    return ld.to_system(lens)


def ideal_lens(fields, field_type="angle"):
    return OpticalSystem(
        components=[ThinLens(id="L", position=0.0, focal_length=0.1, aperture_diameter=0.02)],
        wavelengths=[WL], object=Object(position=-1e6, height=0.0),
        image_plane=ImagePlane(position=0.1), analysis_settings=AnalysisSettings(wavelength=WL),
        fields=fields, field_type=field_type,
    )


class TestModel:

    def test_existing_systems_have_no_field_table(self):
        s = get_preset_by_id("thick_lens")["system"]
        assert s.fields is None and s.wavelength_weights is None

    def test_one_weight_per_wavelength(self):
        with pytest.raises(ValidationError):
            singlet().model_copy(update={}).model_validate(
                {**singlet().model_dump(), "wavelength_weights": [1, 2]})

    def test_vignetting_factor_range(self):
        with pytest.raises(ValidationError):
            FieldPoint(y=0.1, vuy=1.0)

    def test_default_fields_are_code_v_fractions(self):
        s = get_preset_by_id("thick_lens")["system"]
        _, fields = F.resolve_fields(s)
        assert [f.hy for f in fields] == [0.0, 0.7, 1.0]


class TestFieldTypes:

    def test_angle_field_lands_at_f_tan_theta(self):
        theta = math.radians(20)
        row = F.field_summary(ideal_lens([FieldPoint(y=theta)]))["fields"][0]
        assert row["chief_ray"][1] == pytest.approx(0.1 * math.tan(theta), rel=1e-9)
        assert abs(row["distortion"]) < 1e-12

    def test_paraxial_image_height_field(self):
        # the ideal lens inverts: image height -f tan(theta) is field angle theta
        h = -0.1 * math.tan(math.radians(20))
        row = F.field_summary(ideal_lens([FieldPoint(y=h)], "paraxial_image_height"))["fields"][0]
        assert row["chief_ray"][1] == pytest.approx(h, rel=1e-9)

    def test_object_height_field_on_a_finite_object(self):
        s = get_preset_by_id("single_lens")["system"]  # 2f-2f, m = -1
        s = s.model_copy(update={"fields": [FieldPoint(x=0.002, y=-0.003)]})
        row = F.field_summary(s)["fields"][0]
        assert row["chief_ray"][0] == pytest.approx(-0.002, rel=1e-9)
        assert row["chief_ray"][1] == pytest.approx(0.003, rel=1e-9)

    def test_type_must_suit_the_object(self):
        s = get_preset_by_id("single_lens")["system"].model_copy(
            update={"fields": [FieldPoint(y=0.01)], "field_type": "angle"})
        with pytest.raises(ValueError):
            F.resolve_fields(s)


class TestSymmetry:

    def test_same_field_angle_in_any_azimuth(self):
        theta = math.radians(4)
        s = singlet().model_copy(update={
            "fields": [FieldPoint(y=theta), FieldPoint(x=theta), FieldPoint(x=-theta)],
            "field_type": "angle"})
        rows = F.field_summary(s)["fields"]
        assert rows[1]["rms_spot"] == pytest.approx(rows[0]["rms_spot"], rel=1e-9)
        assert rows[2]["rms_spot"] == pytest.approx(rows[0]["rms_spot"], rel=1e-9)
        assert rows[1]["chief_ray"][0] == pytest.approx(rows[0]["chief_ray"][1], rel=1e-9)

    def test_mtf_follows_the_field_direction(self):
        t = math.tan(math.radians(4))
        s = singlet(semi=0.0025)
        y_field = s.model_copy(update={"fields": [FieldPoint(y=math.atan(t))], "field_type": "angle"})
        x_field = s.model_copy(update={"fields": [FieldPoint(x=math.atan(t))], "field_type": "angle"})
        diag = s.model_copy(update={"fields": [FieldPoint(x=math.atan(t / math.sqrt(2)),
                                                          y=math.atan(t / math.sqrt(2)))],
                                    "field_type": "angle"})
        my, mx, md = (F.field_mtf(x, 0, [20, 50]) for x in (y_field, x_field, diag))
        assert mx["tangential"] == pytest.approx(my["tangential"], abs=1e-9)
        assert mx["sagittal"] == pytest.approx(my["sagittal"], abs=1e-9)
        # a 45-degree field reads the OTF between grid axes (interpolated)
        assert md["tangential"] == pytest.approx(my["tangential"], abs=0.01)
        assert md["sagittal"] == pytest.approx(my["sagittal"], abs=0.01)


class TestQuadrature:

    def test_gaussian_pupil_integrates_polynomials_exactly(self):
        px, py, w = F.gaussian_pupil(4)
        r2 = px ** 2 + py ** 2
        assert w.sum() == pytest.approx(1.0)
        # mean of r^(2k) over the unit disk is 1 / (k + 1)
        for k in range(1, 8):
            assert np.sum(w * r2 ** k) == pytest.approx(1.0 / (k + 1), rel=1e-12)

    def test_rms_spot_matches_a_dense_polar_integration(self):
        s = get_preset_by_id("thick_lens")["system"]
        seq = rt.build_sequence(s)
        fo = rt.first_order(s, seq=seq)
        nr, na = 400, 64
        u = (np.arange(nr) + 0.5) / nr
        R, T = np.meshgrid(np.sqrt(u), (np.arange(na) + 0.5) * 2 * np.pi / na, indexing="ij")
        b, _, _ = rt.trace_field_rays(s, 0, 0, (R * np.cos(T)).ravel(), (R * np.sin(T)).ravel(),
                                      seq=seq, fo=fo)
        P = rt._to_local(seq.image_origin, seq.image_rotation, b.image, b.directions)[0][:, :2]
        dense = np.sqrt(np.mean(np.sum((P - P.mean(0)) ** 2, axis=1)))
        assert real_spot(s, 0.0)[1] == pytest.approx(dense, rel=1e-4)
        assert F.field_summary(s)["fields"][0]["rms_spot"] == pytest.approx(dense, rel=1e-4)

    def test_rms_spot_does_not_depend_on_the_plot_grid(self):
        s = get_preset_by_id("thick_lens")["system"]
        values = [real_spot(s, 1.0, n)[1] for n in (7, 15, 31)]
        assert max(values) == pytest.approx(min(values), rel=1e-9)


class TestVignettingAndWeights:

    def test_vignetting_factors_bound_the_pupil(self):
        px, py, _ = F.pupil_samples(6, (0.1, 0.3, 0.5, 0.2))
        assert px.max() <= 1 - 0.1 + 1e-12 and px.min() >= -(1 - 0.3) - 1e-12
        assert py.max() <= 1 - 0.5 + 1e-12 and py.min() >= -(1 - 0.2) - 1e-12

    def test_vignetting_shrinks_the_spot_of_an_aberrated_field(self):
        theta = math.radians(4)
        s = singlet()
        full = s.model_copy(update={"fields": [FieldPoint(y=theta)], "field_type": "angle"})
        cut = s.model_copy(update={"fields": [FieldPoint(y=theta, vuy=0.4, vly=0.4)],
                                   "field_type": "angle"})
        assert F.field_summary(cut)["fields"][0]["rms_spot"] < F.field_summary(full)["fields"][0]["rms_spot"]

    def test_field_weighted_rms(self):
        theta = math.radians(4)
        s = singlet().model_copy(update={"fields": [FieldPoint(y=0, weight=1),
                                                    FieldPoint(y=theta, weight=3)],
                                         "field_type": "angle"})
        r = F.field_summary(s)
        a, b = r["fields"][0]["rms_spot"], r["fields"][1]["rms_spot"]
        assert r["weighted_rms_spot"] == pytest.approx(math.sqrt((a * a + 3 * b * b) / 4), rel=1e-12)

    def test_a_zero_weight_wavelength_does_not_count(self):
        s = singlet(wavelengths=(486.13e-9, WL, 656.27e-9))
        mono = singlet()
        weighted = s.model_copy(update={"wavelength_weights": [0.0, 1.0, 0.0]})
        assert F.field_summary(weighted)["fields"][0]["rms_spot"] == pytest.approx(
            F.field_summary(mono)["fields"][0]["rms_spot"], rel=1e-12)

    def test_merit_uses_the_field_table(self):
        theta = math.radians(4)
        s = singlet()
        one = s.model_copy(update={"fields": [FieldPoint(y=theta)], "field_type": "angle"})
        r = ray_aberration_residuals(one, rings=6)
        # sum of squares = mean-square spot about the reference (chief) ray
        row = F.field_summary(one, rings=6)["fields"][0]
        centroid_offset = np.subtract(row["centroid"], row["chief_ray"])
        assert np.sum(r ** 2) == pytest.approx(row["rms_spot"] ** 2 + np.sum(centroid_offset ** 2),
                                               rel=1e-6)


class TestApi:

    client = TestClient(app)

    def test_fields_endpoint(self):
        s = singlet().model_copy(update={"fields": [FieldPoint(y=0), FieldPoint(x=0.05, weight=2)],
                                         "field_type": "angle"})
        r = self.client.post("/api/analyze/fields", json={"system": s.model_dump()})
        assert r.status_code == 200
        body = r.json()
        assert len(body["fields"]) == 2 and body["weighted_rms_spot"] > 0

    def test_field_mtf_endpoint(self):
        s = singlet().model_copy(update={"fields": [FieldPoint(y=0.05)], "field_type": "angle"})
        r = self.client.post("/api/analyze/field-mtf",
                             json={"system": s.model_dump(), "field": 0, "frequencies": [10, 20]})
        assert r.status_code == 200
        assert len(r.json()["tangential"]) == 2

    def test_bad_field_index(self):
        r = self.client.post("/api/analyze/field-mtf",
                             json={"system": singlet().model_dump(), "field": 9})
        assert r.status_code == 400

    def test_existing_endpoints_accept_field_tables(self):
        s = singlet().model_copy(update={"fields": [FieldPoint(y=0.05)], "field_type": "angle",
                                         "wavelength_weights": [1.0]})
        assert self.client.post("/api/analyze", json={"system": s.model_dump()}).status_code == 200
