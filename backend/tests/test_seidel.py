"""
Seidel (third-order) aberration tests against independent results.

References:
- Spherical mirror, object at infinity: third-order longitudinal spherical
  aberration h^2 / (4R) (e.g. W. J. Smith, Modern Optical Engineering).
- Paraboloid, object at infinity: no spherical aberration at any order.
- Petzval: image-surface sag -h'^2 / 2 * sum c (n' - n) / (n n') for an
  image in air (Welford, Aberrations of Optical Systems, ch. 8).
- Third-order values must approach exact real-ray values as the aperture
  and field shrink, and scale as the third-order power laws.
- An ideal (paraxial) lens images every conjugate without aberration.
"""

import math

import pytest

from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Mirror, Object, ImagePlane, AnalysisSettings,
)
from optics.materials import refractive_index
from optics.raytrace import first_order
from optics.seidel import (
    spherical_aberration, coma, astigmatism_and_field_curvature,
    distortion, seidel_analysis,
)

WL = 550e-9


def settings():
    return AnalysisSettings(num_rays=11, ray_types=["chief", "marginal", "fill"],
                            aperture_fraction=1.0, wavelength=WL)


def focused(system):
    z = first_order(system).image_z
    return system.model_copy(update={"image_plane": ImagePlane(position=z)})


def singlet(aperture=0.004, object_height=0.0005):
    """Equiconvex N-BK7 singlet, R = +/-51.5 mm, 5 mm thick, near 1:1."""
    return focused(OpticalSystem(
        components=[ThickLens(id="L1", position=0.100, radius1=0.0515, radius2=-0.0515,
                              thickness=0.005, aperture_diameter=aperture, material="N-BK7")],
        wavelengths=[WL],
        object=Object(position=0.0, height=object_height),
        image_plane=ImagePlane(position=0.3),
        analysis_settings=settings(),
    ))


def mirror(conic, radius=-1.0, diameter=0.1):
    """Concave mirror at z = 0.5, object effectively at infinity."""
    far = 1.0e6
    return focused(OpticalSystem(
        components=[Mirror(id="M1", position=0.5, angle=0.0, width=diameter,
                           radius=radius, conic=conic)],
        wavelengths=[WL],
        object=Object(position=-far, height=far * math.tan(math.radians(0.25))),
        image_plane=ImagePlane(position=0.0),
        analysis_settings=settings(),
    ))


def ideal_relay():
    return focused(OpticalSystem(
        components=[
            ThinLens(id="L1", position=0.100, focal_length=0.050, aperture_diameter=0.025),
            ThinLens(id="L2", position=0.150, focal_length=0.050, aperture_diameter=0.025),
        ],
        wavelengths=[WL],
        object=Object(position=0.0, height=0.010),
        image_plane=ImagePlane(position=0.175),
        analysis_settings=settings(),
    ))


class TestSphericalAberration:

    def test_spherical_mirror_matches_h2_over_4r(self):
        sa = spherical_aberration(mirror(conic=0.0))
        assert abs(sa["longitudinal"]) == pytest.approx(0.05 ** 2 / (4 * 1.0), rel=1e-9)

    def test_paraboloid_has_none(self):
        r = seidel_analysis(mirror(conic=-1.0))
        assert abs(r["spherical_aberration"]["longitudinal"]) < 1e-15
        assert abs(r["real"]["longitudinal_spherical"]) < 1e-12

    def test_third_order_matches_real_rays_at_small_aperture(self):
        r = seidel_analysis(singlet(aperture=0.002))
        assert r["spherical_aberration"]["transverse"] == pytest.approx(
            r["real"]["transverse_spherical"], rel=2e-3)

    def test_transverse_spherical_scales_as_aperture_cubed(self):
        small = spherical_aberration(singlet(aperture=0.002))["transverse"]
        large = spherical_aberration(singlet(aperture=0.004))["transverse"]
        assert large / small == pytest.approx(8.0, rel=1e-9)

    def test_ideal_lenses_have_none(self):
        sa = spherical_aberration(ideal_relay())
        assert sa["longitudinal"] == 0.0
        assert sa["transverse"] == 0.0


