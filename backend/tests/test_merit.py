"""
Merit functions, operands and the new constraint properties.

Expected values are closed-form results, not engine output:

- a perfect lens defocused by dz forms a uniform disk of radius
  a = dz tan(u') (RMS radius a / sqrt 2) and a defocus wavefront
  W(rho) = W020 rho^2 with W020 = dz (1 - cos u') (RMS about its mean
  W020 / sqrt 12, piston removed);
- through an ideal lens at its stop the chief ray is undeviated (image
  height f tan(theta), chief-ray angle theta) and with the stop at the
  front focal plane the image space is telecentric (angle 0);
- an ideal lens of a dispersive glass has f(lambda) proportional to
  1 / (n(lambda) - 1), which fixes its axial and lateral colour;
- the Geiser triplet's Seidel S-I is ray-optics' 0.010973 mm;
- a thin singlet has minimum spherical aberration (object at infinity) at
  Coddington shape factor q = (R2 + R1) / (R2 - R1) = 2 (n^2 - 1) / (n + 2).
"""

import math

import pytest

from optics.lens_data import (
    Constraint,
    LensData,
    LensSurface,
    MeritSpec,
    Operand,
    optimize,
    to_system,
)
from optics.lens_optimize import merit_report
from optics.materials import refractive_index
from optics.merit import property_value
from optics.models import AnalysisSettings, FieldPoint
from optics.reference_lenses import SASIAN_TRIPLET

WL = 550e-9
F = 0.1


def ideal(defocus=0.0, semi=0.002, stop_gap=None, field_deg=0.0, glass="N-BK7",
          wavelengths=(WL,), merit=None) -> LensData:
    """An ideal lens f = 100 mm; with ``stop_gap`` a separate stop that far
    in front of it; the image ``defocus`` beyond the focus."""
    lens_row = LensSurface(surface_type="paraxial", focal_length=F, thickness=F + defocus,
                           semi_diameter=0.01, ideal_lens_glass=glass)
    if stop_gap is None:
        rows = [lens_row.model_copy(update=dict(is_stop=True, semi_diameter=semi))]
    else:
        rows = [LensSurface(label="STO", is_stop=True, semi_diameter=semi,
                            thickness=stop_gap), lens_row]
    fields = [FieldPoint(y=math.radians(field_deg))] if field_deg else [FieldPoint(y=0.0)]
    return LensData(
        surfaces=rows, object_distance=None, field_angle=math.radians(field_deg),
        fields=fields, field_type="angle", wavelengths=list(wavelengths),
        analysis_settings=AnalysisSettings(wavelength=WL),
        merit=merit or MeritSpec(),
    )


class TestImageTerms:
    def test_transverse_merit_of_a_defocused_perfect_lens(self):
        dz, semi = 0.0005, 0.002
        lens = ideal(dz, semi, merit=MeritSpec(kind="transverse", reference="centroid"))
        a = dz * semi / F  # ideal lens: tan(u') = h / f exactly
        rep = merit_report(lens)
        assert rep["configurations"][0]["image_rms"] == pytest.approx(a / math.sqrt(2), rel=1e-9)
        # about the chief ray the on-axis spot is the same
        chief = merit_report(lens.model_copy(update={"merit": MeritSpec(reference="chief")}))
        assert chief["configurations"][0]["image_rms"] == pytest.approx(a / math.sqrt(2), rel=1e-9)

    def test_wavefront_merit_of_a_defocused_perfect_lens(self):
        # W020 = dz (1 - cos u') holds to first order in dz / f (5e-4 here)
        dz, semi = 0.00005, 0.002
        lens = ideal(dz, semi, merit=MeritSpec(kind="wavefront", rings=4))
        u = math.atan(semi / F)
        w020 = dz * (1 - math.cos(u))
        rms = merit_report(lens)["configurations"][0]["image_rms"]
        assert rms == pytest.approx(w020 / math.sqrt(12) / WL, rel=1e-3)
        assert property_value("wavefront_rms", to_system(lens), 0) == pytest.approx(rms, rel=1e-6)

    def test_spot_rms_property_matches_the_merit(self):
        dz, semi = 0.0005, 0.002
        lens = ideal(dz, semi)
        assert property_value("spot_rms", to_system(lens), 0) == pytest.approx(
            dz * semi / F / math.sqrt(2), rel=1e-9)

    def test_image_weight_zero_leaves_only_operands(self):
        lens = ideal(0.0005, merit=MeritSpec(image_weight=0.0, operands=[
            Operand(kind="efl", target=0.09, weight=10.0)]))
        rep = merit_report(lens)["configurations"][0]
        assert rep["image_contribution"] == 0.0
        assert rep["operands"][0]["value"] == pytest.approx(F)
        assert rep["merit"] == pytest.approx((10.0 * 0.01) ** 2)


