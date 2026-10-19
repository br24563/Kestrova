"""
The compiled ray trace (optics._fasttrace) must reproduce the NumPy trace.

Each system is traced both ways with the same rays, some aimed outside the
pupil so that clipping, misses and total internal reflection are exercised;
the valid masks must be identical and every quantity equal to round-off.
"""

import math

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

pytestmark = pytest.mark.skipif(not ft.AVAILABLE, reason="Numba is not installed")


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


SYSTEMS = {
    "thick": lambda: get_preset_by_id("thick_lens")["system"],
    "parabola": lambda: get_preset_by_id("parabolic_mirror")["system"],
    "six_element": six_element,
    "cassegrain": cassegrain,
    "tilted": tilted,
}


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
    ideal = get_preset_by_id("single_lens")["system"]
    assert not ft.supports(rt.build_sequence(ideal))
    asph = OpticalSystem(
        components=[AsphericSurface(id="A", position=0.1, radius=0.05, conic=-0.5,
                                    aspheric_coeffs=[1e-3], aperture_diameter=0.02,
                                    material="N-BK7"),
                    ThinLens(id="L", position=0.12, focal_length=0.1, aperture_diameter=0.02)],
        wavelengths=[587e-9], object=Object(position=0, height=0.001),
        image_plane=ImagePlane(position=0.3), analysis_settings=AnalysisSettings(wavelength=587e-9))
    assert not ft.supports(rt.build_sequence(asph))


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
