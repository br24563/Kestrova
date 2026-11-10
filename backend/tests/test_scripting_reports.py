"""
Scripting API, script console, design report and ISO 10110 drawings.

The checks are against closed forms or the published data of the
reference lenses, not the engine against itself:

- the Geiser triplet's published focal length (50 mm, ray-optics) through
  the scripting API;
- element edge thickness from the sphere sag  z = R - sqrt(R^2 - h^2):
  t_e = t_c - z1(h) + z2(h) at the outer radius;
- the ISO 10110 sense of a radius (CX/CC seen from outside the element)
  and tolerance codes taken from the tolerance set (3/ fringes, 4/
  arc minutes, centre thickness, index and Abbe tolerances);
- the console's security rules: only loopback clients, Host headers and
  Origins.
"""

import math

import pytest
from fastapi.testclient import TestClient

import kestrova as ks
from api.main import app
from kestrova.runner import _execute, _trim_traceback, api_reference, run_script
from optics.io.element_drawing import element_drawings
from optics.lens_data import LensData, LensSurface
from optics.lens_report import line_plot_svg, lens_report_html
from optics.models import AnalysisSettings
from optics.tolerancing import Tolerance

client = TestClient(app)
MM = 1e-3


def _singlet(r1=0.05, r2=-0.08, t=0.004, semi=0.01) -> LensData:
    return LensData(
        name="Singlet",
        surfaces=[
            LensSurface(
                radius=r1,
                thickness=t,
                material="N-BK7",
                semi_diameter=semi,
                is_stop=True,
            ),
            LensSurface(radius=r2, thickness=0.09, semi_diameter=semi),
        ],
        object_distance=None,
        object_height=0.0,
        field_angle=math.radians(2),
        entrance_pupil_diameter=None,
        wavelengths=[587.5618e-9],
        first_surface_position=0.0,
        analysis_settings=AnalysisSettings(
            num_rays=11,
            ray_types=["chief"],
            aperture_fraction=1.0,
            wavelength=587.5618e-9,
        ),
    )


def _sphere_sag(r: float, h: float) -> float:
    if not r:
        return 0.0
    return math.copysign(abs(r) - math.sqrt(r * r - h * h), r)


# -- scripting API -----------------------------------------------------------


def test_sample_reproduces_the_published_focal_length():
    lens = ks.sample("geiser-triplet")
    assert lens.efl == pytest.approx(50.0 * MM, rel=1e-4)
    assert lens.f_number == pytest.approx(4.0, rel=1e-3)
    fo = lens.first_order()
    assert fo["efl"] == pytest.approx(lens.efl)
    assert lens.value("total_track") == pytest.approx(
        sum(abs(s.thickness) for s in lens.surfaces)
    )


def test_samples_and_unknown_sample():
    ids = [s["id"] for s in ks.samples()]
    assert "geiser-triplet" in ids and "hubble-ota" in ids
    with pytest.raises(ValueError, match="available"):
        ks.sample("nope")


def test_set_get_copy_and_vary_chain():
    lens = ks.sample("geiser-triplet")
    trial = lens.copy().set(1, "thickness", 0.005).vary(0, "radius")
    assert trial.get(1, "thickness") == 0.005
    assert lens.get(1, "thickness") != 0.005  # the copy is independent
    assert "0.radius" in trial.variables()
    trial.vary(0, "radius", on=False)
    assert trial.variables() == {}
    assert len(lens) == 6 and lens[0].material == "N-LAK9"
    assert "Geiser" in lens.name and "6 surfaces" in repr(lens)


def test_singlet_focal_length_matches_the_lensmaker_equation():
    from optics.materials import refractive_index

    r1, r2, t = 0.05, -0.08, 0.004
    lens = ks.Lens(_singlet(r1, r2, t))
    n = refractive_index("N-BK7", 587.5618e-9)
    power = (n - 1) * (1 / r1 - 1 / r2 + (n - 1) * t / (n * r1 * r2))
    assert lens.efl == pytest.approx(1 / power, rel=1e-9)
    lens.set_material(0, "N-SF11")
    assert lens.efl < 1 / power  # the higher index shortens it


def test_analysis_methods_return_their_results():
    lens = ks.Lens(_singlet())
    assert lens.spot_rms() > 0 and lens.wavefront_rms() > 0
    assert lens.fields()["fields"]
    assert lens.mtf(0, [10.0, 20.0])["tangential"][0] <= 1.0
    assert "seidel_sums" in lens.seidel()
    assert lens.beam(1e-3)["waist_radius"] > 0
    assert len(lens.environment([0.0, 20.0])) == 2
    assert "transmittance" in lens.polarization(0)
    assert isinstance(lens.ghosts(0), list)
    assert lens.merit()["merit"] >= 0
    assert lens.default_tolerances()
    assert lens.configuration(0).efl == pytest.approx(lens.efl)
    assert lens.resolve().system().components


def test_optimize_updates_the_lens():
    lens = ks.Lens(_singlet())
    before = lens.spot_rms()
    lens.vary(1, "radius")
    report = lens.optimize(max_iterations=20)
    assert "lens" not in report
    assert lens.spot_rms() <= before


