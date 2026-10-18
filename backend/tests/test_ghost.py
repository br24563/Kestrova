"""
Tests for real-ray ghost analysis (roadmap item 11).

Covers the Fresnel reflectance model, the flattened surface chain, the
bidirectional ghost path tracer (forward -> reflect -> backward -> reflect
-> forward -> image), and the system-level ghost ranking.

The reference system is a two-thin-lens relay whose paraxial image lands at
z = 175 mm. Its four surfaces are L1.front, L1.back, L2.front, L2.back, so
the surface chain is 4 long and there are 6 double-reflection ghost orders.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from optics.ghost import (
    GhostSurface, GhostResult,
    normal_incidence_reflectance, fresnel_reflectance,
    build_surface_chain, trace_ghost_path, chief_ray, pupil_fan,
    primary_image_height, analyze_ghosts, ghost_analysis,
    N_AIR,
)
from optics.models import (
    OpticalSystem, ThinLens, ThickLens, SphericalSurface, Mirror,
    ApertureStop, Object, ImagePlane, AnalysisSettings, Ray,
)

# Paraxial image of the relay below.
PARAXIAL_IMAGE_Z = 0.175

# Fresnel reflectance of an uncoated N-BK7/air interface near 550 nm.
BK7_ND = 1.5168
BK7_R0 = ((1.0 - BK7_ND) / (1.0 + BK7_ND)) ** 2      # ~0.042164


def create_focused_system(image_z=PARAXIAL_IMAGE_Z):
    """Two-lens relay with the image plane at the paraxial focus."""
    return OpticalSystem(
        components=[
            ThinLens(id="L1", position=0.100, focal_length=0.050,
                     aperture_diameter=0.025, material="N-BK7"),
            ThinLens(id="L2", position=0.150, focal_length=0.050,
                     aperture_diameter=0.025, material="N-BK7"),
        ],
        wavelengths=[550e-9],
        object=Object(position=0.0, height=0.010, orientation=0.0),
        image_plane=ImagePlane(position=image_z),
        analysis_settings=AnalysisSettings(
            num_rays=11, ray_types=["chief", "marginal", "fill"],
            aperture_fraction=1.0, wavelength=550e-9,
        ),
    )


def create_stopped_system():
    """Relay with a stop between the lenses (a stop is not a surface)."""
    system = create_focused_system()
    system.components.append(
        ApertureStop(id="STO", position=0.125, diameter=0.020))
    return system


class TestNormalIncidenceReflectance:
    """Fresnel reflectance at normal incidence."""

    def test_bk7_front_surface(self):
        assert normal_incidence_reflectance(1.0, BK7_ND) == pytest.approx(
            BK7_R0, rel=1e-9)

    def test_matches_the_closed_form(self):
        for n in (1.33, 1.5, 1.62, 2.4, 3.5):
            expected = ((1.0 - n) / (1.0 + n)) ** 2
            assert normal_incidence_reflectance(1.0, n) == pytest.approx(expected)

    def test_is_symmetric_in_the_two_media(self):
        assert normal_incidence_reflectance(1.0, 1.5) == pytest.approx(
            normal_incidence_reflectance(1.5, 1.0))

    def test_no_contrast_means_no_reflection(self):
        assert normal_incidence_reflectance(1.5, 1.5) == pytest.approx(0.0)

    def test_increases_with_index_contrast(self):
        values = [normal_incidence_reflectance(1.0, n)
                  for n in (1.33, 1.52, 1.75, 2.4, 4.0)]
        assert all(b > a for a, b in zip(values, values[1:]))

    def test_degenerate_media_are_safe(self):
        assert normal_incidence_reflectance(0.0, 0.0) == 0.0
        assert normal_incidence_reflectance(-1.0, 1.0) == 0.0

    def test_glass_to_glass_interface(self):
        assert normal_incidence_reflectance(1.5168, 1.6204) == pytest.approx(
            normal_incidence_reflectance(1.6204, 1.5168))


class TestFresnelReflectance:
    """Angle- and polarization-resolved Fresnel reflectance."""

    def test_normal_incidence_matches_the_simple_form(self):
        assert fresnel_reflectance(1.0, BK7_ND, 0.0) == pytest.approx(BK7_R0)

    def test_normal_incidence_s_and_p_agree(self):
        assert fresnel_reflectance(1.0, 1.5, 0.0, "s") == pytest.approx(
            fresnel_reflectance(1.0, 1.5, 0.0, "p"))

    def test_avg_is_the_mean_of_s_and_p(self):
        theta = math.radians(50.0)
        rs = fresnel_reflectance(1.0, 1.5, theta, "s")
        rp = fresnel_reflectance(1.0, 1.5, theta, "p")
        assert fresnel_reflectance(1.0, 1.5, theta, "avg") == pytest.approx(
            0.5 * (rs + rp))

    def test_reflectance_rises_with_incidence_angle(self):
        values = [fresnel_reflectance(1.0, BK7_ND, math.radians(a))
                  for a in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 85.0)]
        assert all(b > a for a, b in zip(values, values[1:]))

    def test_grazing_incidence_approaches_unity(self):
        assert fresnel_reflectance(1.0, 1.5, math.radians(89.9)) > 0.9

    def test_s_polarization_reflects_at_least_as_much_as_p(self):
        for a in (5.0, 20.0, 45.0, 70.0, 85.0):
            theta = math.radians(a)
            rs = fresnel_reflectance(1.0, BK7_ND, theta, "s")
            rp = fresnel_reflectance(1.0, BK7_ND, theta, "p")
            assert rs >= rp - 1e-12

    def test_p_polarization_vanishes_at_brewster(self):
        # Brewster angle for air -> glass is atan(n2 / n1).
        theta_b = math.atan(BK7_ND)
        assert fresnel_reflectance(1.0, BK7_ND, theta_b, "p") == pytest.approx(
            0.0, abs=1e-3)
        assert fresnel_reflectance(1.0, BK7_ND, theta_b, "s") > 0.1

    def test_total_internal_reflection(self):
        critical = math.asin(1.0 / BK7_ND)          # ~41.2 degrees
        assert fresnel_reflectance(BK7_ND, 1.0, critical + 0.1) == 1.0
        assert fresnel_reflectance(BK7_ND, 1.0, math.radians(60.0)) == 1.0
        assert fresnel_reflectance(BK7_ND, 1.0, math.radians(30.0)) < 1.0

    def test_polarization_aliases(self):
        theta = math.radians(40.0)
        for name in ("s", "S"):
            assert fresnel_reflectance(1.0, 1.5, theta, name) == pytest.approx(
                fresnel_reflectance(1.0, 1.5, theta, "s"))
        for name in ("p", "P"):
            assert fresnel_reflectance(1.0, 1.5, theta, name) == pytest.approx(
                fresnel_reflectance(1.0, 1.5, theta, "p"))

    def test_invalid_indices_are_safe(self):
        assert fresnel_reflectance(0.0, 1.5) == 0.0
        assert fresnel_reflectance(1.5, 0.0) == 0.0


class TestSurfaceChain:
    """Flattening a system into an ordered list of surfaces."""

    def test_two_thin_lenses_give_four_surfaces(self):
        chain = build_surface_chain(create_focused_system())
        assert len(chain) == 4
        assert [s.label for s in chain] == [
            "L1.front", "L1.back", "L2.front", "L2.back"]

    def test_indices_are_sequential_and_sorted_by_position(self):
        chain = build_surface_chain(create_focused_system())
        assert [s.index for s in chain] == [0, 1, 2, 3]
        zs = [s.z for s in chain]
        assert zs == sorted(zs)

    def test_first_surface_sits_at_the_element_position(self):
        chain = build_surface_chain(create_focused_system())
        assert chain[0].z == pytest.approx(0.100)
        assert chain[2].z == pytest.approx(0.150)

    def test_thin_lens_back_surface_is_behind_the_front(self):
        chain = build_surface_chain(create_focused_system())
        assert chain[1].z > chain[0].z
        # A biconvex estimate: sagitta plus a nominal edge thickness, so a
        # few millimetres for a 25 mm aperture f = 50 mm lens.
        assert 0.001 < (chain[1].z - chain[0].z) < 0.010

    def test_thin_lens_radii_are_opposite(self):
        chain = build_surface_chain(create_focused_system())
        # R = 2 (n - 1) f for the front, negated for the back.
        expected = 2.0 * (BK7_ND - 1.0) * 0.050
        assert chain[0].radius == pytest.approx(expected, rel=0.02)
        assert chain[1].radius == pytest.approx(-expected, rel=0.02)

    def test_media_are_air_glass_glass_air(self):
        chain = build_surface_chain(create_focused_system())
        assert chain[0].n_left == pytest.approx(N_AIR)
        assert chain[0].n_right == pytest.approx(BK7_ND, rel=0.02)
        assert chain[1].n_left == pytest.approx(chain[0].n_right)
        assert chain[1].n_right == pytest.approx(N_AIR)
        assert chain[2].n_left == pytest.approx(N_AIR)

    def test_no_surface_is_marked_reflective_for_lenses(self):
        chain = build_surface_chain(create_focused_system())
        assert not any(s.reflective for s in chain)

    def test_aperture_stop_is_not_a_surface(self):
        plain = build_surface_chain(create_focused_system())
        stopped = build_surface_chain(create_stopped_system())
        assert len(stopped) == len(plain) == 4

    def test_thick_lens_uses_its_real_thickness(self):
        system = OpticalSystem(
            components=[ThickLens(id="T1", position=0.050, radius1=0.030,
                                  radius2=-0.030, thickness=0.008,
                                  aperture_diameter=0.025,
                                  material="N-BK7")],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.005, orientation=0.0),
            image_plane=ImagePlane(position=0.120),
            analysis_settings=AnalysisSettings(num_rays=5, wavelength=550e-9),
        )
        chain = build_surface_chain(system)
        assert len(chain) == 2
        assert chain[0].z == pytest.approx(0.050)
        assert chain[1].z == pytest.approx(0.058)
        assert chain[0].radius == pytest.approx(0.030)
        assert chain[1].radius == pytest.approx(-0.030)

    def test_mirror_is_one_reflective_surface(self):
        system = OpticalSystem(
            components=[Mirror(id="M1", position=0.080, width=0.030,
                               aperture_diameter=0.030)],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.005, orientation=0.0),
            image_plane=ImagePlane(position=0.020),
            analysis_settings=AnalysisSettings(num_rays=5, wavelength=550e-9),
        )
        chain = build_surface_chain(system)
        assert len(chain) == 1
        assert chain[0].reflective is True
        assert chain[0].label == "M1.mirror"

    def test_spherical_surface_is_one_surface_with_air_on_the_left(self):
        system = OpticalSystem(
            components=[SphericalSurface(id="S1", position=0.050,
                                         radius=0.100,
                                         thickness=0.005,
                                         aperture_diameter=0.025,
                                         material="N-BK7")],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.005, orientation=0.0),
            image_plane=ImagePlane(position=0.100),
            analysis_settings=AnalysisSettings(num_rays=5, wavelength=550e-9),
        )
        chain = build_surface_chain(system)
        assert len(chain) == 1
        assert chain[0].n_left == pytest.approx(N_AIR)
        assert chain[0].n_right > 1.0
        assert chain[0].reflective is False

    def test_empty_system_has_no_surfaces(self):
        system = OpticalSystem(
            components=[],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.0, orientation=0.0),
            image_plane=ImagePlane(position=0.100),
            analysis_settings=AnalysisSettings(num_rays=5, wavelength=550e-9),
        )
        assert build_surface_chain(system) == []

    def test_wavelength_override_changes_the_index(self):
        system = create_focused_system()
        red = build_surface_chain(system, wavelength=650e-9)
        blue = build_surface_chain(system, wavelength=450e-9)
        # N-BK7 is more dispersive in the blue, so the index is higher there.
        assert blue[0].n_right > red[0].n_right


class TestGhostPathTracing:
    """The bidirectional forward/backward/forward ghost path."""

    @staticmethod
    def _trace(first, second, field_fraction=0.0, num_rays=5):
        system = create_focused_system()
        chain = build_surface_chain(system)
        rays = pupil_fan(system, field_fraction, num_rays)
        return chain, [trace_ghost_path(chain, r, first, second,
                                        system.image_plane.position)
                       for r in rays]

    @staticmethod
    def _first_path(results):
        return next(r[0] for r in results if r[0] is not None)

    def test_a_path_is_found_for_a_valid_pair(self):
        chain, results = self._trace(first=3, second=1)
        assert any(r[0] is not None for r in results)

    def test_path_starts_at_the_object_and_ends_at_the_image(self):
        chain, results = self._trace(first=3, second=1)
        path = self._first_path(results)
        assert path[0][0] == pytest.approx(0.0)
        assert path[-1][0] == pytest.approx(PARAXIAL_IMAGE_Z)

    def test_the_reflected_leg_travels_back_toward_the_object(self):
        chain, results = self._trace(first=3, second=1)
        zs = [p[0] for p in self._first_path(results)]
        backwards = [i for i in range(len(zs) - 1)
                     if zs[i + 1] < zs[i] - 1e-12]
        assert backwards, "a ghost ray must reverse direction after reflecting"

    def test_the_turning_point_is_the_first_reflecting_surface(self):
        # The first direction reversal along the path is the reflection
        # at ``first``. It is not the global maximum, because the image
        # plane sits beyond the last surface.
        chain, results = self._trace(first=3, second=1)
        zs = [p[0] for p in self._first_path(results)]
        k_turn = next(i for i in range(len(zs) - 1)
                      if zs[i + 1] < zs[i] - 1e-12)
        assert zs[k_turn] == pytest.approx(chain[3].z)

    def test_the_backward_leg_reaches_the_second_surface(self):
        # The second reversal, from travelling backward to forward
        # again, is the reflection at ``second``.
        chain, results = self._trace(first=3, second=1)
        zs = [p[0] for p in self._first_path(results)]
        k_turn = next(i for i in range(len(zs) - 1)
                      if zs[i + 1] < zs[i] - 1e-12)
        k_back = next(i for i in range(k_turn + 1, len(zs) - 1)
                      if zs[i + 1] > zs[i] + 1e-12)
        assert zs[k_back] == pytest.approx(chain[1].z)
        assert zs[k_back] < zs[k_turn]

    def test_direction_reverses_and_then_recovers(self):
        chain, results = self._trace(first=3, second=1)
        zs = [p[0] for p in self._first_path(results)]
        steps = [zs[i + 1] - zs[i] for i in range(len(zs) - 1)]
        assert any(s > 1e-12 for s in steps)          # forward
        assert any(s < -1e-12 for s in steps)         # backward
        assert steps[-1] > 0                          # into the image

    def test_a_shallower_first_surface_shortens_the_path(self):
        chain, results = self._trace(first=2, second=0)
        zs = [p[0] for p in self._first_path(results)]
        k_turn = next(i for i in range(len(zs) - 1)
                      if zs[i + 1] < zs[i] - 1e-12)
        assert zs[k_turn] == pytest.approx(chain[2].z)

    def test_every_reported_point_lands_on_a_surface_or_an_end(self):
        system = create_focused_system()
        chain = build_surface_chain(system)
        ray = chief_ray(system, 0.0)
        path, _, _, _, fail = trace_ghost_path(chain, ray, 3, 0,
                                               system.image_plane.position)
        assert fail is None
        known = {round(0.0, 12), round(PARAXIAL_IMAGE_Z, 12)}
        known |= {round(s.z, 12) for s in chain}
        for z, _y in path:
            assert round(z, 12) in known

    def test_second_must_be_before_first(self):
        chain, _ = self._trace(first=1, second=1)
        ray = chief_ray(create_focused_system(), 0.0)
        path, rf, rs, tr, fail = trace_ghost_path(
            chain, ray, 1, 1, PARAXIAL_IMAGE_Z)
        assert path is None
        assert fail == "invalid_pair"

    def test_out_of_range_indices_are_rejected(self):
        system = create_focused_system()
        chain = build_surface_chain(system)
        ray = chief_ray(system, 0.0)
        for first, second in ((4, 0), (9, 2), (2, -1)):
            path, _rf, _rs, _tr, fail = trace_ghost_path(
                chain, ray, first, second, PARAXIAL_IMAGE_Z)
            assert path is None
            assert fail == "invalid_pair"

    def test_reflectances_are_physical(self):
        chain, results = self._trace(first=3, second=0)
        ok = [r for r in results if r[0] is not None]
        assert ok
        _path, rf, rs, tr, _fail = ok[0]
        assert 0.0 < rf < 1.0
        assert 0.0 < rs < 1.0
        # Uncoated glass, so each reflection is a few percent.
        assert rf == pytest.approx(BK7_R0, rel=0.20)
        assert rs == pytest.approx(BK7_R0, rel=0.20)
        assert tr > 0.0

    def test_transmission_includes_every_surface_crossed(self):
        chain, results = self._trace(first=3, second=0)
        ok = [r for r in results if r[0] is not None]
        _path, rf, rs, tr, _fail = ok[0]
        # Two reflections, minus the (1 - R) losses of the transmitting legs.
        assert tr < rf * rs
        assert tr <= 1.0

    def test_rays_that_miss_are_reported_with_a_surface_label(self):
        # At the field edge the pupil fan is steep enough that some rays miss
        # the (biconvex) first surface, which is a genuine geometric block
        # rather than an aperture-stop block.
        chain, results = self._trace(first=2, second=0, field_fraction=1.0,
                                     num_rays=5)
        blocked = [r for r in results if r[0] is None]
        assert blocked, "expected at least one geometrically blocked ray"
        assert all(r[4] for r in blocked), "a block must name a surface"
        assert all(r[4] in {s.label for s in chain} for r in blocked)

    def test_mirror_may_be_the_first_reflector(self):
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.100, focal_length=0.050,
                         aperture_diameter=0.025, material="N-BK7"),
                Mirror(id="M1", position=0.160, width=0.030,
                       aperture_diameter=0.030),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.005, orientation=0.0),
            image_plane=ImagePlane(position=0.175),
            analysis_settings=AnalysisSettings(num_rays=5, wavelength=550e-9),
        )
        chain = build_surface_chain(system)
        assert chain[-1].reflective
        ray = chief_ray(system, 0.0)
        path, rf, rs, tr, fail = trace_ghost_path(
            chain, ray, 2, 0, system.image_plane.position,
            mirror_reflectance=0.95)
        assert fail is None
        assert rf == pytest.approx(0.95)          # the mirror
        assert 0.0 < rs < 1.0                     # the lens front surface
        assert tr > 0.0

    def test_coating_override_controls_the_reflectance(self):
        chain, _ = self._trace(first=2, second=0)
        ray = chief_ray(create_focused_system(), 0.0)
        path, rf, rs, _tr, fail = trace_ghost_path(
            chain, ray, 2, 0, PARAXIAL_IMAGE_Z, coating_reflectance=0.005)
        assert fail is None
        assert rf == pytest.approx(0.005)
        assert rs == pytest.approx(0.005)


class TestRayFanAndImageHeight:
    """The caller-side helpers that feed the ghost tracer."""

    def test_axial_chief_ray_is_horizontal(self):
        ray = chief_ray(create_focused_system(), 0.0)
        assert ray.y == pytest.approx(0.0)
        assert ray.theta == pytest.approx(0.0)

    def test_chief_ray_starts_at_the_object(self):
        system = create_focused_system()
        ray = chief_ray(system, 1.0)
        assert ray.z == pytest.approx(system.object.position)
        assert ray.y == pytest.approx(system.object.height)
        assert ray.wavelength == pytest.approx(550e-9)
        assert ray.ray_type == "chief"

    def test_chief_ray_aims_at_the_centre_of_the_first_element(self):
        system = create_focused_system()
        ray = chief_ray(system, 1.0)
        d = 0.100 - system.object.position
        assert ray.theta == pytest.approx(math.atan(-0.010 / d))

    def test_chief_ray_tilts_more_with_field(self):
        system = create_focused_system()
        thetas = [chief_ray(system, ff).theta for ff in (0.0, 0.25, 0.5, 1.0)]
        assert all(b < a for a, b in zip(thetas, thetas[1:]))

    def test_pupil_fan_size_and_field_height(self):
        system = create_focused_system()
        fan = pupil_fan(system, 1.0, 5)
        assert len(fan) == 5
        assert all(r.y == pytest.approx(system.object.height) for r in fan)
        assert all(r.ray_type == "fill" for r in fan)

    def test_pupil_fan_is_symmetric_about_the_chief_ray(self):
        system = create_focused_system()
        fan = pupil_fan(system, 0.0, 5)
        thetas = [r.theta for r in fan]
        assert thetas[0] == pytest.approx(-thetas[-1])
        assert thetas[2] == pytest.approx(0.0)

    def test_pupil_fan_angles_increase_monotonically(self):
        fan = pupil_fan(create_focused_system(), 0.0, 7)
        thetas = [r.theta for r in fan]
        assert all(b > a for a, b in zip(thetas, thetas[1:]))

    def test_pupil_fan_never_exceeds_the_entrance_semi_aperture(self):
        system = create_focused_system()
        fan = pupil_fan(system, 0.0, 9)
        semi = 0.025 / 2.0
        # Every ray must be inside the pupil when it reaches the first lens.
        for r in fan:
            y_at_lens = r.y + (0.100 - r.z) * math.tan(r.theta)
            assert abs(y_at_lens) <= semi * (1.0 + 1e-6)

    def test_single_ray_pupil_fan_is_the_chief_ray(self):
        system = create_focused_system()
        fan = pupil_fan(system, 0.5, 1)
        assert len(fan) == 1
        assert fan[0].theta == pytest.approx(chief_ray(system, 0.5).theta)

    def test_pupil_fan_without_an_aperture_is_axial(self):
        system = create_focused_system()
        for comp in system.components:
            comp.aperture_diameter = 0.0
        assert all(r.theta == 0.0 for r in pupil_fan(system, 0.0, 5))

    def test_primary_image_height_is_zero_on_axis(self):
        assert primary_image_height(create_focused_system(), 0.0) == pytest.approx(
            0.0, abs=1e-9)

    def test_primary_image_height_inverts_for_this_relay(self):
        assert primary_image_height(create_focused_system(), 1.0) < 0.0

    def test_primary_image_height_grows_with_field(self):
        system = create_focused_system()
        heights = [primary_image_height(system, ff) for ff in (0.0, 0.25, 0.5, 1.0)]
        assert all(abs(b) > abs(a) for a, b in zip(heights, heights[1:]))

    def test_primary_image_height_is_roughly_linear_in_field(self):
        system = create_focused_system()
        full = primary_image_height(system, 1.0)
        half = primary_image_height(system, 0.5)
        assert half == pytest.approx(0.5 * full, rel=0.1)


class TestAnalyzeGhosts:
    """Ranking and book-keeping of the double-reflection ghost orders."""

    def test_all_six_orders_are_found_on_axis(self):
        # Four surfaces give C(4, 2) = 6 double-reflection pairs.
        assert len(analyze_ghosts(create_focused_system(), 0.0)) == 6

    def test_results_are_sorted_brightest_first(self):
        irr = [g.relative_irradiance
               for g in analyze_ghosts(create_focused_system(), 0.0)]
        assert irr == sorted(irr, reverse=True)

    def test_the_second_surface_is_always_ahead_of_the_first(self):
        for g in analyze_ghosts(create_focused_system(), 0.0):
            assert 0 <= g.second_surface < g.first_surface

    def test_pairs_are_unique(self):
        pairs = [(g.first_surface, g.second_surface)
                 for g in analyze_ghosts(create_focused_system(), 0.0)]
        assert len(pairs) == len(set(pairs))

    def test_labels_agree_with_the_surface_chain(self):
        chain = build_surface_chain(create_focused_system())
        for g in analyze_ghosts(create_focused_system(), 0.0):
            assert g.first_label == chain[g.first_surface].label
            assert g.second_label == chain[g.second_surface].label

    def test_ray_book_keeping(self):
        for g in analyze_ghosts(create_focused_system(), 0.0, num_rays=7):
            assert g.num_rays_attempted == 7
            assert 1 <= g.num_rays <= 7

    def test_wavelength_is_carried_through(self):
        for g in analyze_ghosts(create_focused_system(), 0.0):
            assert g.wavelength == pytest.approx(550e-9)

    def test_reflectance_product_and_transmission(self):
        for g in analyze_ghosts(create_focused_system(), 0.0):
            assert g.reflectance_product == pytest.approx(
                g.first_reflectance * g.second_reflectance)
            assert g.relative_irradiance == pytest.approx(g.transmission)
            assert 0.0 < g.transmission < g.reflectance_product

    def test_displacement_is_ghost_minus_primary(self):
        for g in analyze_ghosts(create_focused_system(), 0.0):
            assert g.displacement == pytest.approx(
                g.ghost_image_height - g.primary_image_height)

    def test_all_ghosts_share_the_same_primary_reference(self):
        expected = primary_image_height(create_focused_system(), 0.0)
        for g in analyze_ghosts(create_focused_system(), 0.0):
            assert g.primary_image_height == pytest.approx(expected)

    def test_the_brightest_ghost_comes_from_adjacent_surfaces(self):
        # Adjacent-surface ghosts cross the fewest interfaces, so they lose
        # the least light to transmission and dominate in a real system.
        brightest = analyze_ghosts(create_focused_system(), 0.0)[0]
        assert brightest.first_surface - brightest.second_surface == 1

    def test_uncoated_ghost_is_a_fraction_of_a_percent(self):
        brightest = analyze_ghosts(create_focused_system(), 0.0)[0]
        assert 1.0e-4 < brightest.relative_irradiance < 1.0e-2

    def test_ar_coating_suppresses_every_ghost(self):
        system = create_focused_system()
        bare = analyze_ghosts(system, 0.0)
        coated = analyze_ghosts(system, 0.0, coating_reflectance=0.005)
        assert coated
        assert max(g.relative_irradiance for g in coated) < \
            max(g.relative_irradiance for g in bare) / 10.0

    def test_threshold_can_remove_every_ghost(self):
        assert analyze_ghosts(create_focused_system(), 0.0,
                              min_relative_irradiance=1.0) == []

    def test_explicit_surface_pairs(self):
        ghosts = analyze_ghosts(create_focused_system(), 0.0,
                                surface_pairs=[(0, 1)])
        assert len(ghosts) == 1
        assert ghosts[0].second_surface == 0
        assert ghosts[0].first_surface == 1

    def test_invalid_surface_pairs_are_ignored(self):
        assert analyze_ghosts(create_focused_system(), 0.0,
                              surface_pairs=[(2, 0), (5, 9)]) is not None
        ghosts = analyze_ghosts(create_focused_system(), 0.0,
                                surface_pairs=[(5, 9), (1, 1)])
        assert ghosts == []

    def test_axis_and_edge_share_the_same_pairs(self):
        system = create_focused_system()
        axis = {(g.first_surface, g.second_surface)
                for g in analyze_ghosts(system, 0.0)}
        edge = {(g.first_surface, g.second_surface)
                for g in analyze_ghosts(system, 1.0)}
        assert edge.issubset(axis)

    def test_system_with_one_surface_has_no_ghosts(self):
        system = OpticalSystem(
            components=[SphericalSurface(id="S1", position=0.050,
                                         radius=0.100,
                                         thickness=0.005,
                                         aperture_diameter=0.025,
                                         material="N-BK7")],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.005, orientation=0.0),
            image_plane=ImagePlane(position=0.100),
            analysis_settings=AnalysisSettings(num_rays=5, wavelength=550e-9),
        )
        assert analyze_ghosts(system, 0.0) == []


class TestGhostFocusAndBlocking:
    """Ghost focus location, spot statistics and blocked paths."""

    def test_focus_geometry_is_self_consistent(self):
        for g in analyze_ghosts(create_focused_system(), 0.0):
            assert g.ghost_focus_offset == pytest.approx(
                g.ghost_focus_z - PARAXIAL_IMAGE_Z)
            assert g.ghost_spot_rms >= 0.0
            assert g.ghost_spot_rms_at_image >= 0.0
            assert isinstance(g.focus_clipped, bool)
            assert math.isfinite(g.ghost_focus_z)

    def test_a_single_pupil_ray_has_no_spot_statistics(self):
        # One ray defines no spot, so the RMS values stay at zero rather
        # than reporting a meaningless number.
        ghosts = analyze_ghosts(create_focused_system(), 0.0, num_rays=1)
        assert ghosts
        assert all(g.ghost_spot_rms == 0.0 for g in ghosts)

    def test_a_multi_ray_fan_gives_a_positive_spot(self):
        ghosts = analyze_ghosts(create_focused_system(), 1.0, num_rays=9,
                                surface_pairs=[(2, 3)])
        assert ghosts
        assert ghosts[0].ghost_spot_rms > 0.0
        assert ghosts[0].ghost_spot_rms_at_image > 0.0

    def test_the_internal_lens_ghost_focuses_in_front_of_the_image(self):
        # The L2 front/back ghost is a weak negative lens: it focuses short
        # of the image plane by a noticeable fraction of the image distance.
        ghosts = analyze_ghosts(create_focused_system(), 0.0, num_rays=5,
                                surface_pairs=[(2, 3)])
        assert ghosts
        g = ghosts[0]
        assert g.ghost_focus_z < PARAXIAL_IMAGE_Z
        assert 0.005 < abs(g.ghost_focus_offset) < 0.050
        assert g.focus_clipped is False

    def test_a_narrow_focus_scan_reports_clipping(self):
        ghosts = analyze_ghosts(create_focused_system(), 0.0, num_rays=5,
                                surface_pairs=[(2, 3)], focus_scan_mm=0.001,
                                focus_points=11)
        assert ghosts
        assert ghosts[0].focus_clipped is True

    def test_a_generous_focus_scan_does_not_clip(self):
        ghosts = analyze_ghosts(create_focused_system(), 0.0, num_rays=5,
                                surface_pairs=[(2, 3)], focus_scan_mm=200.0,
                                focus_points=81)
        assert ghosts
        assert ghosts[0].focus_clipped is False

    def test_blocked_ghosts_are_dropped_by_default(self):
        assert all(not g.blocked
                   for g in analyze_ghosts(create_focused_system(), 1.0))

    def test_include_blocked_reports_the_failures(self):
        ghosts = analyze_ghosts(create_focused_system(), 1.0,
                                include_blocked=True)
        blocked = [g for g in ghosts if g.blocked]
        assert blocked, "the field edge should block some ghost orders"
        for g in blocked:
            assert g.num_rays == 0
            assert g.num_rays_attempted > 0
            assert g.blocked_at, "a block must name the surface it failed at"
            assert g.transmission == pytest.approx(1.0)   # nothing got through

    def test_include_blocked_only_adds_results(self):
        system = create_focused_system()
        visible = analyze_ghosts(system, 1.0)
        everything = analyze_ghosts(system, 1.0, include_blocked=True)
        assert len(visible) < len(everything)
        assert {g.first_surface for g in visible}.issubset(
            {g.first_surface for g in everything})

    def test_blocked_at_names_a_real_surface(self):
        chain = build_surface_chain(create_focused_system())
        labels = {s.label for s in chain}
        for g in analyze_ghosts(create_focused_system(), 1.0,
                                include_blocked=True):
            if g.blocked:
                assert g.blocked_at in labels

    def test_as_dict_uses_millimetres(self):
        g = analyze_ghosts(create_focused_system(), 0.0)[0]
        d = g.as_dict()
        assert d["order"] == 2
        assert d["first_surface"] == g.first_surface
        assert d["second_surface"] == g.second_surface
        assert d["ghost_image_height_mm"] == pytest.approx(
            g.ghost_image_height * 1e3)
        assert d["primary_image_height_mm"] == pytest.approx(
            g.primary_image_height * 1e3)
        assert d["displacement_mm"] == pytest.approx(g.displacement * 1e3)
        assert d["ghost_focus_z_mm"] == pytest.approx(g.ghost_focus_z * 1e3)
        assert d["ghost_focus_offset_mm"] == pytest.approx(
            g.ghost_focus_offset * 1e3)
        assert d["ghost_spot_rms_mm"] == pytest.approx(g.ghost_spot_rms * 1e3)
        assert d["relative_irradiance"] == pytest.approx(
            g.relative_irradiance)
        assert d["num_rays"] == g.num_rays


class TestGhostAnalysisSummary:
    """The field-wide ghost summary used by reports and the API."""

    def test_summary_keys(self):
        out = ghost_analysis(create_focused_system())
        for key in ("num_surfaces", "surfaces", "axis_ghosts", "edge_ghosts",
                    "num_axis_ghosts", "num_edge_ghosts", "worst_field",
                    "worst_ghost", "worst_relative_irradiance"):
            assert key in out

    def test_surface_table(self):
        out = ghost_analysis(create_focused_system())
        assert out["num_surfaces"] == 4
        assert len(out["surfaces"]) == 4
        first = out["surfaces"][0]
        assert first["label"] == "L1.front"
        assert first["z_mm"] == pytest.approx(100.0)
        assert first["reflective"] is False
        assert first["n_left"] == pytest.approx(1.0)
        assert first["n_right"] > 1.0

    def test_surface_table_is_ordered_along_the_axis(self):
        out = ghost_analysis(create_focused_system())
        zs = [s["z_mm"] for s in out["surfaces"]]
        assert zs == sorted(zs)
        assert [s["index"] for s in out["surfaces"]] == [0, 1, 2, 3]

    def test_both_fields_are_analysed(self):
        out = ghost_analysis(create_focused_system())
        assert out["num_axis_ghosts"] == len(out["axis_ghosts"]) == 6
        assert out["num_edge_ghosts"] == len(out["edge_ghosts"]) == 4

    def test_ghost_entries_are_dicts(self):
        out = ghost_analysis(create_focused_system())
        for entry in out["axis_ghosts"]:
            assert isinstance(entry, dict)
            assert entry["order"] == 2
            assert "relative_irradiance" in entry

    def test_worst_ghost_is_the_brightest_of_either_field(self):
        out = ghost_analysis(create_focused_system())
        assert out["worst_field"] in ("axis", "edge")
        assert out["worst_ghost"] is not None
        assert out["worst_relative_irradiance"] == pytest.approx(
            out["worst_ghost"]["relative_irradiance"])
        expected = max(out["axis_ghosts"][0]["relative_irradiance"],
                       out["edge_ghosts"][0]["relative_irradiance"])
        assert out["worst_relative_irradiance"] == pytest.approx(expected)

    def test_worst_ghost_is_positive(self):
        out = ghost_analysis(create_focused_system())
        assert out["worst_relative_irradiance"] > 0.0

    def test_kwargs_reach_analyze_ghosts(self):
        out = ghost_analysis(create_focused_system(),
                             coating_reflectance=0.005, num_rays=3)
        assert out["num_axis_ghosts"] == 6
        assert out["worst_relative_irradiance"] < 1.0e-4

    def test_threshold_can_empty_the_summary(self):
        out = ghost_analysis(create_focused_system(),
                             min_relative_irradiance=1.0)
        assert out["num_axis_ghosts"] == 0
        assert out["num_edge_ghosts"] == 0
        assert out["worst_ghost"] is None
        assert out["worst_field"] is None
        assert out["worst_relative_irradiance"] == 0.0

    def test_a_system_with_no_surfaces_summarises_cleanly(self):
        system = OpticalSystem(
            components=[],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.0, orientation=0.0),
            image_plane=ImagePlane(position=0.100),
            analysis_settings=AnalysisSettings(num_rays=5, wavelength=550e-9),
        )
        out = ghost_analysis(system)
        assert out["num_surfaces"] == 0
        assert out["worst_ghost"] is None
