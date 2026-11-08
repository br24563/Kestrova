"""
Validation against published lenses (optics.reference_lenses).

Every expected number comes from the source cited in the reference entry,
never from this engine. Tolerances follow what each source supports:

- ray-optics' printed output (an independent program tracing the same
  prescription): to the last printed digit;
- a designer's stated focal length for the original glasses, of which the
  tabulated copy substitutes catalogue equivalents: about 1 %;
- COMSOL's ray-traced best focus, quoted to two figures: 10 um.
"""

import math

import numpy as np
import pytest

from optics import raytrace as rt
from optics.io.lensfile import read_codev, read_zemax, write_codev, write_zemax
from optics.lens_data import (
    LensData,
    LensSurface,
    from_system,
    get_parameter,
    resolve,
    set_parameter,
    to_system,
)
from optics.materials import refractive_index
from optics.reference_lenses import (
    D_LINE,
    DOUBLE_GAUSS,
    HUBBLE,
    PETZVAL,
    PHONE_LENS,
    REFERENCE_LENSES,
    SASIAN_TRIPLET,
    get_reference,
)

MM = 1e-3


def first_order(ref):
    return rt.first_order(to_system(ref.build()))


def last_surface_z(lens: LensData) -> float:
    return lens.first_surface_position + sum(s.thickness for s in lens.surfaces[:-1])


# =============================================================================
# The library itself
# =============================================================================


class TestLibrary:
    def test_ids_are_unique_and_found(self):
        ids = [r.id for r in REFERENCE_LENSES]
        assert len(ids) == len(set(ids))
        for r in REFERENCE_LENSES:
            assert get_reference(r.id) is r
        assert get_reference("no-such-lens") is None

    @pytest.mark.parametrize("ref", REFERENCE_LENSES, ids=lambda r: r.id)
    def test_every_entry_is_cited_and_resolves(self, ref):
        assert ref.citation and ref.url.startswith("https://")
        assert ref.published
        resolve(ref.build())


# =============================================================================
# Geiser triplet: ray-optics first-order data, paraxial rays and Seidel sums
# =============================================================================


class TestGeiserTriplet:
    ref = SASIAN_TRIPLET

    def test_glass_indices(self):
        for glass, nd in self.ref.published["n_d"].items():
            assert refractive_index(glass, D_LINE) == pytest.approx(nd, abs=5e-6)

    def test_first_order(self):
        p = self.ref.published
        lens = self.ref.build()
        fo = first_order(self.ref)
        assert fo.efl / MM == pytest.approx(p["efl"], abs=5e-3)
        assert fo.bfl / MM == pytest.approx(p["bfl"], abs=5e-3)
        # ray-optics measures the front focal distance towards the object as
        # negative; Kestrova reports it as a positive distance in front.
        assert -fo.ffl / MM == pytest.approx(p["ffl"], abs=0.05)
        assert fo.f_number == pytest.approx(p["f_number"], abs=5e-4)
        z1 = lens.first_surface_position
        assert (fo.entrance_pupil_z - z1) / MM == pytest.approx(
            p["entrance_pupil_from_first"], abs=5e-3
        )
        assert (fo.exit_pupil_z - last_surface_z(lens)) / MM == pytest.approx(
            p["exit_pupil_from_last"], abs=5e-3
        )
        assert fo.exit_pupil_semi_diameter / MM == pytest.approx(
            p["exit_pupil_semi"], abs=5e-4
        )
        assert abs(fo.image_height) / MM == pytest.approx(p["image_height"], abs=0.05)

    def test_paraxial_ray_heights(self):
        t = self.ref.tables
        fo = first_order(self.ref)
        np.testing.assert_allclose(
            np.array(fo.marginal.y) / MM, t["marginal_height"][:6], atol=6e-6
        )
        np.testing.assert_allclose(
            np.array(fo.chief.y) / MM, t["chief_height"][:6], atol=6e-6
        )
        assert fo.marginal.u_after[-1] == pytest.approx(
            t["marginal_slope_image"], abs=1e-6
        )
        assert fo.chief.u_before[0] == pytest.approx(t["chief_slope_object"], abs=1e-5)

    def test_seidel_surface_by_surface(self):
        t = self.ref.tables
        ss = rt.seidel_sums(to_system(self.ref.build()))
        rows = [
            [r[k] / MM for k in ("S1", "S2", "S3", "S4", "S5")] for r in ss.per_surface
        ]
        np.testing.assert_allclose(rows, t["seidel"], atol=1.5e-6)
        sums = [getattr(ss, k) / MM for k in ("S1", "S2", "S3", "S4", "S5")]
        np.testing.assert_allclose(sums, t["seidel_sum"], atol=1.5e-6)
        assert ss.unsupported == []

    def test_wavefront_coefficients(self):
        # W040 = S_I/8, W131 = S_II/2, W222 = S_III/2, W220 = (S_III+S_IV)/4,
        # W311 = S_V/2 (Welford), in waves at 587.5618 nm.
        w = self.ref.tables["wavefront_waves"]
        ss = rt.seidel_sums(to_system(self.ref.build()))
        lam = D_LINE
        ours = {
            "W040": ss.S1 / 8,
            "W131": ss.S2 / 2,
            "W222": ss.S3 / 2,
            "W220": (ss.S3 + ss.S4) / 4,
            "W311": ss.S5 / 2,
        }
        for k, v in w.items():
            assert ours[k] / lam == pytest.approx(v, abs=2e-3), k


