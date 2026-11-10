"""
Polarization ray tracing through the prescription, against closed forms
(M. Born and E. Wolf, Principles of Optics, 1.5; H. A. Macleod,
Thin-Film Optical Filters, ch. 2-3):

- Fresnel at normal incidence: R = ((n - 1) / (n + 1))^2 per bare surface;
- at incidence theta (refraction angle theta_t):
  Rs = (sin(theta - theta_t) / sin(theta + theta_t))^2 and
  Rp = (tan(theta - theta_t) / tan(theta + theta_t))^2; no retardance in
  transmission through a dielectric;
- at Brewster's angle, theta_B = atan(n), Rp = 0;
- a quarter-wave layer n1 on a substrate ns at its design wavelength:
  R = ((n0 ns - n1^2) / (n0 ns + n1^2))^2;
- an ideal mirror is lossless and changes no polarization.
"""

import math

import numpy as np
import pytest

from optics.coating_spec import CoatingLayer, CoatingSpec
from optics.coatings.layer import Layer
from optics.coatings.transfer_matrix import reflection_transmission
from optics.lens_data import LensData, LensSurface, to_system
from optics.materials import refractive_index
from optics.models import AnalysisSettings, FieldPoint
from optics.polarization_trace import (
    jones_matrices,
    jones_properties,
    polarization_rays,
    pupil_map,
    transmission_coefficients,
    transmittance,
)

WL = 550e-9


def plate(theta_deg=0.0, front=None, back=None, glass="N-BK7") -> LensData:
    """A 5 mm flat plate met by a collimated beam at theta."""
    th = math.radians(theta_deg)
    return LensData(
        surfaces=[
            LensSurface(label="STO", is_stop=True, semi_diameter=0.004, thickness=0.01),
            LensSurface(thickness=0.005, material=glass, semi_diameter=0.02, coating=front),
            LensSurface(thickness=0.05, semi_diameter=0.02, coating=back),
        ],
        object_distance=None, field_angle=th,
        fields=[FieldPoint(y=th)], field_type="angle",
        wavelengths=[WL], analysis_settings=AnalysisSettings(wavelength=WL),
    )


def chief(lens: LensData) -> dict:
    system = to_system(lens)
    from optics.fields import resolve_fields

    tracing, fields = resolve_fields(system)
    f = fields[0]
    rays = polarization_rays(tracing, f.hx, f.hy, [0.0], [0.0], WL)
    J = jones_matrices(rays)
    return {"J": J[0], **{k: v[0] for k, v in jones_properties(J).items()}}


def fresnel(theta, n):
    tt = math.asin(math.sin(theta) / n)
    if theta == 0:
        r = ((n - 1) / (n + 1)) ** 2
        return r, r
    rs = (math.sin(theta - tt) / math.sin(theta + tt)) ** 2
    rp = (math.tan(theta - tt) / math.tan(theta + tt)) ** 2
    return rs, rp


class TestBareSurfaces:
    def test_normal_incidence(self):
        n = refractive_index("N-BK7", WL)
        r = chief(plate())
        R = ((n - 1) / (n + 1)) ** 2
        assert r["transmittance"] == pytest.approx((1 - R) ** 2, rel=1e-12)
        assert r["diattenuation"] == pytest.approx(0.0, abs=1e-12)
        assert r["retardance"] == pytest.approx(0.0, abs=1e-12)

    @pytest.mark.parametrize("theta_deg", [15.0, 30.0, 50.0])
    def test_oblique_plate(self, theta_deg):
        n = refractive_index("N-BK7", WL)
        rs, rp = fresnel(math.radians(theta_deg), n)
        Ts, Tp = (1 - rs) ** 2, (1 - rp) ** 2
        r = chief(plate(theta_deg))
        assert r["transmittance"] == pytest.approx((Ts + Tp) / 2, rel=1e-10)
        assert r["diattenuation"] == pytest.approx((Tp - Ts) / (Tp + Ts), rel=1e-8)
        assert r["retardance"] == pytest.approx(0.0, abs=1e-10)
        # the s state (across the plane of incidence, here x) is the one losing more
        J = r["J"]
        assert abs(J[0, 0]) ** 2 == pytest.approx(Ts, rel=1e-10)
        assert abs(J[1, 1]) ** 2 == pytest.approx(Tp, rel=1e-10)

    def test_brewster_window_passes_p_completely(self):
        n = refractive_index("N-BK7", WL)
        r = chief(plate(math.degrees(math.atan(n))))
        assert abs(r["J"][1, 1]) ** 2 == pytest.approx(1.0, abs=1e-12)

    def test_coefficients_are_power_normalised(self):
        n = 1.7
        cos_i = np.cos(np.radians([0.0, 20.0, 40.0]))
        ts, tp = transmission_coefficients(1.0, n, cos_i, WL)
        for c, a, b in zip(cos_i, ts, tp):
            rs, rp = fresnel(math.acos(c), n)
            assert abs(a) ** 2 == pytest.approx(1 - rs, rel=1e-12)
            assert abs(b) ** 2 == pytest.approx(1 - rp, rel=1e-12)


