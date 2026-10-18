"""Tests for the Seidel aberration analysis endpoint."""
import pytest
from fastapi.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from api.main import app
from optics.systems import create_default_system

client = TestClient(app)


def test_seidel_endpoint_returns_all_aberrations():
    system = create_default_system()
    response = client.post("/api/analyze/seidel", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    assert "spherical_aberration" in data
    assert "coma" in data
    assert "astigmatism" in data
    assert "field_curvature" in data
    assert "distortion" in data
    assert "paraxial_image_position" in data
    assert "paraxial_image_height" in data


def test_seidel_endpoint_spherical_has_longitudinal_transverse():
    system = create_default_system()
    response = client.post("/api/analyze/seidel", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    sa = data["spherical_aberration"]
    assert "longitudinal" in sa
    assert "transverse" in sa


def test_seidel_endpoint_paraxial_position_finite():
    system = create_default_system()
    response = client.post("/api/analyze/seidel", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    import math
    assert math.isfinite(data["paraxial_image_position"])
    assert math.isfinite(data["paraxial_image_height"])


def test_seidel_endpoint_distortion_is_float():
    system = create_default_system()
    response = client.post("/api/analyze/seidel", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["distortion"], float)
