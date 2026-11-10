"""
CAD export (STEP / IGES), lens layout, and the engine's startup pieces.

Checks against closed forms and the file formats' own rules:

- the volume of a lens element from its outline (Pappus, V = pi |∮ r² dz|)
  against the closed form: a cylinder between the rim planes plus the two
  spherical segments, pi s (3 a² + s²) / 6 each (signed);
- STEP topology: every reference resolves, and in each closed shell every
  edge is used exactly twice, once in each sense (a closed 2-manifold);
- IGES fixed format: 80-column records, the Terminate section's counts,
  every directory entry pointing at its own parameter lines;
- B-spline profiles within PROFILE_TOLERANCE of the sag;
- when OpenCascade (OCP) is installed: the STEP solids read back valid with
  the outline volume.
"""

import math
import re
import sys

import pytest
from fastapi.testclient import TestClient

import kestrova as ks
from api.main import app
from optics.io.cad_export import (
    PROFILE_TOLERANCE,
    _evaluate,
    lens_bodies,
    profile_spline,
    write_iges,
    write_step,
)
from optics.lens_data import LensData, LensSurface
from optics.lens_layout import lens_layout
from optics.models import AnalysisSettings

client = TestClient(app)


def _lens(surfaces, field=2.0) -> LensData:
    return LensData(
        name="Test, lens",
        surfaces=surfaces,
        object_distance=None,
        field_angle=math.radians(field),
        wavelengths=[587.5618e-9],
        analysis_settings=AnalysisSettings(
            num_rays=11,
            ray_types=["chief"],
            aperture_fraction=1.0,
            wavelength=587.5618e-9,
        ),
    )


def _singlet(r1=0.05, r2=-0.08, t=0.004, semi=0.01, **front) -> LensData:
    return _lens(
        [
            LensSurface(
                radius=r1,
                thickness=t,
                material="N-BK7",
                semi_diameter=semi,
                is_stop=True,
                **front,
            ),
            LensSurface(radius=r2, thickness=0.09, semi_diameter=semi),
        ]
    )


def _outline_volume(body) -> float:
    """pi |∮ r² dz| over the outline, the optical faces finely sampled (mm³)."""
    import numpy as np

    v = 0.0
    for f in body.faces:
        if f.kind == "surface":
            r = np.linspace(f.a[1], f.b[1], 4001)
            z = np.array([f.sag(x) for x in r])
        else:
            r = np.array([f.a[1], f.b[1]])
            z = np.array([f.a[0], f.b[0]])
        v += np.trapezoid(r**2, z)
    return abs(math.pi * v)


def _segment(radius_mm: float, a: float) -> float:
    """Signed volume of the spherical segment of base radius a (mm³)."""
    s = abs(radius_mm) - math.sqrt(radius_mm**2 - a**2)
    return math.pi * s * (3 * a * a + s * s) / 6


# -- geometry ------------------------------------------------------------------


def test_element_volume_matches_the_closed_form():
    r1, r2, t, semi, margin = 50.0, -80.0, 4.0, 10.0, 1.0
    (body,), warnings = lens_bodies(
        _singlet(r1 / 1e3, r2 / 1e3, t / 1e3, semi / 1e3), edge_margin=margin / 1e3
    )
    assert warnings == []
    outer = semi + margin / 2
    s1 = r1 - math.sqrt(r1**2 - semi**2)  # front rim sag (convex: +)
    s2 = abs(r2) - math.sqrt(r2**2 - semi**2)  # back rim sag toward the front
    edge = t - s1 - s2
    expected = math.pi * outer**2 * edge + _segment(r1, semi) + _segment(r2, semi)
    assert _outline_volume(body) == pytest.approx(expected, rel=1e-6)
    kinds = [f.kind for f in body.faces]
    assert kinds == ["surface", "plane", "cylinder", "plane", "surface"]


def test_mirror_substrate_lies_behind_the_reflecting_side():
    bodies, _ = lens_bodies(ks.sample("hubble-ota").data)
    primary, secondary = bodies
    zs = [p for f in primary.faces for p in (f.a[0], f.b[0])]
    # the primary (vertex at z = 0, concave toward the light coming from -z)
    # has its rim in front of the vertex and its substrate D/8 behind it
    semi = max(f.b[1] for f in primary.faces if f.kind == "surface")
    assert min(zs) < -60 and max(zs) == pytest.approx(2 * semi / 8)
    zs2 = [p for f in secondary.faces for p in (f.a[0], f.b[0])]
    assert max(zs2) < -4000  # the secondary, 4.9 m in front, backs toward -z


