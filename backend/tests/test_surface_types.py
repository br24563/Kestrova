"""
Surface types and clear apertures of the lens model, validated against
closed-form results that do not come from the engine:

- Forbes Q polynomials against Forbes' recurrence (Opt. Express 18, 19700
  (2010), eqs. A.14-A.16) and a Qcon term against the equal power series;
- a toroid with equal radii against a sphere; a cylinder's two sections;
- Zernike terms (Noll) against their XY polynomial expansions, and a zero
  departure against the bare conic;
- XY polynomial terms against an even asphere and a tilted plane against
  Snell's law at a wedge;
- a diffractive surface against the grating equation, its paraxial power
  added to the base surface's, and its Abbe number lambda_d/(lambda_F -
  lambda_C) = -3.45;
- obscured, rectangular and elliptical apertures against their areas, and
  the MTF of an obscured perfect lens against O'Neill's annular-pupil MTF
  (J. Opt. Soc. Am. 46, 285 (1956)).
"""

import math

import numpy as np
import pytest

from optics import mtf_analysis as ma
from optics import raytrace as rt
from optics.lens_data import (
    LensData,
    LensSurface,
    from_system,
    get_parameter,
    resolve,
    set_parameter,
    surface_shape,
    to_system,
)
from optics.lens_optimize import edge_thickness
from optics.materials import F_LINE, C_LINE, D_LINE, refractive_index
from optics.models import AnalysisSettings

WL = D_LINE


def singlet(first: LensSurface, back_radius: float = -0.1) -> LensData:
    """A singlet whose front surface (the stop) is ``first``."""
    front = first.model_copy(
        update=dict(thickness=0.005, material="N-BK7", semi_diameter=0.01, is_stop=True)
    )
    return LensData(
        surfaces=[
            front,
            LensSurface(radius=back_radius, thickness=0.09, semi_diameter=0.012),
        ],
        object_distance=None,
        field_angle=math.radians(3),
        wavelengths=[WL],
        analysis_settings=AnalysisSettings(wavelength=WL),
    )


def trace(lens: LensData, wavelength: float = WL):
    """Image points and directions of a fixed set of skew rays."""
    seq = rt.build_sequence(to_system(lens), wavelength)
    rng = np.random.default_rng(3)
    n = 60
    r = 0.009 * np.sqrt(rng.uniform(0, 1, n))
    a = rng.uniform(0, 2 * np.pi, n)
    tilt_x, tilt_y = rng.uniform(-0.05, 0.05, n), rng.uniform(-0.05, 0.05, n)
    d0 = np.stack([tilt_x, tilt_y, np.ones(n)], axis=1)
    d0 /= np.linalg.norm(d0, axis=1, keepdims=True)
    z0 = -0.01
    p0 = np.stack(
        [
            r * np.cos(a) + z0 * d0[:, 0] / d0[:, 2],
            r * np.sin(a) + z0 * d0[:, 1] / d0[:, 2],
            np.full(n, z0),
        ],
        axis=1,
    )
    b = rt.trace_bundle(seq, p0, d0, clip=False)
    assert b.valid.all()
    return b.image, b.directions


def assert_same_rays(a: LensData, b: LensData, atol=1e-11):
    pa, da = trace(a)
    pb, db = trace(b)
    np.testing.assert_allclose(pa, pb, rtol=0, atol=atol)
    np.testing.assert_allclose(da, db, rtol=0, atol=atol)


# =============================================================================
# Forbes Q aspheres
# =============================================================================


def forbes_qbfs(m_max: int, x: float) -> list:
    """Q_0 .. Q_m_max at x = u^2 from Forbes' 2010 recurrence (eqs. A.14-A.16)."""
    f = {0: 2.0, 1: math.sqrt(19) / 2}
    g = {0: -0.5}
    h = {}
    for n in range(2, m_max + 1):
        h[n - 2] = -n * (n - 1) / (2 * f[n - 2])
        if n - 1 not in g:
            g[n - 1] = -(1 + g[n - 2] * h[n - 2]) / f[n - 1]
        f[n] = math.sqrt(n * (n + 1) + 3 - g[n - 1] ** 2 - h[n - 2] ** 2)
    P = [2.0, 6 - 8 * x]
    Q = [1.0, (13 - 16 * x) / math.sqrt(19)]
    for n in range(2, m_max + 1):
        P.append((2 - 4 * x) * P[-1] - P[-2])
        Q.append((P[n] - g[n - 1] * Q[n - 1] - h[n - 2] * Q[n - 2]) / f[n])
    return Q[: m_max + 1]