def test_save_and_open_round_trip(tmp_path):
    lens = ks.sample("geiser-triplet")
    for ext in ("json", "seq", "zmx"):
        path = tmp_path / f"t.{ext}"
        lens.save(path)
        back = ks.open_lens(path)
        assert back.efl == pytest.approx(lens.efl, rel=1e-6), ext
    with pytest.raises(ValueError):
        lens.save(tmp_path / "t.txt")


def test_tolerance_through_the_api():
    lens = ks.Lens(_singlet())
    out = lens.tolerance(trials=200)
    assert out["units"] == "waves" and out["sensitivities"]
    one = lens.tolerance([{"kind": "DLT", "surface": 0, "limit": 1e-4}], trials=200)
    assert len(one["sensitivities"]) == 1


# -- console -----------------------------------------------------------------


def test_execute_captures_output_and_returns_the_lens():
    lens = ks.Lens(_singlet()).to_dict()
    out = _execute(
        "print('efl', round(lens.efl, 6))\nlens.set(0, 'thickness', 0.005)", lens
    )
    assert out["error"] is None and out["output"].startswith("efl ")
    assert out["lens"]["surfaces"][0]["thickness"] == 0.005


def test_execute_reports_the_script_traceback_only():
    out = _execute("x = 1\ny = x / 0", None)
    assert out["lens"] is None
    assert out["error"].startswith("Traceback")
    assert 'File "<console>", line 2' in out["error"]
    assert "runner.py" not in out["error"]
    assert _trim_traceback("plain") == "plain"


def test_execute_without_a_lens_variable_and_exit():
    assert _execute("lens = 3", None)["lens"] is None
    assert _execute("raise SystemExit", None)["error"] is None


def test_run_script_in_its_own_process():
    out = run_script("print(ks.sample('geiser-triplet').efl > 0)", None, timeout=120)
    assert out["error"] is None and out["output"].strip() == "True"
    assert out["timed_out"] is False and out["duration"] > 0


def test_run_script_time_limit():
    out = run_script("while True:\n    pass", None, timeout=1.0)
    assert out["timed_out"] is True and "longer than 1 s" in out["error"]


def test_api_reference_lists_the_calls():
    names = {r["name"]: r for r in api_reference()}
    assert "ks.sample" in names and "lens.optimize" in names
    assert names["lens.efl"]["doc"].startswith("Effective focal length")
    assert "self" not in names["lens.set"]["signature"]


# -- element drawings --------------------------------------------------------


def test_edge_thickness_and_sense_match_the_sphere_sag():
    r1, r2, t, semi = 0.05, -0.08, 0.004, 0.01
    (d,) = element_drawings(_singlet(r1, r2, t, semi), edge_margin=2 * MM)
    h = semi + 1 * MM
    expected = t - _sphere_sag(r1, semi) + _sphere_sag(r2, semi)  # flat land past ⌀e
    assert d["edge_thickness"] == pytest.approx(expected, rel=1e-9)
    assert d["outer_diameter"] == pytest.approx(2 * h)
    left, right = dict(d["left"]), dict(d["right"])
    assert left["Radius (mm)"] == "R 50.0000 CX"
    assert right["Radius (mm)"] == "R 80.0000 CX"  # R < 0 on the back: convex
    assert "<svg" in d["svg"] and "ISO 10110" in d["html"]


def test_concave_and_plano_surfaces():
    (d,) = element_drawings(_singlet(-0.05, 0.0, 0.002, 0.008))
    assert dict(d["left"])["Radius (mm)"] == "R 50.0000 CC"
    assert dict(d["right"])["Radius (mm)"] == "∞ (plano)"
    assert d["edge_thickness"] == pytest.approx(0.002 - _sphere_sag(-0.05, 0.008))


def test_tolerance_codes_come_from_the_tolerance_set():
    tols = [
        Tolerance(kind="DLF", surface=0, limit=2.0),
        Tolerance(kind="DLT", surface=0, limit=0.1 * MM),
        Tolerance(kind="DLN", surface=0, limit=0.001),
        Tolerance(kind="DLV", surface=0, limit=0.5),
        Tolerance(kind="TRX", surface=1, limit=math.radians(2 / 60)),
        Tolerance(kind="DLR", surface=1, limit=0.02 * MM),
    ]
    notes = {"5/": "5/3×0.16", "irregularity": "0.5", "1/": "1/2×0.1"}
    (d,) = element_drawings(_singlet(), tolerances=tols, notes=notes)
    left, right, mat = dict(d["left"]), dict(d["right"]), dict(d["material"])
    assert left["3/"] == "3/2(0.5)" and left["5/"] == "5/3×0.16"
    assert left["4/"] == "—"  # no tilt tolerance on the front surface
    assert right["3/"] == "—" and right["4/"] == "4/2.0′"
    assert right["Radius (mm)"].endswith("±0.0200")
    assert mat["Centre thickness (mm)"] == "4.000 ±0.100"
    assert mat["nd"].endswith("±0.001") and mat["νd"].endswith("±0.50")
    assert mat["1/"] == "1/2×0.1" and mat["0/"] == "—"