class TestProperties:
    def test_chief_ray_through_an_ideal_lens_at_its_stop(self):
        th = 5.0
        s = to_system(ideal(field_deg=th))
        assert property_value("image_height", s) == pytest.approx(F * math.tan(math.radians(th)), rel=1e-12)
        assert property_value("chief_ray_angle", s) == pytest.approx(math.radians(th), rel=1e-12)
        assert property_value("distortion", s) == pytest.approx(0.0, abs=1e-12)

    def test_stop_at_the_front_focal_plane_is_telecentric(self):
        s = to_system(ideal(stop_gap=F, field_deg=5.0))
        assert property_value("chief_ray_angle", s) == pytest.approx(0.0, abs=1e-12)

    def test_colour_of_a_dispersive_ideal_lens(self):
        # stop d in front of the lens: the chief ray meets it at y = d tan(theta)
        # and leaves at tan(theta) - y / f(lambda), reaching the image plane
        # (L = f behind) at Y = y + L (tan(theta) - y / f(lambda))
        lo, hi = 486.1327e-9, 656.2725e-9
        th, d = 5.0, 0.03
        s = to_system(ideal(stop_gap=d, field_deg=th, wavelengths=(lo, WL, hi)))
        n = {wl: refractive_index("N-BK7", wl) for wl in (lo, WL, hi)}
        f = {wl: F * (n[WL] - 1) / (n[wl] - 1) for wl in (lo, hi)}
        assert property_value("axial_color", s) == pytest.approx(f[hi] - f[lo], rel=1e-9)
        t = math.tan(math.radians(th))
        y = d * t
        Y = {wl: y + F * (t - y / f[wl]) for wl in (lo, hi)}
        assert property_value("lateral_color", s) == pytest.approx(
            abs(Y[hi]) - abs(Y[lo]), rel=1e-9)

    def test_seidel_operand_matches_the_published_triplet(self):
        s = to_system(SASIAN_TRIPLET.build())
        assert property_value("seidel_S1", s) / 1e-3 == pytest.approx(0.010973, abs=1.5e-6)
        assert property_value("seidel_S4", s) / 1e-3 == pytest.approx(0.036297, abs=1.5e-6)

    def test_distortion_matches_the_field_plot(self):
        from optics.image_quality import field_plots

        s = to_system(SASIAN_TRIPLET.build())
        full = field_plots(s, points=2)["distortion"][-1]
        assert property_value("distortion", s) == pytest.approx(full, rel=1e-9)

    def test_unknown_field_is_reported(self):
        with pytest.raises(ValueError, match="Field 7 does not exist"):
            property_value("image_height", to_system(ideal(field_deg=5)), 7)