class TestQAsphere:
    @pytest.mark.parametrize("x", [0.0, 0.13, 0.5, 0.87, 1.0])
    def test_qbfs_basis_matches_forbes_recurrence(self, x):
        basis = rt.qbfs_basis(6)
        ours = [np.polynomial.polynomial.polyval(x, b) for b in basis]
        np.testing.assert_allclose(ours, forbes_qbfs(6, x), atol=1e-12)

    def test_qcon_q0_equals_an_r4_term(self):
        # Qcon: sag = conic + u^4 sum a_m P_m^(0,4)(2u^2 - 1), P_0 = 1, so
        # q_0 alone is the even asphere term A4 = q_0 / R^4.
        rn, q0 = 0.012, 2e-5
        q = singlet(
            LensSurface(
                surface_type="q_asphere",
                q_type="qcon",
                radius=0.06,
                conic=-0.4,
                norm_radius=rn,
                q_coefficients=[q0],
            )
        )
        e = singlet(
            LensSurface(
                surface_type="even_asphere",
                radius=0.06,
                conic=-0.4,
                aspheric_coefficients=[q0 / rn**4],
            )
        )
        # Q surfaces are traced with finite-difference normals
        assert_same_rays(q, e, atol=1e-9)

    def test_qbfs_sag_and_paraxial_curvature(self):
        # Qbfs: sag = sphere + u^2 (1 - u^2) / sqrt(1 - c^2 r^2) sum a_m Q_m(u^2)
        rn, c = 0.012, 1 / 0.06
        a = [3e-5, -1e-5]
        s = LensSurface(
            surface_type="q_asphere", radius=0.06, norm_radius=rn, q_coefficients=a
        )
        r = 0.007
        u2 = (r / rn) ** 2
        Q = forbes_qbfs(1, u2)
        expected = c * r * r / (1 + math.sqrt(1 - c * c * r * r)) + u2 * (
            1 - u2
        ) / math.sqrt(1 - c * c * r * r) * (a[0] * Q[0] + a[1] * Q[1])
        assert float(surface_shape(s).sag(np.array(0.0), np.array(r))) == pytest.approx(
            expected, rel=1e-12
        )
        # its r^2 term changes the paraxial curvature by 2 sum a_m Q_m(0) / R^2
        Q0 = forbes_qbfs(1, 0.0)
        c_par = c + 2 * (a[0] * Q0[0] + a[1] * Q0[1]) / rn**2
        fo = rt.first_order(to_system(singlet(s)))
        sphere = rt.first_order(to_system(singlet(LensSurface(radius=1 / c_par))))
        assert fo.efl == pytest.approx(sphere.efl, rel=1e-6)


# =============================================================================
# Toroids and cylinders
# =============================================================================


class TestToroid:
    def test_equal_radii_is_a_sphere(self):
        t = singlet(LensSurface(surface_type="toroid", radius=0.06, radius_x=0.06))
        s = singlet(LensSurface(radius=0.06))
        assert_same_rays(t, s, atol=1e-10)

    def test_sections(self):
        s = LensSurface(surface_type="toroid", radius=0.05, radius_x=0.2, conic=-0.5)
        shape = surface_shape(s)
        c = 1 / 0.05
        for v in (0.003, 0.008):
            # y-z section: the conic; x-z section: a circle of radius 0.2
            conic = c * v * v / (1 + math.sqrt(1 - 0.5 * c * c * v * v))
            assert float(shape.sag(np.array(0.0), np.array(v))) == pytest.approx(conic)
            circle = 0.2 - math.sqrt(0.2**2 - v * v)
            assert float(shape.sag(np.array(v), np.array(0.0))) == pytest.approx(circle)

    def test_cylinder_focuses_in_one_plane_only(self):
        cyl = singlet(
            LensSurface(surface_type="toroid", radius=0.05, radius_x=0.0),
            back_radius=0.0,
        )
        # paraxial data follow the y section: the same as a plano-convex sphere
        fo = rt.first_order(to_system(cyl))
        sph = rt.first_order(
            to_system(singlet(LensSurface(radius=0.05), back_radius=0.0))
        )
        assert fo.efl == pytest.approx(sph.efl, rel=1e-12)
        # a ray in the x-z plane meets two flat sections and is not deviated
        seq = rt.build_sequence(to_system(cyl), WL)
        b = rt.trace_bundle(
            seq,
            np.array([[0.006, 0.0, -0.01]]),
            np.array([[0.0, 0.0, 1.0]]),
            clip=False,
        )
        np.testing.assert_allclose(b.directions[0], [0.0, 0.0, 1.0], atol=1e-14)
        b = rt.trace_bundle(
            seq,
            np.array([[0.0, 0.006, -0.01]]),
            np.array([[0.0, 0.0, 1.0]]),
            clip=False,
        )
        assert b.directions[0, 1] < -0.05


