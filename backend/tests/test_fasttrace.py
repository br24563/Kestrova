"""
The compiled ray trace (optics._fasttrace) must reproduce the NumPy trace.

Each system is traced both ways with the same rays, some aimed outside the
pupil so that clipping, misses and total internal reflection are exercised;
the valid masks must be identical and every quantity equal to round-off.
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from optics import _fasttrace as ft
from optics import lens_data as ld
from optics import raytrace as rt
from optics.advanced_surfaces import AsphericSurface, CoordinateBreak
from optics.lens_data import LensData, LensSurface
from optics.models import (
    AnalysisSettings, ImagePlane, Object, OpticalSystem, ThickLens, ThinLens,
)
from optics.presets import get_preset_by_id

needs_numba = pytest.mark.skipif(not ft.AVAILABLE, reason="Numba is not installed")


def six_element():
    far = 1e5
    comps, z = [], 0.1
    for i, (r1, r2) in enumerate([(0.06, 0.3), (0.03, 0.025), (-0.025, -0.03),
                                  (-0.3, -0.06), (0.08, -0.2), (0.1, -0.1)]):
        comps.append(ThickLens(id=f"L{i}", position=z + far, radius1=r1, radius2=r2,
                               thickness=0.006, aperture_diameter=0.02, material="N-BK7"))
        z += 0.015
    return OpticalSystem(components=comps, wavelengths=[587e-9],
                         object=Object(position=0, height=far * math.tan(math.radians(10))),
                         image_plane=ImagePlane(position=far + 0.25),
                         analysis_settings=AnalysisSettings(wavelength=587e-9))


def cassegrain():
    return ld.to_system(LensData(
        surfaces=[LensSurface(label="M1", radius=-1.0, material="MIRROR", is_stop=True,
                              semi_diameter=0.05, thickness=-0.35),
                  LensSurface(label="M2", radius=-0.4, material="MIRROR", thickness=0.6)],
        object_distance=None, field_angle=math.radians(0.3), wavelengths=[587e-9],
        analysis_settings={"wavelength": 587e-9}))


def tilted():
    t = get_preset_by_id("thick_lens")["system"]
    return t.model_copy(update={"components": [
        t.components[0],
        CoordinateBreak(id="cb", position=0.25, tilt_x=math.radians(2), decenter_y=0.001),
        ThickLens(id="L2", position=0.27, radius1=0.15, radius2=-0.2, thickness=0.006,
                  aperture_diameter=0.03, material="N-SF5")]})


def obscured():
    s = cassegrain()
    comps = [c.model_copy(update={"obscuration_diameter": 0.04}) if c.id == "M1" else c
             for c in s.components]
    return s.model_copy(update={"components": comps})


def shaped_apertures():
    s = six_element()
    shapes = {"L1": ("rectangular", 0.004, 0.006), "L4": ("elliptical", 0.008, 0.005)}
    comps = []
    for c in s.components:
        if c.id in shapes:
            kind, hx, hy = shapes[c.id]
            c = c.model_copy(update={"aperture_shape": kind, "aperture_half_x": hx,
                                     "aperture_half_y": hy})
        comps.append(c)
    return s.model_copy(update={"components": comps})


def _singlet(front: dict, back: dict | None = None, field_deg=3.0):
    """A stop, then one N-BK7 element with the given front and back surfaces."""
    return ld.to_system(LensData(
        surfaces=[LensSurface(is_stop=True, semi_diameter=0.004, thickness=0.002),
                  LensSurface(radius=0.04, thickness=0.004, material="N-BK7",
                              semi_diameter=0.006, **front),
                  LensSurface(radius=-0.06, thickness=0.05, semi_diameter=0.006,
                              **(back or {}))],
        object_distance=None, field_angle=math.radians(field_deg),
        wavelengths=[587e-9], analysis_settings={"wavelength": 587e-9}))


def even_asphere():
    return _singlet(
        {"surface_type": "even_asphere", "conic": -0.6, "asphere_4": -2.0e3,
         "asphere_6": 4.0e7, "asphere_8": -1.0e11},
        {"surface_type": "even_asphere", "asphere_4": 1.5e3, "asphere_10": 2.0e15})


def odd_asphere():
    return _singlet(
        {"surface_type": "odd_asphere", "conic": 0.3, "asphere_3": 4.0,
         "asphere_4": -1.0e3, "asphere_5": 3.0e5},
        {"surface_type": "odd_asphere", "asphere_3": -2.0, "asphere_7": 1.0e9})


def xy_polynomial():
    return _singlet(
        {"surface_type": "xy_polynomial", "conic": -0.2, "norm_radius": 0.006,
         "x1y0": 2.0e-5, "x2y0": 3.0e-5, "x0y2": -2.0e-5, "x2y1": 1.5e-5,
         "x0y3": -1.0e-5, "x4y0": 2.0e-5, "x2y2": 4.0e-5, "x0y4": 1.0e-5})


def q_bfs():
    return _singlet(
        {"surface_type": "q_asphere", "q_type": "qbfs", "norm_radius": 0.0065,
         "q_0": 4.0e-6, "q_1": -2.0e-6, "q_2": 1.0e-6, "q_3": -5.0e-7, "q_5": 2.0e-7},
        {"surface_type": "q_asphere", "q_type": "qbfs", "norm_radius": 0.0065,
         "q_0": -3.0e-6, "q_4": 4.0e-7})


def q_con():
    return _singlet(
        {"surface_type": "q_asphere", "q_type": "qcon", "conic": -0.8,
         "norm_radius": 0.0065, "q_0": 5.0e-6, "q_1": -2.0e-6, "q_2": 1.0e-6,
         "q_6": 3.0e-7})


def zernike():
    return _singlet(
        {"surface_type": "zernike", "conic": -0.3, "norm_radius": 0.0065,
         "z_4": 2.0e-6, "z_5": -1.5e-6, "z_6": 1.0e-6, "z_7": 8.0e-7, "z_8": -6.0e-7,
         "z_11": 5.0e-7, "z_17": 2.0e-7, "z_22": -2.0e-7, "z_37": 1.0e-7})


def toroid():
    return _singlet({"surface_type": "toroid", "radius_x": 0.055, "conic": -0.4},
                    {"surface_type": "toroid", "radius_x": -0.05})


def cylinder():
    return _singlet({"surface_type": "toroid", "radius_x": 0.0})


def diffractive():
    # the phase sits on a flat surface behind the element
    lens = LensData(
        surfaces=[LensSurface(is_stop=True, semi_diameter=0.004, thickness=0.002),
                  LensSurface(radius=0.04, thickness=0.004, material="N-BK7",
                              semi_diameter=0.006),
                  LensSurface(surface_type="diffractive", radius=-0.2, thickness=0.05,
                              semi_diameter=0.006, diffraction_order=1,
                              phase_2=-4.0e4, phase_4=6.0e7, phase_6=-1.0e11)],
        object_distance=None, field_angle=math.radians(3.0),
        wavelengths=[587e-9], analysis_settings={"wavelength": 587e-9})
    return ld.to_system(lens)


def aspheric_mirror():
    return ld.to_system(LensData(
        surfaces=[LensSurface(label="M1", surface_type="even_asphere", radius=-1.0,
                              conic=-1.02, asphere_4=2.0e-3, asphere_6=-1.0e-1,
                              material="MIRROR", is_stop=True, semi_diameter=0.05,
                              thickness=-0.35),
                  LensSurface(label="M2", surface_type="even_asphere", radius=-0.4,
                              conic=-2.5, asphere_4=-5.0e-2, material="MIRROR",
                              thickness=0.6)],
        object_distance=None, field_angle=math.radians(0.3), wavelengths=[587e-9],
        analysis_settings={"wavelength": 587e-9}))


def phone_lens():
    from optics.reference_lenses import get_reference

    return ld.to_system(get_reference("phone-camera-us7535658").build())


def ideal_lens():
    return get_preset_by_id("single_lens")["system"]


def ideal_lens_finite_conjugates():
    # an ideal relay behind a real singlet: its object point is finite
    lens = LensData(
        surfaces=[LensSurface(is_stop=True, semi_diameter=0.004, thickness=0.002),
                  LensSurface(radius=0.04, thickness=0.004, material="N-BK7",
                              semi_diameter=0.006),
                  LensSurface(radius=-0.06, thickness=0.03, semi_diameter=0.006),
                  LensSurface(surface_type="paraxial", focal_length=0.02,
                              semi_diameter=0.006, thickness=0.03)],
        object_distance=None, field_angle=math.radians(3.0),
        wavelengths=[587e-9], analysis_settings={"wavelength": 587e-9})
    return ld.to_system(lens)


def asphere_and_ideal_lens():
    return OpticalSystem(
        components=[AsphericSurface(id="A", position=0.1, radius=0.05, conic=-0.5,
                                    aspheric_coeffs=[1e-3], aperture_diameter=0.02,
                                    material="N-BK7"),
                    ThinLens(id="L", position=0.12, focal_length=0.1, aperture_diameter=0.02)],
        wavelengths=[587e-9], object=Object(position=0, height=0.001),
        image_plane=ImagePlane(position=0.3), analysis_settings=AnalysisSettings(wavelength=587e-9))


SYSTEMS = {
    "ideal_lens": ideal_lens,
    "ideal_lens_finite_conjugates": ideal_lens_finite_conjugates,
    "asphere_and_ideal_lens": asphere_and_ideal_lens,
    "thick": lambda: get_preset_by_id("thick_lens")["system"],
    "parabola": lambda: get_preset_by_id("parabolic_mirror")["system"],
    "six_element": six_element,
    "cassegrain": cassegrain,
    "tilted": tilted,
    "obscured": obscured,
    "shaped_apertures": shaped_apertures,
    "even_asphere": even_asphere,
    "odd_asphere": odd_asphere,
    "xy_polynomial": xy_polynomial,
    "q_bfs": q_bfs,
    "q_con": q_con,
    "zernike": zernike,
    "toroid": toroid,
    "cylinder": cylinder,
    "diffractive": diffractive,
    "aspheric_mirror": aspheric_mirror,
    "phone_lens": phone_lens,
}


@needs_numba
@pytest.mark.parametrize("name", SYSTEMS)
@pytest.mark.parametrize("clip", [True, False])
def test_kernel_matches_numpy(name, clip):
    s = SYSTEMS[name]()
    seq = rt.build_sequence(s)
    fo = rt.first_order(s, seq=seq)
    assert ft.supports(seq)
    rng = np.random.default_rng(7)
    px, py = rng.uniform(-1.3, 1.3, 4000), rng.uniform(-1.3, 1.3, 4000)
    p0, d0, _ = rt.aim_rays(seq, fo, 0.0, 0.8, px, py)
    fast = rt.RayBundle(*ft.trace(seq, p0, d0, clip))
    with np.errstate(all="ignore"):
        ref = rt._trace_bundle(seq, p0, d0, clip)
    assert np.array_equal(fast.valid, ref.valid)
    assert 0 < ref.valid.sum()
    v = ref.valid
    np.testing.assert_allclose(fast.points[v], ref.points[v], rtol=0, atol=1e-12)
    np.testing.assert_allclose(fast.directions[v], ref.directions[v], rtol=0, atol=1e-14)
    np.testing.assert_allclose(fast.opl[v], ref.opl[v], rtol=1e-14, atol=1e-15)
    np.testing.assert_allclose(fast.surface_opl[v], ref.surface_opl[v], rtol=1e-14, atol=1e-15)
    assert fast.n_image == ref.n_image


def test_unsupported_surfaces_use_numpy():
    # a sag given as a function is the one shape the kernel does not know
    seq = rt.build_sequence(even_asphere())
    powered = next(sf for sf in seq.surfaces if sf.kind == "refract")
    powered.shape = rt.RadialNumeric(lambda r: 10.0 * r * r, 20.0)
    assert not ft.supports(seq)
    x = np.linspace(-0.003, 0.003, 9)
    p0 = np.stack([x, 0 * x, np.full_like(x, -0.01)], axis=1)
    d0 = np.tile([0.0, 0.0, 1.0], (len(x), 1))
    assert rt.trace_bundle(seq, p0, d0).valid.all()


@needs_numba
@pytest.mark.parametrize("name", ["even_asphere", "odd_asphere", "xy_polynomial",
                                  "q_bfs", "q_con", "zernike", "toroid", "cylinder",
                                  "diffractive", "aspheric_mirror", "phone_lens"])
def test_aspheres_and_polynomials_use_the_kernel(name):
    assert ft.supports(rt.build_sequence(SYSTEMS[name]()))


# The shapes' analytic sags and slopes, against independent evaluations.


def test_zernike_monomials_match_the_polynomials():
    from optics.zernike import zernike_standard

    rng = np.random.default_rng(3)
    coeffs = rng.normal(size=37)
    u, v = rng.uniform(-0.7, 0.7, 500), rng.uniform(-0.7, 0.7, 500)
    ref = sum(a * zernike_standard(j, np.hypot(u, v), np.arctan2(v, u))
              for j, a in enumerate(coeffs, start=1))
    got = sum(a * u**i * v**j for i, j, a in rt.zernike_xy_terms(coeffs))
    np.testing.assert_allclose(got, ref, rtol=0, atol=1e-12)


@pytest.mark.parametrize("q_type,k", [("Qbfs", 0.0), ("Qcon", -0.7)])
def test_q_asphere_sag_and_slope(q_type, k):
    # the sag against the Jacobi / Forbes-basis evaluation, the slope
    # against Richardson-extrapolated differences of it
    c, rn = 1 / 0.05, 0.01
    coeffs = [4e-6, -2e-6, 1e-6, -5e-7, 3e-7, -2e-7, 1e-7]
    shape = rt.QAsphere(c, k, coeffs, rn, q_type)
    f = rt.q_aspheric_sag_function(c, k, coeffs, rn, q_type)
    r = np.linspace(1e-4, 0.0095, 200)
    s, ds = shape._radial(r)
    np.testing.assert_allclose(s, f(r), rtol=0, atol=1e-15)
    d = lambda h: (f(r + h) - f(r - h)) / (2 * h)
    np.testing.assert_allclose(ds, (4 * d(1e-5) - d(2e-5)) / 3, rtol=0, atol=2e-9)


@pytest.mark.parametrize("cx", [1 / 0.08, -1 / 0.06, 0.0])
def test_toroid_slope(cx):
    shape = rt.YToroid(1 / 0.05, cx, -0.3)
    rng = np.random.default_rng(5)
    x, y = rng.uniform(-0.007, 0.007, 300), rng.uniform(-0.007, 0.007, 300)
    gx, gy = shape.grad(x, y)
    dx = lambda h: (shape.sag(x + h, y) - shape.sag(x - h, y)) / (2 * h)
    dy = lambda h: (shape.sag(x, y + h) - shape.sag(x, y - h)) / (2 * h)
    np.testing.assert_allclose(gx, (4 * dx(1e-5) - dx(2e-5)) / 3, rtol=0, atol=2e-9)
    np.testing.assert_allclose(gy, (4 * dy(1e-5) - dy(2e-5)) / 3, rtol=0, atol=2e-9)


@needs_numba
def test_numpy_fallback_gives_the_same_bundle(monkeypatch):
    s = six_element()
    seq = rt.build_sequence(s)
    fo = rt.first_order(s, seq=seq)
    px, py = rt.pupil_grid(15)
    fast, _, _ = rt.trace_field_rays(s, 0.0, 1.0, px, py, seq=seq, fo=fo)
    monkeypatch.setattr(ft, "AVAILABLE", False)
    slow, _, _ = rt.trace_field_rays(s, 0.0, 1.0, px, py, seq=seq, fo=fo)
    assert np.array_equal(fast.valid, slow.valid)
    np.testing.assert_allclose(fast.image[fast.valid], slow.image[slow.valid], rtol=0, atol=1e-12)


def test_aimed_rays_hit_their_stop_targets():
    s = six_element()
    seq = rt.build_sequence(s)
    fo = rt.first_order(s, seq=seq)
    px, py = rt.pupil_grid(21)
    p0, d0, conv = rt.aim_rays(seq, fo, 0.0, 0.7, px, py)
    assert conv.all()
    x, y, ok = rt._stop_coords(seq, p0, d0)
    rs = fo.stop_semi_diameter
    assert ok.all()
    # aiming tolerance: 1e-10 of the stop radius, or round-off in the
    # absolute coordinates (this system sits 1e5 m from the origin)
    z_scale = max(abs(seq.object_z), max(abs(sf.z) for sf in seq.surfaces))
    tol = max(1e-10 * rs, 64 * np.finfo(float).eps * z_scale)
    assert np.max(np.hypot(x - px * rs, y - py * rs)) < tol


@pytest.mark.parametrize("name", SYSTEMS)
@pytest.mark.parametrize("clip", [True, False])
def test_kernel_source_matches_numpy_in_python(name, clip, monkeypatch):
    # The kernel's Python source, run uncompiled (prange is range), against
    # the NumPy trace: checks the algorithm itself, with or without Numba
    # (compiled code is invisible to coverage).
    monkeypatch.setattr(ft, "numba", SimpleNamespace(prange=range))
    s = SYSTEMS[name]()
    seq = rt.build_sequence(s)
    fo = rt.first_order(s, seq=seq)
    rng = np.random.default_rng(11)
    px, py = rng.uniform(-1.3, 1.3, 150), rng.uniform(-1.3, 1.3, 150)
    p0, d0, _ = rt.aim_rays(seq, fo, 0.0, 0.8, px, py)
    monkeypatch.setattr(ft, "_sag_grad", ft._sag_grad_impl)
    monkeypatch.setattr(ft, "_ideal_opl", ft._ideal_opl_impl)
    monkeypatch.setattr(ft, "_signed_len", getattr(ft._signed_len, "py_func", ft._signed_len))
    with np.errstate(all="ignore"):
        pts, d, opl, valid, img, sopl = ft._kernel_impl(
            np.ascontiguousarray(p0, dtype=float), np.ascontiguousarray(d0, dtype=float),
            *ft._pack(seq), float(seq.wavelength),
            float(seq.surfaces[0].n_before),
            np.ascontiguousarray(seq.image_origin, dtype=float),
            np.ascontiguousarray(seq.image_rotation, dtype=float), clip,
        )
        ref = rt._trace_bundle(seq, p0, d0, clip)
    assert np.array_equal(valid, ref.valid)
    assert 0 < ref.valid.sum() < len(px) or not clip
    v = ref.valid
    np.testing.assert_allclose(pts[v], ref.points[v], rtol=0, atol=1e-12)
    np.testing.assert_allclose(d[v], ref.directions[v], rtol=0, atol=1e-14)
    np.testing.assert_allclose(opl[v], ref.opl[v], rtol=1e-14, atol=1e-15)
    np.testing.assert_allclose(sopl[v], ref.surface_opl[v], rtol=1e-14, atol=1e-15)
    np.testing.assert_allclose(img[v], ref.image[v], rtol=0, atol=1e-12)
