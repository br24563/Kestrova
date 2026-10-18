"""Tests for optical system validation."""
import pytest
from pydantic import ValidationError
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from optics.models import (
    OpticalSystem, ThinLens, ThickLens, Object, ImagePlane, AnalysisSettings
)


class TestThinLensValidation:
    """Tests for ThinLens field validation."""

    def test_zero_focal_length_raises(self):
        """Zero focal length should raise ValueError."""
        with pytest.raises(ValidationError, match="Focal length cannot be zero"):
            ThinLens(id="L1", position=0.1, focal_length=0.0, aperture_diameter=0.025)

    def test_near_zero_focal_length_raises(self):
        """Near-zero focal length should raise ValueError."""
        with pytest.raises(ValidationError, match="Focal length cannot be zero"):
            ThinLens(id="L1", position=0.1, focal_length=1e-15, aperture_diameter=0.025)

    def test_negative_aperture_raises(self):
        """Negative aperture diameter should raise ValueError."""
        with pytest.raises(ValidationError, match="Aperture diameter must be positive"):
            ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=-0.025)

    def test_zero_aperture_raises(self):
        """Zero aperture diameter should raise ValueError."""
        with pytest.raises(ValidationError, match="Aperture diameter must be positive"):
            ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.0)

    def test_empty_id_raises(self):
        """Empty ID should raise ValueError."""
        with pytest.raises(ValidationError, match="Component ID cannot be empty"):
            ThinLens(id="", position=0.1, focal_length=0.1, aperture_diameter=0.025)

    def test_valid_thin_lens(self):
        """Valid thin lens should be created successfully."""
        lens = ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025)
        assert lens.focal_length == 0.1
        assert lens.aperture_diameter == 0.025

    def test_diverging_lens_valid(self):
        """Diverging lens (negative focal length) should be valid."""
        lens = ThinLens(id="L1", position=0.1, focal_length=-0.05, aperture_diameter=0.025)
        assert lens.focal_length == -0.05


class TestOpticalSystemValidation:
    """Tests for OpticalSystem validation."""

    def test_empty_wavelengths_raises(self):
        """Empty wavelengths list should raise ValueError."""
        with pytest.raises(ValidationError, match="At least one wavelength"):
            OpticalSystem(
                components=[ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025)],
                wavelengths=[],
                object=Object(position=0.0, height=0.01),
                image_plane=ImagePlane(position=0.3),
            )

    def test_negative_wavelength_raises(self):
        """Negative wavelength should raise ValueError."""
        with pytest.raises(ValidationError, match="Wavelengths must be positive"):
            OpticalSystem(
                components=[ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025)],
                wavelengths=[-550e-9],
                object=Object(position=0.0, height=0.01),
                image_plane=ImagePlane(position=0.3),
            )

    def test_duplicate_ids_raises(self):
        """Duplicate component IDs should raise ValueError."""
        with pytest.raises(ValidationError, match="Component IDs must be unique"):
            OpticalSystem(
                components=[
                    ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025),
                    ThinLens(id="L1", position=0.2, focal_length=0.05, aperture_diameter=0.025),
                ],
                wavelengths=[550e-9],
                object=Object(position=0.0, height=0.01),
                image_plane=ImagePlane(position=0.3),
            )

    def test_valid_system(self):
        """Valid system should be created successfully."""
        system = OpticalSystem(
            components=[
                ThinLens(id="L1", position=0.1, focal_length=0.1, aperture_diameter=0.025),
                ThinLens(id="L2", position=0.2, focal_length=0.05, aperture_diameter=0.025),
            ],
            wavelengths=[550e-9],
            object=Object(position=0.0, height=0.01),
            image_plane=ImagePlane(position=0.3),
        )
        assert len(system.components) == 2


class TestPresetsAPI:
    """Tests for presets API endpoints."""

    def test_get_presets_list(self):
        """Should return list of preset metadata."""
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        assert all(k in data[0] for k in ["id", "name", "description", "category"])

    def test_get_preset_by_id(self):
        """Should return full preset system."""
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/presets/single_lens")
        assert resp.status_code == 200
        data = resp.json()
        assert "system" in data
        assert "id" in data

    def test_get_preset_not_found(self):
        """Should return 404 for unknown preset."""
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/presets/nonexistent")
        assert resp.status_code == 404

    def test_health_check(self):
        """Health check should return status."""
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "features" in data