# =============================================================================
# Zernike and XY polynomial freeforms
# =============================================================================


class TestZernike:
    def test_zero_departure_is_the_conic(self):
        z = singlet(
            LensSurface(
                surface_type="zernike", radius=0.06, conic=-1.2, norm_radius=0.01
            )
        )
        e = singlet(LensSurface(radius=0.06, conic=-1.2))
        assert_same_rays(z, e)

    def test_defocus_term_curvature(self):
        # Noll Z4 = sqrt(3) (2 rho^2 - 1): vertex curvature 4 sqrt(3) a / R^2
        a, rn = 2e-5, 0.01
        s = LensSurface(
            surface_type="zernike", norm_radius=rn, zernike_coefficients=[0, 0, 0, a]
        )
        assert surface_shape(s).vertex_curvature() == pytest.approx(
            4 * math.sqrt(3) * a / rn**2, rel=1e-6
        )

    def test_matches_its_xy_polynomial_expansion(self):
        # sqrt(5) a (6 rho^4 - 6 rho^2) [Z11 with Z1 cancelling its piston]
        # plus b sqrt(8) (3 rho^3 - 2 rho) cos(theta) [Z8, x coma], written
        # out in x, y over the same normalisation radius.
        a, b, rn = 1.5e-5, -8e-6, 0.01
        zcoef = [0.0] * 11
        zcoef[0], zcoef[10], zcoef[7] = -math.sqrt(5) * a, a, b
        z = singlet(
            LensSurface(
                surface_type="zernike",
                radius=0.08,
                norm_radius=rn,
                zernike_coefficients=zcoef,
            )
        )
        k5, k8 = 6 * math.sqrt(5) * a, math.sqrt(8) * b
        xy = {
            "x4y0": k5,
            "x2y2": 2 * k5,
            "x0y4": k5,
            "x2y0": -k5,
            "x0y2": -k5,
            "x3y0": 3 * k8,
            "x1y2": 3 * k8,
            "x1y0": -2 * k8,
        }
        p = singlet(
            LensSurface(
                surface_type="xy_polynomial",
                radius=0.08,
                norm_radius=rn,
                xy_coefficients=xy,
            )
        )
        assert_same_rays(z, p, atol=1e-9)


class TestXYPolynomial:
    def test_symmetric_terms_equal_an_even_asphere(self):
        A, rn = 3e2, 0.01
        p = singlet(
            LensSurface(
                surface_type="xy_polynomial",
                radius=0.06,
                conic=-0.3,
                norm_radius=rn,
                xy_coefficients={
                    "x4y0": A * rn**4,
                    "x2y2": 2 * A * rn**4,
                    "x0y4": A * rn**4,
                },
            )
        )
        e = singlet(
            LensSurface(
                surface_type="even_asphere",
                radius=0.06,
                conic=-0.3,
                aspheric_coefficients=[A],
            )
        )
        assert_same_rays(p, e)

    def test_linear_term_is_a_wedge(self):
        # sag = s y: a plane tilted by atan(s); Snell's law at the tilted face
        # and the flat back face gives the exit direction.
        s_, rn = 0.05, 0.01
        lens = singlet(
            LensSurface(
                surface_type="xy_polynomial",
                norm_radius=rn,
                xy_coefficients={"x0y1": s_ * rn},
            ),
            back_radius=0.0,
        )
        seq = rt.build_sequence(to_system(lens), WL)
        b = rt.trace_bundle(
            seq, np.array([[0.0, 0.0, -0.01]]), np.array([[0.0, 0.0, 1.0]]), clip=False
        )
        n = refractive_index("N-BK7", WL)
        nrm = np.array([0.0, -s_, 1.0]) / math.hypot(1.0, s_)
        d = np.array([0.0, 0.0, 1.0])
        cos_i = d @ nrm
        mu = 1 / n
        d1 = mu * d + (math.sqrt(1 - mu * mu * (1 - cos_i**2)) - mu * cos_i) * nrm
        my = n * d1[1]  # tangential component is conserved at the flat face
        np.testing.assert_allclose(
            b.directions[0], [0.0, my, math.sqrt(1 - my * my)], atol=1e-14
        )


# =============================================================================
# Diffractive surfaces
# =============================================================================