def test_cemented_groups_give_one_drawing_per_glass():
    drawings = ks.sample("double-gauss-us2784643").drawings()
    assert [d["surfaces"] for d in drawings] == [
        [0, 1],
        [2, 3],
        [3, 4],
        [6, 7],
        [7, 8],
        [9, 10],
    ]
    assert drawings[1]["glass"] == "S-BAH11" and drawings[2]["glass"] == "N-SF5"


def test_mirror_systems_have_no_glass_drawings():
    assert ks.sample("hubble-ota").drawings() == []


def test_aspheric_elements_draw_within_their_extent():
    for d in ks.sample("phone-camera-us7535658").drawings():
        assert d["edge_thickness"] > 0


# -- report --------------------------------------------------------------------


def test_report_is_self_contained_with_every_section(tmp_path):
    lens = ks.sample("geiser-triplet")
    path = tmp_path / "r.html"
    html = lens.report(path, trials=300, author="A. Designer")
    assert path.read_text(encoding="utf-8") == html
    for heading in (
        "System data",
        "First-order properties",
        "Prescription",
        "Field performance",
        "Polychromatic MTF",
        "Third-order aberrations",
        "Tolerance budget",
        "Element drawings (ISO 10110)",
    ):
        assert heading in html, heading
    assert "A. Designer" in html and ">50.00" in html  # EFL in mm
    assert html.count('class="drawing"') == 3
    assert "src=" not in html and "<link" not in html  # no external files


def test_report_options_leave_sections_out():
    html = lens_report_html(
        _singlet(), mtf=False, tolerances=False, drawings=False, title="T"
    )
    assert "<title>T</title>" in html
    assert (
        "MTF" not in html and "Tolerance budget" not in html and "ISO 10110" not in html
    )


def test_line_plot_svg():
    svg = line_plot_svg(
        [
            {"label": "a", "x": [0, 1], "y": [0, 1]},
            {"label": "b", "x": [0, 1], "y": [1, 1], "dashed": True},
        ],
        "x",
        "y",
    )
    assert svg.count("<polyline") == 2 and "stroke-dasharray" in svg
    assert line_plot_svg([], "x", "y") == ""


# -- API ---------------------------------------------------------------------


def _lens_json():
    return _singlet().model_dump(mode="json")


def test_report_and_drawings_endpoints():
    r = client.post("/api/lens/report", json={"lens": _lens_json(), "trials": 200})
    assert r.status_code == 200 and r.json()["html"].startswith("<!doctype html>")
    r = client.post(
        "/api/lens/drawings", json={"lens": _lens_json(), "notes": {"5/": "5/2×0.1"}}
    )
    (d,) = r.json()["drawings"]
    assert ["5/", "5/2×0.1"] in d["left"]


def test_script_endpoints():
    r = client.get("/api/script/reference")
    assert any(e["name"] == "lens.report" for e in r.json()["reference"])
    r = client.post(
        "/api/script/run",
        json={"code": "print(round(lens.efl * 1e3, 3))", "lens": _lens_json()},
        headers={"Origin": "http://127.0.0.1:8000"},
    )
    body = r.json()
    assert r.status_code == 200 and body["error"] is None
    assert float(body["output"]) > 0 and body["lens"] is not None


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://example.com"},
        {"Origin": "null"},
        {"Host": "evil.example.com"},
        {"Origin": "http://localhost.example.com"},
    ],
)
def test_script_run_refuses_other_sites(headers):
    r = client.post("/api/script/run", json={"code": "print(1)"}, headers=headers)
    assert r.status_code == 403


def test_script_run_can_be_disabled(monkeypatch):
    monkeypatch.setenv("KESTROVA_DISABLE_SCRIPTING", "1")
    r = client.post("/api/script/run", json={"code": "print(1)"})
    assert r.status_code == 403 and "disabled" in r.json()["detail"]


def test_script_run_refuses_remote_clients():
    remote = TestClient(app, client=("192.168.1.20", 5000))
    r = remote.post("/api/script/run", json={"code": "print(1)"})
    assert r.status_code == 403


def test_stop_on_a_concave_surface_passes_off_axis_rays():
    """A stop on a curved surface that is not the limiting aperture gets a
    flat aperture; at the vertex of a concave front surface that plane
    would sit behind the surface's rim and every off-axis ray would be
    lost. Narrowing the Geiser triplet's first air gap 20% (its published
    apertures fixed) makes another surface limiting: the pupil must still
    trace, with the same spot as with automatic apertures."""
    lens = ks.sample("geiser-triplet")
    gap = 0.8 * lens.get(1, "thickness")
    fixed = lens.copy().set(1, "thickness", gap)
    auto = lens.copy().set(1, "thickness", gap)
    for s in auto.surfaces:
        s.semi_diameter = None
    axis = fixed.fields()["fields"][0]
    assert axis["vignetted_fraction"] < 0.1
    assert fixed.spot_rms(0) == pytest.approx(auto.spot_rms(0), rel=0.02)