def test_unexportable_surfaces_are_reported():
    tilted = _singlet(tilt_x=0.01)
    with pytest.raises(ValueError, match="decentred or tilted"):
        write_step(tilted)
    toroid = _lens(
        [
            LensSurface(
                surface_type="toroid",
                radius=0.05,
                radius_x=0.06,
                thickness=0.004,
                material="N-BK7",
                semi_diameter=0.01,
                is_stop=True,
            ),
            LensSurface(radius=-0.08, thickness=0.09, semi_diameter=0.01),
            LensSurface(
                radius=0.05, thickness=0.004, material="N-BK7", semi_diameter=0.01
            ),
            LensSurface(radius=-0.08, thickness=0.05, semi_diameter=0.01),
        ]
    )
    text, warnings = write_step(toroid)
    assert len(warnings) == 1 and "toroid" in warnings[0]
    assert text.count("MANIFOLD_SOLID_BREP") == 1


def test_profile_spline_follows_an_asphere():
    lens = ks.sample("phone-camera-us7535658")
    bodies, _ = lens_bodies(lens.data)
    checked = 0
    for body in bodies:
        for f in body.faces:
            if f.kind != "surface" or f.surface.surface_type == "standard":
                continue
            ctrl, U = profile_spline(f)
            r_max = max(f.a[1], f.b[1])
            for u in [k / 37 for k in range(38)]:
                zq, rq = _evaluate(ctrl, U, u)
                assert abs(zq - f.sag(min(max(rq, 0.0), r_max))) < 2 * PROFILE_TOLERANCE
            checked += 1
    assert checked >= 6


# -- STEP --------------------------------------------------------------------


def _step_entities(text: str) -> dict[int, str]:
    data = text.split("DATA;")[1].split("ENDSEC;")[0]
    return {int(m.group(1)): m.group(2) for m in re.finditer(r"#(\d+)=(.*?);\n", data)}


@pytest.mark.parametrize(
    "sample", ["geiser-triplet", "phone-camera-us7535658", "hubble-ota"]
)
def test_step_shells_are_closed_manifolds(sample):
    text, warnings = write_step(ks.sample(sample).data)
    assert text.startswith("ISO-10303-21;") and text.rstrip().endswith(
        "END-ISO-10303-21;"
    )
    ents = _step_entities(text)
    for body in ents.values():
        for ref in re.findall(r"#(\d+)", body):
            assert int(ref) in ents
    oriented = {k: v for k, v in ents.items() if v.startswith("ORIENTED_EDGE")}
    for k, v in ents.items():
        if not v.startswith("CLOSED_SHELL"):
            continue
        uses: dict[int, list[str]] = {}
        stack = [int(x) for x in re.findall(r"#(\d+)", v)]
        seen = set()
        while stack:
            e = stack.pop()
            if e in seen:
                continue
            seen.add(e)
            body = ents[e]
            if e in oriented:
                edge, sense = re.match(
                    r"ORIENTED_EDGE\('',\*,\*,#(\d+),(\.[TF]\.)\)", body
                ).groups()
                uses.setdefault(int(edge), []).append(sense)
            elif body.startswith(("ADVANCED_FACE", "FACE_BOUND", "EDGE_LOOP")):
                stack += [int(x) for x in re.findall(r"#(\d+)", body)]
        assert uses
        for senses in uses.values():
            assert sorted(senses) == [".F.", ".T."]
    solids = sum(v.startswith("MANIFOLD_SOLID_BREP") for v in ents.values())
    assert solids == len(lens_bodies(ks.sample(sample).data)[0])
    assert "SI_UNIT(.MILLI.,.METRE.)" in text


def test_step_reads_back_valid_in_opencascade(tmp_path):
    pytest.importorskip("OCP")
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    lens = ks.sample("phone-camera-us7535658").data
    text, _ = write_step(lens)
    path = tmp_path / "phone.step"
    path.write_text(text)
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone
    reader.TransferRoots()
    explorer = TopExp_Explorer(reader.OneShape(), TopAbs_SOLID)
    volumes = []
    while explorer.More():
        solid = explorer.Current()
        assert BRepCheck_Analyzer(solid).IsValid()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        volumes.append(props.Mass())
        explorer.Next()
    expected = [_outline_volume(b) for b in lens_bodies(lens)[0]]
    assert volumes == pytest.approx(expected, rel=1e-5)