def doe_lens(c1: float, radius: float = 0.0, material=None, order: int = 1) -> LensData:
    return LensData(
        surfaces=[
            LensSurface(
                surface_type="diffractive",
                radius=radius,
                material=material,
                phase_coefficients=[c1],
                diffraction_order=order,
                semi_diameter=0.01,
                is_stop=True,
                thickness=0.1,
            )
        ],
        object_distance=None,
        wavelengths=[F_LINE, D_LINE, C_LINE],
        analysis_settings=AnalysisSettings(wavelength=WL),
    )


class TestDiffractive:
    def test_grating_equation_on_a_plane(self):
        # phase c1 r^2: a ray at height h leaves at sin(theta) = (m lambda/2pi) 2 c1 h
        c1, m = -2.0e5, 1
        seq = rt.build_sequence(to_system(doe_lens(c1, order=m)), WL)
        h = np.array([0.002, 0.006, 0.0095])
        p0 = np.stack([np.zeros(3), h, np.full(3, -0.01)], axis=1)
        b = rt.trace_bundle(seq, p0, np.tile([0.0, 0.0, 1.0], (3, 1)), clip=False)
        np.testing.assert_allclose(
            b.directions[:, 1], m * WL / (2 * math.pi) * 2 * c1 * h, rtol=1e-12
        )

    def test_paraxial_focal_length_and_abbe_number(self):
        c1 = -2.0e5
        system = to_system(doe_lens(c1))
        fo = rt.first_order(system, D_LINE)
        assert fo.efl == pytest.approx(-math.pi / (c1 * D_LINE), rel=1e-9)
        power = {
            wl: 1 / rt.first_order(system, wl).efl for wl in (F_LINE, D_LINE, C_LINE)
        }
        V = power[D_LINE] / (power[F_LINE] - power[C_LINE])
        assert V == pytest.approx(D_LINE / (F_LINE - C_LINE), rel=1e-9)
        assert V == pytest.approx(-3.452, abs=2e-3)

    def test_power_adds_to_the_base_surface(self):
        # one surface into glass: n'/s' = c (n' - 1) - c1 m lambda / pi
        c1, R = -1.0e5, 0.05
        fo = rt.first_order(to_system(doe_lens(c1, radius=R, material="N-BK7")), D_LINE)
        n = refractive_index("N-BK7", D_LINE)
        phi = (n - 1) / R - c1 * D_LINE / math.pi
        assert fo.bfl == pytest.approx(n / phi, rel=1e-9)

    def test_zero_phase_on_a_sphere_is_plain_refraction(self):
        d = singlet(LensSurface(surface_type="diffractive", radius=0.06))
        s = singlet(LensSurface(radius=0.06))
        assert_same_rays(d, s, atol=1e-13)


# =============================================================================
# Clear apertures
# =============================================================================


def baffle_lens(**aperture) -> LensData:
    return LensData(
        surfaces=[
            LensSurface(label="STO", is_stop=True, semi_diameter=0.01, thickness=0.001),
            LensSurface(
                label="Baffle", thickness=0.001, semi_diameter=0.0101, **aperture
            ),
            LensSurface(
                surface_type="paraxial",
                focal_length=0.1,
                thickness=0.1,
                semi_diameter=0.0102,
            ),
        ],
        object_distance=None,
        wavelengths=[550e-9],
        analysis_settings=AnalysisSettings(wavelength=550e-9),
    )


def pass_fraction(lens: LensData) -> float:
    seq = rt.build_sequence(to_system(lens), 550e-9)
    x = np.linspace(-0.01, 0.01, 801)
    X, Y = np.meshgrid(x, x)
    inside = X**2 + Y**2 <= 0.01**2 * (1 - 1e-9)
    p0 = np.stack([X[inside], Y[inside], np.full(inside.sum(), -0.01)], axis=1)
    b = rt.trace_bundle(seq, p0, np.tile([0.0, 0.0, 1.0], (len(p0), 1)))
    return b.valid.mean()


def oneill_mtf(v: float, e: float) -> float:
    """MTF of an annular pupil with obscuration ratio e at frequency v (1 = cutoff)."""
    A = 2 / math.pi * (math.acos(v) - v * math.sqrt(1 - v * v)) if v < 1 else 0.0
    B = (
        2 * e * e / math.pi * (math.acos(v / e) - v / e * math.sqrt(1 - (v / e) ** 2))
        if v <= e
        else 0.0
    )
    if v <= (1 - e) / 2:
        C = -2 * e * e
    elif v < (1 + e) / 2:
        phi = math.acos((1 + e * e - 4 * v * v) / (2 * e))
        C = (
            2 * e / math.pi * math.sin(phi)
            + (1 + e * e) / math.pi * phi
            - 2
            * (1 - e * e)
            / math.pi
            * math.atan((1 + e) / (1 - e) * math.tan(phi / 2))
            - 2 * e * e
        )
    else:
        C = 0.0
    return (A + B + C) / (1 - e * e)


