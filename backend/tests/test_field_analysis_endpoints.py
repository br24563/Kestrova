"""Tests for the ray-fan, OPD-fan, field-curve and constraint endpoints."""
import math
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from api.main import app

client = TestClient(app)


def _preset(pid):
    return client.get(f"/api/presets/{pid}").json()["system"]


def test_ray_fan_thick_lens_has_spherical_aberration():
    data = client.post("/api/analyze/ray-fan",
                       json={"system": _preset("thick_lens"), "field_fraction": 0.0}).json()
    t = data["transverse_t"]
    assert len(t) == len(data["pupil_x"]) == 21
    # on axis the tangential fan is odd in py and non-zero at the pupil edge
    assert abs(t[0] + t[-1]) < 1e-9
    assert abs(t[-1]) > 1e-5
    assert data["field_unit"] in ("deg", "m")


def test_opd_fan_reports_wavefront_statistics():
    data = client.post("/api/analyze/opd-fan",
                       json={"system": _preset("thick_lens"), "field_fraction": 1.0}).json()
    assert data["opd_rms"] > 0
    assert data["opd_peak_to_valley"] >= data["opd_rms"]
    assert 0 <= data["strehl_ratio"] <= 1
    assert math.isclose(data["wavelength"], 550e-9)


def test_field_curves_start_at_paraxial_focus_on_axis():
    data = client.post("/api/analyze/field-curves",
                       json={"system": _preset("thick_lens"), "num_fields": 5}).json()
    assert data["field_fractions"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert data["distortion"][0] == 0.0
    # on axis tangential and sagittal foci coincide
    assert abs(data["tangential_focus"][0] - data["sagittal_focus"][0]) < 1e-9


def test_image_plane_plots_reject_afocal_systems():
    system = _preset("keplerian_telescope")
    for ep in ("ray-fan", "opd-fan", "field-curves"):
        r = client.post(f"/api/analyze/{ep}", json={"system": system})
        assert r.status_code == 400
        assert "infinity" in r.json()["detail"]


def test_constraint_values_and_penalty():
    r = client.post("/api/optimize/constraints", json={
        "system": _preset("thick_lens"),
        "constraints": [
            {"type": "efl", "lower": 0.2, "upper": None, "weight": 2.0},
            {"type": "center_thickness", "surface_index": 0},
            {"type": "center_thickness", "surface_index": 9},
        ],
    }).json()["constraints"]
    efl = r[0]["value"]
    assert 0.09 < efl < 0.11
    assert math.isclose(r[0]["penalty"], 2.0 * (0.2 - efl) * 1e6)
    assert math.isclose(r[1]["value"], 0.01)
    assert r[1]["penalty"] == 0
    assert r[2]["value"] is None and r[2]["error"]


def test_hybrid_accepts_null_bounds_and_reports_true_merit():
    system = _preset("thick_lens")
    r = client.post("/api/optimize/hybrid", json={
        "system": system, "objective": "rms_spot",
        "params": [{"component_id": "TL1", "field": "radius1"}], "bounds": [[0.05, 0.15]],
        "constraints": [{"type": "efl", "lower": 0.099, "upper": None}],
        "global_maxiter": 5, "local_maxiter": 5, "seed": 1,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    # the merit after local refinement never exceeds the global result
    assert data["objective"] <= data["global_objective"] + 1e-15


def test_hybrid_target_objective_requires_target():
    r = client.post("/api/optimize/hybrid", json={
        "system": _preset("thick_lens"), "objective": "efl",
        "params": [{"component_id": "TL1", "field": "radius1"}], "bounds": [[0.05, 0.15]],
    })
    assert r.status_code == 400
