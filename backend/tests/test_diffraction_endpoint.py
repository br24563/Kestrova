"""Tests for the diffraction analysis endpoint."""
import pytest
from fastapi.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from api.main import app
from optics.systems import create_default_system

client = TestClient(app)


def test_diffraction_endpoint_returns_psf():
    system = create_default_system()
    response = client.post("/api/analyze/diffraction", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    assert "psf" in data
    assert "encircled_energy" in data
    assert "mtf" in data
    assert "strehl_ratio" in data
    assert "airy_disk_radius" in data
    assert "diffraction_limited" in data


def test_diffraction_endpoint_mtf_cutoff_positive():
    system = create_default_system()
    response = client.post("/api/analyze/diffraction", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    # cutoff 2 NA / lambda, NA from the real image-space marginal ray
    assert data["mtf"]["cutoff"] == pytest.approx(
        2.0 * data["na_image"] / system.analysis_settings.wavelength, rel=1e-9)


def test_diffraction_endpoint_psf_peak_at_center():
    system = create_default_system()
    response = client.post("/api/analyze/diffraction", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    psf = data["psf"]
    # PSF intensity should peak at or near the center
    max_intensity = max(psf["intensity"])
    assert psf["intensity"][0] >= max_intensity * 0.9


def test_diffraction_endpoint_airy_radius_positive():
    system = create_default_system()
    response = client.post("/api/analyze/diffraction", json={"system": system.model_dump()})
    assert response.status_code == 200
    data = response.json()
    assert data["airy_disk_radius"] > 0