class TestApertures:
    def test_oneill_formula_against_the_pupil_overlap(self):
        # guards the transcription of the formula used below
        e = 0.4
        x = np.linspace(-1, 1, 1201)
        X, Y = np.meshgrid(x, x)
        P = (X**2 + Y**2 <= 1) & (X**2 + Y**2 >= e * e)
        for v in (0.1, 0.25, 0.5, 0.75, 0.9):
            Xs = X - 2 * v
            Q = (Xs**2 + Y**2 <= 1) & (Xs**2 + Y**2 >= e * e)
            assert (P & Q).sum() / P.sum() == pytest.approx(oneill_mtf(v, e), abs=3e-3)

    @pytest.mark.parametrize(
        "aperture, area",
        [
            (dict(obscuration_semi=0.004), 1 - 0.4**2),
            (
                dict(
                    aperture_shape="rectangular",
                    aperture_half_x=0.004,
                    aperture_half_y=0.006,
                ),
                4 * 0.004 * 0.006 / (math.pi * 0.01**2),
            ),
            (
                dict(
                    aperture_shape="elliptical",
                    aperture_half_x=0.009,
                    aperture_half_y=0.005,
                ),
                0.009 * 0.005 / 0.01**2,
            ),
        ],
    )
    def test_rays_passed_match_the_aperture_area(self, aperture, area):
        assert pass_fraction(baffle_lens(**aperture)) == pytest.approx(area, rel=6e-3)

    @pytest.mark.parametrize("method", ["hopkins", "fft"])
    def test_obscured_perfect_lens_mtf_is_oneills(self, method):
        e = 0.4
        lens = LensData(
            surfaces=[
                LensSurface(
                    surface_type="paraxial",
                    focal_length=0.1,
                    thickness=0.1,
                    semi_diameter=0.01,
                    obscuration_semi=0.01 * e,
                    is_stop=True,
                )
            ],
            object_distance=None,
            wavelengths=[550e-9],
            analysis_settings=AnalysisSettings(wavelength=550e-9),
        )
        system = to_system(lens)
        v = np.linspace(0.0, 0.95, 12)
        # the cutoff is 2 NA / lambda with NA the sine of the marginal ray angle
        cutoff = 2 * math.sin(math.atan(0.01 / 0.1)) / 550e-9
        if method == "hopkins":
            # direct integration splits its quadrature at the hole's edges
            r = ma.hopkins_otf(system, v * cutoff, 550e-9)
            tol = 1e-3
        else:
            r = ma._fft_otf(system, v * cutoff, 550e-9, 0.0, 0.0, 0.0, None, 256)
            tol = 1e-2
        expected = [oneill_mtf(x, e) for x in v]
        np.testing.assert_allclose(np.abs(r["tangential"]), expected, atol=tol)
        np.testing.assert_allclose(np.abs(r["sagittal"]), expected, atol=tol)

    @pytest.mark.parametrize("method", ["hopkins", "fft"])
    def test_square_aperture_mtf(self, method):
        # a square baffle of half-width a (in pupil radii) in front of a
        # perfect lens: the pupil overlap along a side falls as 1 - v / a
        a = 0.6
        lens = LensData(
            surfaces=[
                LensSurface(
                    label="Baffle",
                    thickness=0.001,
                    semi_diameter=0.0101,
                    aperture_shape="rectangular",
                    aperture_half_x=0.01 * a,
                    aperture_half_y=0.01 * a,
                ),
                LensSurface(
                    surface_type="paraxial",
                    focal_length=0.1,
                    thickness=0.1,
                    semi_diameter=0.01,
                    is_stop=True,
                ),
            ],
            object_distance=None,
            wavelengths=[550e-9],
            analysis_settings=AnalysisSettings(wavelength=550e-9),
        )
        system = to_system(lens)
        v = np.linspace(0.0, 0.55, 8)
        cutoff = 2 * math.sin(math.atan(0.01 / 0.1)) / 550e-9
        if method == "hopkins":
            r = ma.hopkins_otf(system, v * cutoff, 550e-9)
            tol = 1e-3
        else:
            r = ma._fft_otf(system, v * cutoff, 550e-9, 0.0, 0.0, 0.0, None, 256)
            tol = 1e-2
        np.testing.assert_allclose(np.abs(r["tangential"]), 1 - v / a, atol=tol)
        np.testing.assert_allclose(np.abs(r["sagittal"]), 1 - v / a, atol=tol)

    def test_validation(self):
        with pytest.raises(ValueError, match="half"):
            LensSurface(aperture_shape="rectangular", aperture_half_x=0.01)
        with pytest.raises(ValueError, match="circular"):
            LensSurface(
                is_stop=True,
                aperture_shape="elliptical",
                aperture_half_x=0.01,
                aperture_half_y=0.01,
            )