# =============================================================================
# Cell-phone lens: exact real rays through odd/even polynomial aspheres
# =============================================================================


def _trace_rows(ref, name):
    """Trace one published ray and return its rows in the published form:
    local X, Y, Z (mm) at each surface and the image, then L, M, N after."""
    t = ref.tables[name]
    system = to_system(ref.build())
    seq = rt.build_sequence(system, D_LINE)
    d = np.array(t["direction"], dtype=float)
    d /= np.linalg.norm(d)
    p = np.array(t["start"], dtype=float) * MM
    p0 = p - d * (MM / d[2])  # start 1 mm before the stop plane
    bundle = rt.trace_bundle(seq, p0[None], d[None], clip=False)
    assert bundle.valid[0]
    pts = bundle.points[0, 1:]  # each surface, then the image plane
    origins = [s.origin[2] for s in seq.surfaces] + [pts[-1, 2]]
    rows = []
    direction = d
    for k, (pt, z0) in enumerate(zip(pts, origins)):
        if k + 1 < len(pts):
            step = pts[k + 1] - pt
            # a surface met at the same point as the next one (the stop on
            # the first lens vertex) leaves the direction as it was
            if np.linalg.norm(step) > 1e-12:
                direction = step / np.linalg.norm(step)
        else:
            direction = bundle.directions[0]
        rows.append([pt[0] / MM, pt[1] / MM, (pt[2] - z0) / MM, *direction])
    return np.array(rows)


class TestPhoneLens:
    ref = PHONE_LENS

    def test_first_order(self):
        p = self.ref.published
        lens = self.ref.build()
        fo = first_order(self.ref)
        assert fo.efl / MM == pytest.approx(p["efl"], abs=5e-4)
        assert fo.bfl / MM == pytest.approx(p["bfl"], abs=5e-5)
        assert -fo.ffl / MM == pytest.approx(p["ffl"], abs=5e-4)
        assert fo.entrance_pupil_semi_diameter / MM == pytest.approx(
            p["entrance_pupil_semi"], abs=5e-5
        )
        assert fo.exit_pupil_semi_diameter / MM == pytest.approx(
            p["exit_pupil_semi"], abs=5e-5
        )
        # ray-optics' exp_dist is -(exit pupil to image plane - paraxial
        # image distance): this lens's image plane sits 0.64 mm behind the
        # filter rather than at the paraxial focus.
        image_plane = last_surface_z(lens) + lens.surfaces[-1].thickness
        exp_dist = -((image_plane - fo.exit_pupil_z) - fo.bfl)
        assert exp_dist / MM == pytest.approx(p["exit_pupil_from_last"], abs=5e-4)

    @pytest.mark.parametrize("name", ["marginal_ray", "skew_ray", "chief_ray_field_1"])
    def test_exact_ray(self, name):
        expected = np.array(self.ref.tables[name]["rows"])
        ours = _trace_rows(self.ref, name)
        assert ours.shape == expected.shape
        # coordinates printed to 5 decimals (sags to 5 significant figures),
        # direction cosines to 6
        np.testing.assert_allclose(ours[:, :2], expected[:, :2], atol=6e-6)
        np.testing.assert_allclose(ours[:, 2], expected[:, 2], atol=6e-6, rtol=1e-4)
        np.testing.assert_allclose(ours[:, 3:], expected[:, 3:], atol=1e-6)