class TestCoatings:
    def test_quarter_wave_mgf2(self):
        qw = CoatingSpec.quarter_wave("MgF2", WL)
        n1 = refractive_index("MgF2", WL)
        ns = refractive_index("N-BK7", WL)
        assert qw.layers[0].thickness == pytest.approx(WL / (4 * n1))
        r = chief(plate(front=qw))
        R_coat = ((ns - n1**2) / (ns + n1**2)) ** 2
        R_bare = ((ns - 1) / (ns + 1)) ** 2
        assert r["transmittance"] == pytest.approx((1 - R_coat) * (1 - R_bare), rel=1e-10)

    def test_coated_surface_retardance_matches_the_thin_film_phases(self):
        # a two-layer stack at 40 degrees: retardance = |arg(t_p) - arg(t_s)|
        stack = CoatingSpec(layers=[
            CoatingLayer(material="TiO2", thickness=70e-9),
            CoatingLayer(material="MgF2", thickness=120e-9),
        ])
        theta = math.radians(40.0)
        n = refractive_index("N-BK7", WL)
        r = chief(plate(40.0, front=stack))
        layers = [Layer(material="TiO2", thickness=70.0, n=refractive_index("TiO2", WL)),
                  Layer(material="MgF2", thickness=120.0, n=refractive_index("MgF2", WL))]
        _, Ts, _, ts = reflection_transmission(layers, WL * 1e9, 1.0, n, theta, "s")
        _, Tp, _, tp = reflection_transmission(layers, WL * 1e9, 1.0, n, theta, "p")
        expected = abs(np.angle(tp / ts))
        assert r["retardance"] == pytest.approx(expected, abs=1e-9)
        rs, rp = fresnel(theta, n)  # the bare back surface
        assert abs(r["J"][0, 0]) ** 2 == pytest.approx(Ts * (1 - rs), rel=1e-9)
        assert abs(r["J"][1, 1]) ** 2 == pytest.approx(Tp * (1 - rp), rel=1e-9)

    def test_layer_needs_material_or_index(self):
        with pytest.raises(ValueError, match="material or an index"):
            CoatingLayer(thickness=1e-7)


class TestSystems:
    def test_ideal_mirror_is_lossless_and_non_polarizing(self):
        lens = LensData(
            surfaces=[LensSurface(radius=-0.5, material="MIRROR", is_stop=True,
                                  semi_diameter=0.02, thickness=-0.25)],
            object_distance=None, wavelengths=[WL],
            analysis_settings=AnalysisSettings(wavelength=WL),
        )
        m = pupil_map(to_system(lens), 0, WL, grid=9)
        inside = ~np.isnan(m["transmittance"])
        np.testing.assert_allclose(m["transmittance"][inside], 1.0, atol=1e-12)
        np.testing.assert_allclose(m["diattenuation"][inside], 0.0, atol=1e-12)
        np.testing.assert_allclose(m["retardance"][inside], 0.0, atol=1e-9)

    def test_singlet_transmission(self):
        def singlet(coating=None):
            return LensData(
                surfaces=[
                    LensSurface(radius=0.05, thickness=0.005, material="N-BK7",
                                semi_diameter=0.01, is_stop=True, coating=coating),
                    LensSurface(radius=-0.05, thickness=0.045, coating=coating),
                ],
                object_distance=None, wavelengths=[WL],
                analysis_settings=AnalysisSettings(wavelength=WL),
            )
        n = refractive_index("N-BK7", WL)
        bare = pupil_map(to_system(singlet()), 0, WL, grid=11)
        centre = bare["transmittance"][5, 5]
        assert centre == pytest.approx((1 - ((n - 1) / (n + 1)) ** 2) ** 2, rel=1e-12)
        # steeper rays at the pupil edge lose more (apodization)
        assert np.nanmin(bare["transmittance"]) < centre
        qw = CoatingSpec.quarter_wave("MgF2", WL)
        t_bare = transmittance(to_system(singlet()))["transmittance"]
        t_coat = transmittance(to_system(singlet(qw)))["transmittance"]
        assert t_coat > t_bare + 0.01

    def test_coating_round_trips_the_lens_model(self):
        qw = CoatingSpec.quarter_wave("MgF2", WL)
        lens = plate(front=qw)
        from optics import raytrace as rt

        seq = rt.build_sequence(to_system(lens), WL)
        coated = [s for s in seq.surfaces if s.coating]
        assert len(coated) == 1
        assert CoatingSpec.model_validate(coated[0].coating) == qw


def test_polarization_api():
    from fastapi.testclient import TestClient

    from api.main import app

    system = to_system(plate(30.0)).model_dump()
    r = TestClient(app).post("/api/analyze/polarization",
                             json={"system": system, "field": 0, "grid": 7})
    assert r.status_code == 200
    body = r.json()
    assert len(body["transmittance"]) == 7
    n = refractive_index("N-BK7", WL)
    rs, rp = fresnel(math.radians(30.0), n)
    assert body["summary"]["transmittance"] == pytest.approx(
        ((1 - rs) ** 2 + (1 - rp) ** 2) / 2, rel=1e-6)