# -- IGES --------------------------------------------------------------------


def test_iges_records_follow_the_fixed_format():
    lens = ks.sample("double-gauss-us2784643").data  # its name holds commas
    text, _ = write_iges(lens)
    lines = text.splitlines()
    assert all(len(line) == 80 for line in lines)
    counts = {c: sum(line[72] == c for line in lines) for c in "SGDPT"}
    term = lines[-1]
    assert term[72] == "T" and counts["T"] == 1
    assert (
        term[:32]
        == f"S{counts['S']:>7}G{counts['G']:>7}D{counts['D']:>7}P{counts['P']:>7}"
    )
    d = [line for line in lines if line[72] == "D"]
    p = [line for line in lines if line[72] == "P"]
    for k in range(0, len(d), 2):
        etype, pstart = int(d[k][0:8]), int(d[k][8:16])
        nlines = int(d[k + 1][24:32])
        de = k + 1
        block = p[pstart - 1 : pstart - 1 + nlines]
        assert all(int(line[64:72]) == de for line in block)
        assert block[0].startswith(f"{etype},") and block[-1][:64].rstrip().endswith(
            ";"
        )
    surfaces = sum(int(d[k][0:8]) == 120 for k in range(0, len(d), 2))
    assert surfaces == sum(len(b.faces) for b in lens_bodies(lens)[0])


# -- API ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt,head", [("step", "ISO-10303-21;"), ("igs", "Kestrova optical")]
)
def test_export_endpoint_writes_cad(fmt, head):
    r = client.post(
        "/api/lens/export",
        json={
            "lens": _singlet().model_dump(mode="json"),
            "format": fmt,
            "edge_margin": 0.002,
        },
    )
    body = r.json()
    assert r.status_code == 200 and body["content"].startswith(head)
    assert body["filename"].endswith(f".{fmt}") and body["warnings"] == []


def test_export_endpoint_refuses_unexportable_lenses():
    r = client.post(
        "/api/lens/export",
        json={"lens": _singlet(tilt_x=0.01).model_dump(mode="json"), "format": "step"},
    )
    assert r.status_code == 400


# -- layout --------------------------------------------------------------------


def test_layout_rays_reach_the_image_and_cross_the_stop():
    lens = ks.sample("geiser-triplet").data
    out = lens_layout(lens, rays=5)
    assert len(out["elements"]) == 3 and out["fields"] == 3
    for ray in out["rays"]:
        assert ray["points"][-1][2] == pytest.approx(out["image"]["z"])
        assert ray["pupil"][0] == 0.0  # meridional fan
    # the on-axis marginal rays meet the image near the axis (a good lens)
    axis = [r for r in out["rays"] if r["field"] == 0]
    assert max(abs(r["points"][-1][1]) for r in axis) < 1e-4
    outline = out["elements"][0]["outline"]
    assert outline[0][1] == 0.0 and outline[-1][1] == 0.0


def test_layout_ring_for_3d_and_endpoint():
    lens = ks.sample("geiser-triplet").data
    ring = lens_layout(lens, rays=4, pupil="ring")
    assert any(abs(r["pupil"][0]) > 0.5 for r in ring["rays"])
    r = client.post(
        "/api/lens/layout", json={"lens": lens.model_dump(mode="json"), "pupil": "ring"}
    )
    assert r.status_code == 200 and r.json()["rays"]


# -- startup -----------------------------------------------------------------


def test_optics_package_loads_names_on_first_use():
    import optics

    assert "refractive_index" in dir(optics)
    assert optics.refractive_index("N-BK7", 587.5618e-9) == pytest.approx(
        1.5168, abs=1e-4
    )
    with pytest.raises(AttributeError):
        optics.no_such_name  # noqa: B018


def test_warm_up_compiles_the_kernels():
    from optics import _fasttrace

    _fasttrace.warm_up()  # no error with or without Numba


def test_numba_cache_dir_for_frozen_builds(monkeypatch, tmp_path):
    import kestrova_server

    monkeypatch.delenv("NUMBA_CACHE_DIR", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert kestrova_server.numba_cache_dir() is None
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("KESTROVA_DATA_DIR", str(tmp_path))
    assert kestrova_server.numba_cache_dir() == str(tmp_path / "numba-cache")
    monkeypatch.setenv("NUMBA_CACHE_DIR", "x")
    assert kestrova_server.numba_cache_dir() is None