# =============================================================================
# Double Gauss and Petzval: designers' focal lengths, COMSOL's best focus
# =============================================================================


def _hexapolar(rings: int, radius: float) -> np.ndarray:
    pts = [(0.0, 0.0)]
    for k in range(1, rings + 1):
        for j in range(6 * k):
            a = 2 * math.pi * j / (6 * k)
            pts.append(
                (radius * k / rings * math.cos(a), radius * k / rings * math.sin(a))
            )
    return np.array(pts)


class TestDoubleGauss:
    ref = DOUBLE_GAUSS

    def test_focal_length_and_aperture(self):
        p = self.ref.published
        fo = first_order(self.ref)
        assert fo.efl / MM == pytest.approx(p["efl"], rel=5e-3)
        assert fo.f_number == pytest.approx(p["f_number"], abs=0.01)

    def test_best_focus_matches_comsol(self):
        # COMSOL traces 1027 rays (18 hexapolar rings) on axis at 550 nm and
        # finds the minimum-RMS plane 180 um in front of the nominal image.
        lens = self.ref.build()
        seq = rt.build_sequence(to_system(lens), 550e-9)
        xy = _hexapolar(18, 0.5 * lens.entrance_pupil_diameter)
        p0 = np.column_stack([xy, np.full(len(xy), -0.01)])
        d0 = np.tile([0.0, 0.0, 1.0], (len(xy), 1))
        b = rt.trace_bundle(seq, p0, d0)
        assert b.valid.all()
        P, D = b.image, b.directions
        x, y = P[:, 0] - P[:, 0].mean(), P[:, 1] - P[:, 1].mean()
        sx, sy = D[:, 0] / D[:, 2], D[:, 1] / D[:, 2]
        sx, sy = sx - sx.mean(), sy - sy.mean()
        shift = -np.sum(x * sx + y * sy) / np.sum(sx * sx + sy * sy)
        assert shift / MM == pytest.approx(
            self.ref.published["best_focus_shift"], abs=0.010
        )
        # and the paraxial focus lies between the nominal plane and best focus
        image_plane = last_surface_z(lens) + lens.surfaces[-1].thickness
        fo = rt.first_order(to_system(lens))
        assert shift < fo.image_z - image_plane < 0


class TestPetzval:
    ref = PETZVAL

    def test_focal_length_and_aperture(self):
        p = self.ref.published
        fo = first_order(self.ref)
        assert fo.efl / MM == pytest.approx(p["efl"], rel=0.01)
        assert fo.f_number == pytest.approx(p["f_number"], rel=0.02)


# =============================================================================
# Hubble Space Telescope: published focal length; an aplanatic design
# =============================================================================


class TestHubble:
    ref = HUBBLE

    def test_focal_length_and_focal_ratio(self):
        p = self.ref.published
        fo = first_order(self.ref)
        assert fo.efl / MM == pytest.approx(p["efl"], rel=1e-4)
        assert fo.f_number == pytest.approx(p["f_number"], rel=1e-4)
        assert 2 * fo.entrance_pupil_semi_diameter / MM == pytest.approx(p["epd"])

    def test_ritchey_chretien_is_aplanatic(self):
        # A Ritchey-Chretien telescope cancels third-order spherical
        # aberration and coma between its two mirrors; the published conics
        # (given to 5 and 8 figures) do so to a few percent and 0.1 %.
        ss = rt.seidel_sums(to_system(self.ref.build()))
        s1 = max(abs(r["S1"]) for r in ss.per_surface)
        s2 = max(abs(r["S2"]) for r in ss.per_surface)
        assert abs(ss.S1) < 0.05 * s1
        assert abs(ss.S2) < 1e-3 * s2


# =============================================================================
# Lens files: every reference survives Code V and Zemax files
# =============================================================================


@pytest.mark.parametrize("ref", REFERENCE_LENSES, ids=lambda r: r.id)
@pytest.mark.parametrize(
    "write, read",
    [(write_codev, read_codev), (write_zemax, read_zemax)],
    ids=["codev", "zemax"],
)
def test_reference_survives_lens_files(ref, write, read):
    lens = ref.build()
    text, _ = write(lens)
    back = read(text).lens
    a = rt.first_order(to_system(lens))
    b = rt.first_order(to_system(back))
    assert b.efl == pytest.approx(a.efl, rel=1e-9)
    assert b.bfl == pytest.approx(a.bfl, rel=1e-9, abs=1e-12)