# =============================================================================
# The lens model: parameters, conversion, constraints
# =============================================================================


class TestLensModel:
    def test_norm_radius_and_term_names_are_checked(self):
        for kind in ("q_asphere", "zernike", "xy_polynomial"):
            with pytest.raises(ValueError, match="norm_radius"):
                LensSurface(surface_type=kind)
        with pytest.raises(ValueError, match="XY polynomial term"):
            LensSurface(
                surface_type="xy_polynomial",
                norm_radius=0.01,
                xy_coefficients={"x11y0": 1.0},
            )

    @pytest.mark.parametrize(
        "surface, name, value",
        [
            (LensSurface(surface_type="q_asphere", norm_radius=0.01), "q_3", 1e-6),
            (LensSurface(surface_type="zernike", norm_radius=0.01), "z_9", -2e-6),
            (LensSurface(surface_type="xy_polynomial", norm_radius=0.01), "x2y1", 5e-6),
            (LensSurface(surface_type="diffractive"), "phase_4", 3e7),
            (LensSurface(surface_type="toroid", radius=0.05), "radius_x", 0.08),
        ],
    )
    def test_parameters(self, surface, name, value):
        lens = singlet(surface)
        assert get_parameter(lens.surfaces[0], name) == 0.0
        out = set_parameter(lens, 0, name, value)
        assert get_parameter(out.surfaces[0], name) == value
        varied = out.model_copy(deep=True)
        varied.surfaces[0].variables = [name]
        resolve(varied)

    @pytest.mark.parametrize(
        "surface",
        [
            LensSurface(
                surface_type="q_asphere",
                radius=0.06,
                norm_radius=0.01,
                q_type="qcon",
                q_coefficients=[1e-5, 2e-6],
            ),
            LensSurface(surface_type="toroid", radius=0.06, radius_x=0.09, conic=-0.2),
            LensSurface(
                surface_type="zernike",
                radius=0.06,
                norm_radius=0.01,
                zernike_coefficients=[0, 1e-6, 0, 2e-6],
            ),
            LensSurface(
                surface_type="xy_polynomial",
                radius=0.06,
                norm_radius=0.01,
                xy_coefficients={"x2y0": 1e-6, "x0y3": -2e-6},
            ),
            LensSurface(
                surface_type="diffractive",
                radius=0.06,
                phase_coefficients=[-1e4],
                diffraction_order=2,
            ),
        ],
        ids=lambda s: s.surface_type,
    )
    def test_component_round_trip(self, surface):
        lens = singlet(surface)
        back = from_system(to_system(lens))
        row = next(s for s in back.surfaces if s.surface_type == surface.surface_type)
        for field in (
            "radius",
            "radius_x",
            "conic",
            "norm_radius",
            "q_type",
            "q_coefficients",
            "zernike_coefficients",
            "xy_coefficients",
            "phase_coefficients",
            "diffraction_order",
        ):
            assert getattr(row, field) == getattr(surface, field), field
        assert_same_rays(lens, back)

    def test_aperture_fields_reach_the_engine(self):
        lens = baffle_lens(
            obscuration_semi=0.003,
            aperture_shape="rectangular",
            aperture_half_x=0.006,
            aperture_half_y=0.008,
        )
        seq = rt.build_sequence(to_system(lens), 550e-9)
        baffle = next(s for s in seq.surfaces if s.label.startswith("Baffle"))
        assert baffle.obscuration == pytest.approx(0.003)
        assert baffle.aperture_xy == ("rectangular", 0.006, 0.008)

    def test_edge_thickness_of_a_freeform(self):
        lens = singlet(
            LensSurface(
                surface_type="zernike",
                radius=0.06,
                norm_radius=0.01,
                zernike_coefficients=[0, 0, 0, 5e-6],
            )
        )
        lens = resolve(lens)
        h = min(lens.surfaces[0].semi_diameter, lens.surfaces[1].semi_diameter)
        s0 = float(surface_shape(lens.surfaces[0]).sag(np.array(0.0), np.array(h)))
        s1 = float(surface_shape(lens.surfaces[1]).sag(np.array(0.0), np.array(h)))
        assert edge_thickness(lens, 0) == pytest.approx(0.005 - s0 + s1)

    def test_diffractive_mirrors_are_refused(self):
        lens = mirror_lens(
            LensSurface(
                surface_type="diffractive", radius=-0.5, phase_coefficients=[1e3]
            )
        )
        with pytest.raises(ValueError, match="diffractive mirrors are not supported"):
            to_system(lens)