class TestOptimizing:
    def test_spherical_operand_finds_coddingtons_best_form(self):
        # a thin f/20 singlet (object at infinity), EFL held; minimising
        # |S-I| alone must reach the minimum-spherical bending
        n = refractive_index("N-BK7", WL)
        lens = LensData(
            surfaces=[
                LensSurface(radius=0.05, thickness=0.0005, material="N-BK7",
                            semi_diameter=0.0025, is_stop=True, variables=["radius"]),
                LensSurface(radius=-0.2, thickness=0.098, variables=["radius"]),
            ],
            object_distance=None, wavelengths=[WL],
            analysis_settings=AnalysisSettings(wavelength=WL),
            constraints=[Constraint(kind="efl", target=F)],
            merit=MeritSpec(image_weight=0.0, operands=[Operand(kind="seidel_S1", weight=1.0)]),
        )
        out = optimize(lens, max_evaluations=400)
        assert out["success"]
        r1, r2 = out["variables"]["0.radius"], out["variables"]["1.radius"]
        q = (r2 + r1) / (r2 - r1)
        # thin-lens formula; the 0.5 mm thickness shifts it by well under 1 %
        assert q == pytest.approx(2 * (n * n - 1) / (n + 2), rel=0.01)

    def test_telecentric_constraint_moves_the_stop_to_the_focal_plane(self):
        lens = ideal(stop_gap=0.04, field_deg=5.0).model_copy(deep=True)
        lens.surfaces[0].variables = ["thickness"]
        lens.constraints = [Constraint(kind="chief_ray_angle", target=0.0)]
        lens = LensData.model_validate(lens.model_dump())
        out = optimize(lens, max_evaluations=200)
        assert out["success"]
        assert out["variables"]["0.thickness"] == pytest.approx(F, rel=1e-6)

    def test_wavefront_merit_focus_is_the_minimum_rms(self):
        # vary only the back focus: the optimum is the minimum of the
        # reported RMS wavefront (found here by a 1-D search)
        from scipy.optimize import minimize_scalar

        base = SASIAN_TRIPLET.build().model_copy(deep=True)
        base.merit = MeritSpec(kind="wavefront")
        base.surfaces[5].variables = ["thickness"]
        base = LensData.model_validate(base.model_dump())
        out = optimize(base, max_evaluations=200)

        def rms(t):
            trial = base.model_copy(deep=True)
            trial.surfaces[5].thickness = t
            trial.surfaces[5].variables = []
            return merit_report(trial)["configurations"][0]["image_rms"]

        t0 = base.surfaces[5].thickness
        ref = minimize_scalar(rms, bounds=(t0 - 0.002, t0 + 0.002), method="bounded",
                              options={"xatol": 1e-9})
        assert out["variables"]["5.thickness"] == pytest.approx(ref.x, abs=2e-7)


class TestModel:
    def test_operand_validation(self):
        with pytest.raises(ValueError, match="needs a surface"):
            Operand(kind="edge_thickness")
        with pytest.raises(ValueError, match="does not take a field"):
            Operand(kind="efl", field=1)
        with pytest.raises(ValueError, match="configuration 3 does not exist"):
            ideal(merit=MeritSpec(operands=[Operand(kind="efl", configuration=3)]))

    def test_report_lists_operands_per_configuration(self):
        lens = ideal(0.0002, merit=MeritSpec(operands=[
            Operand(kind="efl", target=0.1),
            Operand(kind="center_thickness", surface=0, target=0.1, weight=2.0),
        ]))
        rep = merit_report(lens)
        ops = rep["configurations"][0]["operands"]
        assert [o["index"] for o in ops] == [0, 1]
        assert ops[1]["value"] == pytest.approx(0.1002)
        assert ops[1]["contribution"] == pytest.approx((2.0 * 0.0002) ** 2)
        assert rep["merit"] == pytest.approx(rep["configurations"][0]["merit"])


def test_merit_api():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    lens = ideal(0.0005, merit=MeritSpec(reference="centroid", operands=[
        Operand(kind="efl", target=0.1)])).model_dump()
    r = client.post("/api/lens/merit", json={"lens": lens})
    assert r.status_code == 200
    body = r.json()
    assert body["configurations"][0]["image_rms"] == pytest.approx(0.0005 * 0.02 / math.sqrt(2), rel=1e-9)
    opt = dict(lens)
    opt["surfaces"] = [dict(lens["surfaces"][0], variables=["thickness"])]
    r = client.post("/api/lens/optimize", json={"lens": opt, "max_evaluations": 60})
    assert r.status_code == 200
    out = r.json()
    assert out["image_kind"] == "transverse"
    assert out["rms_spot_after"] < out["rms_spot_before"]
    assert "merit_report" in out and "merit_report_before" in out