# =============================================================================
# Odd aspheres in the lens model
# =============================================================================


def _odd_lens() -> LensData:
    return LensData(
        surfaces=[
            LensSurface(
                surface_type="odd_asphere",
                radius=0.02,
                thickness=0.004,
                material="N-BK7",
                semi_diameter=0.005,
                is_stop=True,
                conic=-0.5,
                aspheric_coefficients=[1e2],
                odd_coefficients=[-3.0, 4e3],
            ),
            LensSurface(radius=-0.05, thickness=0.03),
        ]
    )


class TestOddAsphere:
    def test_parameters(self):
        lens = _odd_lens()
        s = lens.surfaces[0]
        assert get_parameter(s, "asphere_3") == -3.0
        assert get_parameter(s, "asphere_4") == 1e2
        assert get_parameter(s, "asphere_5") == 4e3
        assert get_parameter(s, "asphere_7") == 0.0
        out = set_parameter(lens, 0, "asphere_9", 7.0)
        assert out.surfaces[0].odd_coefficients == [-3.0, 4e3, 0.0, 7.0]
        assert out.surfaces[0].aspheric_coefficients == [1e2]
        with pytest.raises(ValueError):
            get_parameter(LensSurface(surface_type="even_asphere"), "asphere_3")

    def test_traced_sag_includes_odd_terms(self):
        lens = _odd_lens()
        seq = rt.build_sequence(to_system(lens), 550e-9)
        shape = next(s for s in seq.surfaces if s.kind == "refract").shape
        r = 0.004
        c, k = 1 / 0.02, -0.5
        expected = (
            c * r**2 / (1 + math.sqrt(1 - (1 + k) * c**2 * r**2))
            - 3.0 * r**3
            + 1e2 * r**4
            + 4e3 * r**5
        )
        assert float(shape.sag(np.array(r), np.array(0.0))) == pytest.approx(expected)

    def test_component_model_round_trip(self):
        lens = _odd_lens()
        back = from_system(to_system(lens))
        s = next(s for s in back.surfaces if s.surface_type == "odd_asphere")
        assert s.odd_coefficients == pytest.approx([-3.0, 4e3])
        assert s.aspheric_coefficients == pytest.approx([1e2])

    def test_zemax_odd_asphere_round_trip(self):
        lens = _odd_lens()
        text, warnings = write_zemax(lens)
        assert "TYPE ODDASPH" in text and not warnings
        s = read_zemax(text).lens.surfaces[0]
        assert s.surface_type == "odd_asphere"
        assert s.odd_coefficients == pytest.approx([-3.0, 4e3])
        assert s.aspheric_coefficients == pytest.approx([1e2])

    def test_zemax_reader_reports_unsupported_terms(self):
        text, _ = write_zemax(_odd_lens())
        text = text.replace("TYPE ODDASPH", "TYPE ODDASPH\n  PARM 1 0.5\n  PARM 2 0.1")
        res = read_zemax(text)
        assert any("r^1 asphere term" in w for w in res.warnings)
        assert any("r^2 asphere term" in w for w in res.warnings)

    def test_codev_writer_reports_dropped_odd_terms(self):
        _, warnings = write_codev(_odd_lens())
        assert any("odd asphere terms" in w for w in warnings)


# =============================================================================
# Samples API
# =============================================================================


def test_samples_api():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    listing = client.get("/api/lens/samples")
    assert listing.status_code == 200
    assert [s["id"] for s in listing.json()] == [r.id for r in REFERENCE_LENSES]
    assert all("lens" not in s and s["citation"] for s in listing.json())

    one = client.get(f"/api/lens/samples/{PHONE_LENS.id}")
    assert one.status_code == 200
    body = one.json()
    assert body["name"] == PHONE_LENS.name
    lens = LensData.model_validate(body["lens"])
    assert lens.surfaces[1].surface_type == "odd_asphere"
    resolved = client.post("/api/lens/resolve", json={"lens": body["lens"]})
    assert resolved.status_code == 200
    assert resolved.json()["first_order"]["efl"] == pytest.approx(5.555e-3, abs=5e-7)

    assert client.get("/api/lens/samples/nope").status_code == 404