# =============================================================================
# Shaped mirrors
# =============================================================================


def mirror_lens(surface: LensSurface) -> LensData:
    """One concave mirror (the stop) with collimated light from -z."""
    return LensData(
        surfaces=[
            surface.model_copy(
                update=dict(
                    material="MIRROR", is_stop=True, semi_diameter=0.02, thickness=-0.25
                )
            )
        ],
        object_distance=None,
        wavelengths=[550e-9],
        analysis_settings=AnalysisSettings(wavelength=550e-9),
    )


def axis_crossings(lens: LensData, points) -> np.ndarray:
    """Where collimated rays starting at (x, y) cross the axis in the plane of
    their offset (z of the crossing)."""
    seq = rt.build_sequence(to_system(lens), 550e-9)
    p0 = np.array([[x, y, -0.01] for x, y in points])
    b = rt.trace_bundle(seq, p0, np.tile([0.0, 0.0, 1.0], (len(p0), 1)), clip=False)
    assert b.valid.all()
    hit, d = b.points[:, 1], b.directions
    out = []
    for (x, y), h, dd in zip(points, hit, d):
        k = 0 if x else 1
        out.append(h[2] - h[k] / dd[k] * dd[2])
    return np.array(out)


class TestShapedMirrors:
    def test_paraboloid_focuses_perfectly(self):
        # a paraboloid (Zernike surface on a conic -1 base, no terms) sends
        # every axial ray through its focus at R/2
        lens = mirror_lens(
            LensSurface(
                surface_type="zernike", radius=-0.5, conic=-1.0, norm_radius=0.02
            )
        )
        z = axis_crossings(lens, [(0.0, h) for h in (0.002, 0.008, 0.015, 0.0199)])
        np.testing.assert_allclose(z, -0.25, rtol=0, atol=1e-12)

    def test_toroidal_mirror_has_two_focal_lines(self):
        # paraxial foci R_y/2 and R_x/2 in the two principal sections
        lens = mirror_lens(
            LensSurface(surface_type="toroid", radius=-0.5, radius_x=-0.8)
        )
        zy, zx = axis_crossings(lens, [(0.0, 1e-4), (1e-4, 0.0)])
        assert zy == pytest.approx(-0.25, rel=1e-6)
        assert zx == pytest.approx(-0.4, rel=1e-6)

    def test_shapes_of_one_mirror_trace_alike(self):
        A, rn = 50.0, 0.02
        even = mirror_lens(
            LensSurface(
                surface_type="even_asphere",
                radius=-0.5,
                conic=-0.5,
                aspheric_coefficients=[A],
            )
        )
        xy = mirror_lens(
            LensSurface(
                surface_type="xy_polynomial",
                radius=-0.5,
                conic=-0.5,
                norm_radius=rn,
                xy_coefficients={
                    "x4y0": A * rn**4,
                    "x2y2": 2 * A * rn**4,
                    "x0y4": A * rn**4,
                },
            )
        )
        pts = [(0.0, 0.01), (0.012, 0.0), (0.005, 0.0)]
        np.testing.assert_allclose(
            axis_crossings(even, pts), axis_crossings(xy, pts), rtol=0, atol=1e-12
        )
        plain = mirror_lens(LensSurface(radius=-0.5, conic=-0.7))
        zern = mirror_lens(
            LensSurface(surface_type="zernike", radius=-0.5, conic=-0.7, norm_radius=rn)
        )
        np.testing.assert_allclose(
            axis_crossings(plain, pts), axis_crossings(zern, pts), rtol=0, atol=1e-12
        )

    def test_hubble_with_a_freeform_secondary(self):
        # the Hubble secondary written as a Zernike surface with no terms
        # gives the same telescope
        from optics.reference_lenses import HUBBLE

        lens = HUBBLE.build()
        free = lens.model_copy(deep=True)
        sec = free.surfaces[1]
        free.surfaces[1] = sec.model_copy(
            update=dict(surface_type="zernike", norm_radius=0.2)
        )
        a, b = rt.first_order(to_system(lens)), rt.first_order(to_system(free))
        assert b.efl == pytest.approx(a.efl, rel=1e-12)
        seq_a = rt.build_sequence(to_system(lens), 550e-9)
        seq_b = rt.build_sequence(to_system(free), 550e-9)
        p0 = np.array([[0.0, y, -1.0] for y in (0.5, 0.9, 1.15)])
        d0 = np.tile([0.0, 0.0, 1.0], (3, 1))
        ia = rt.trace_bundle(seq_a, p0, d0, clip=False).image
        ib = rt.trace_bundle(seq_b, p0, d0, clip=False).image
        np.testing.assert_allclose(ia, ib, rtol=0, atol=1e-9)

    @pytest.mark.parametrize(
        "surface",
        [
            LensSurface(
                surface_type="even_asphere",
                radius=-0.5,
                conic=-1.0,
                aspheric_coefficients=[20.0],
            ),
            LensSurface(
                surface_type="odd_asphere", radius=-0.5, odd_coefficients=[0.5]
            ),
            LensSurface(surface_type="toroid", radius=-0.5, radius_x=-0.7),
            LensSurface(
                surface_type="zernike",
                radius=-0.5,
                norm_radius=0.02,
                zernike_coefficients=[0, 0, 0, 1e-6, 2e-6],
            ),
            LensSurface(
                surface_type="xy_polynomial",
                radius=-0.5,
                norm_radius=0.02,
                xy_coefficients={"x2y1": 1e-6},
            ),
            LensSurface(
                surface_type="q_asphere",
                radius=-0.5,
                norm_radius=0.02,
                q_coefficients=[1e-6],
            ),
        ],
        ids=lambda s: s.surface_type,
    )
    def test_component_round_trip(self, surface):
        lens = mirror_lens(surface)
        back = from_system(to_system(lens))
        row = back.surfaces[0]
        assert row.material == "MIRROR"
        assert row.surface_type == surface.surface_type
        pts = [(0.0, 0.01), (0.015, 0.0)]
        np.testing.assert_allclose(
            axis_crossings(lens, pts), axis_crossings(back, pts), rtol=0, atol=1e-12
        )