class TestComa:

    def test_third_order_matches_real_rays_at_small_aperture_and_field(self):
        r = seidel_analysis(singlet(aperture=0.002, object_height=0.0005))
        assert r["coma"] == pytest.approx(r["real"]["tangential_coma"], rel=0.03)

    def test_coma_scales_with_aperture_squared_and_field(self):
        base = coma(singlet(aperture=0.002, object_height=0.0005))
        assert coma(singlet(aperture=0.004, object_height=0.0005)) / base == pytest.approx(4.0, rel=1e-9)
        assert coma(singlet(aperture=0.002, object_height=0.001)) / base == pytest.approx(2.0, rel=1e-9)

    def test_ideal_lenses_have_none(self):
        assert coma(ideal_relay()) == 0.0


class TestAstigmatismAndFieldCurvature:

    def test_petzval_matches_surface_curvature_sum(self):
        system = singlet()
        n = refractive_index("N-BK7", WL)
        c = 1.0 / 0.0515
        petzval_sum = c * (n - 1.0) / n + (-c) * (1.0 - n) / n
        h_img = first_order(system).image_height
        r = astigmatism_and_field_curvature(system)
        assert r["petzval"] == pytest.approx(-h_img ** 2 * petzval_sum / 2.0, rel=1e-6)

    def test_astigmatism_scales_with_field_squared(self):
        a1 = astigmatism_and_field_curvature(singlet(object_height=0.0005))["astigmatism"]
        a2 = astigmatism_and_field_curvature(singlet(object_height=0.001))["astigmatism"]
        assert a2 / a1 == pytest.approx(4.0, rel=1e-9)

    def test_ideal_lenses_have_no_astigmatism(self):
        assert astigmatism_and_field_curvature(ideal_relay())["astigmatism"] == 0.0


class TestDistortion:

    def test_fractional_distortion_scales_with_field_squared(self):
        d1 = distortion(singlet(object_height=0.0005))
        d2 = distortion(singlet(object_height=0.001))
        assert d2 / d1 == pytest.approx(4.0, rel=1e-9)

    def test_ideal_lenses_have_none(self):
        assert distortion(ideal_relay()) == 0.0


class TestSeidelAnalysis:

    def test_wavefront_coefficients_follow_the_sums(self):
        r = seidel_analysis(singlet())
        s = r["seidel_sums"]
        w = r["wavefront_coefficients"]
        assert w["W040"] == pytest.approx(s["S1"] / 8.0)
        assert w["W131"] == pytest.approx(s["S2"] / 2.0)
        assert w["W222"] == pytest.approx(s["S3"] / 2.0)
        assert w["W220"] == pytest.approx((s["S3"] + s["S4"]) / 4.0)
        assert w["W311"] == pytest.approx(s["S5"] / 2.0)

    def test_per_surface_contributions_add_up(self):
        r = seidel_analysis(singlet())
        for key in ("S1", "S2", "S3", "S4", "S5"):
            total = sum(row[key] for row in r["per_surface"])
            assert total == pytest.approx(r["seidel_sums"][key], rel=1e-12, abs=1e-30)

    def test_empty_system_is_rejected(self):
        system = OpticalSystem(components=[], wavelengths=[WL],
                               object=Object(position=0.0, height=0.001),
                               image_plane=ImagePlane(position=0.1),
                               analysis_settings=settings())
        with pytest.raises(ValueError):
            seidel_analysis(system)

    def test_afocal_system_is_rejected(self):
        far = 1.0e5
        system = OpticalSystem(
            components=[ThinLens(id="L1", position=far, focal_length=0.1, aperture_diameter=0.02),
                        ThinLens(id="L2", position=far + 0.15, focal_length=0.05,
                                 aperture_diameter=0.02)],
            wavelengths=[WL], object=Object(position=0.0, height=1000.0),
            image_plane=ImagePlane(position=far + 0.3), analysis_settings=settings())
        with pytest.raises(ValueError):
            seidel_analysis(system)