# =============================================================================
# Lens files
# =============================================================================


class TestLensFiles:
    def test_zemax_toroid_round_trip(self):
        from optics.io.lensfile import read_zemax, write_zemax

        lens = singlet(
            LensSurface(surface_type="toroid", radius=0.05, radius_x=0.12, conic=-0.3)
        )
        text, warnings = write_zemax(lens)
        assert "TYPE TOROIDAL" in text and not warnings
        back = read_zemax(text).lens
        row = back.surfaces[0]
        assert row.surface_type == "toroid"
        assert row.radius == pytest.approx(0.05)
        assert row.radius_x == pytest.approx(0.12)
        assert row.conic == pytest.approx(-0.3)
        assert_same_rays(lens, back)

    @pytest.mark.parametrize(
        "surface",
        [
            LensSurface(
                surface_type="zernike",
                radius=0.06,
                norm_radius=0.01,
                zernike_coefficients=[0, 0, 0, 1e-6],
            ),
            LensSurface(
                surface_type="q_asphere",
                radius=0.06,
                norm_radius=0.01,
                q_coefficients=[1e-6],
            ),
            LensSurface(
                surface_type="xy_polynomial",
                radius=0.06,
                norm_radius=0.01,
                xy_coefficients={"x2y0": 1e-6},
            ),
            LensSurface(
                surface_type="diffractive", radius=0.06, phase_coefficients=[-1e3]
            ),
            LensSurface(surface_type="toroid", radius=0.06, radius_x=0.1),
        ],
        ids=lambda s: s.surface_type,
    )
    def test_unwritten_types_are_reported(self, surface):
        from optics.io.lensfile import read_codev, read_zemax, write_codev, write_zemax

        lens = singlet(surface)
        for write, read, fmt in (
            (write_codev, read_codev, "Code V"),
            (write_zemax, read_zemax, "Zemax"),
        ):
            text, warnings = write(lens)
            if fmt == "Zemax" and surface.surface_type == "toroid":
                continue
            assert any("not written" in w and fmt in w for w in warnings), (
                fmt,
                warnings,
            )
            # the base conic is kept
            assert read(text).lens.surfaces[0].radius == pytest.approx(0.06)

    def test_unwritten_apertures_are_reported(self):
        from optics.io.lensfile import write_codev, write_zemax

        lens = baffle_lens(obscuration_semi=0.003)
        lens.surfaces[2] = LensSurface(radius=-0.2, thickness=0.1, semi_diameter=0.0102)
        for write in (write_codev, write_zemax):
            _, warnings = write(lens)
            assert any("obscuration" in w for w in warnings)
