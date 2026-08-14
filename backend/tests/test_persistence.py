"""
Tests for the SQLite persistence module.

These tests verify that optical systems can be saved, listed, loaded,
and deleted correctly. Each test uses a temporary database file so
the real database is never touched.
"""

import json
import pytest
from pathlib import Path

from persistence import (
    save_system, list_systems, get_system, delete_system,
)
from optics.systems import create_default_system


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path for each test."""
    return tmp_path / "test_systems.db"


def test_save_and_get_system(db_path: Path):
    """A saved system should be retrievable by id."""
    system = create_default_system()
    system_json = system.model_dump_json()

    system_id = save_system("test_project", system_json, db_path)
    saved = get_system(system_id, db_path)

    assert saved is not None
    assert saved["name"] == "test_project"
    # The JSON should round-trip back to an equivalent system
    loaded = json.loads(saved["system_json"])
    assert loaded["object"]["height"] == system.object.height
    assert len(loaded["components"]) == len(system.components)


def test_save_updates_existing_name(db_path: Path):
    """Saving with an existing name should update, not duplicate."""
    system = create_default_system()
    system_json = system.model_dump_json()

    id1 = save_system("project", system_json, db_path)
    id2 = save_system("project", system_json, db_path)

    # Same name should reuse the same id
    assert id1 == id2
    systems = list_systems(db_path)
    assert len(systems) == 1


def test_list_systems(db_path: Path):
    """list_systems should return metadata for all saved systems."""
    system = create_default_system()
    system_json = system.model_dump_json()

    save_system("alpha", system_json, db_path)
    save_system("beta", system_json, db_path)

    systems = list_systems(db_path)
    assert len(systems) == 2
    names = {s["name"] for s in systems}
    assert names == {"alpha", "beta"}
    # Metadata should not include the full system_json
    assert "system_json" not in systems[0]


def test_get_nonexistent_system(db_path: Path):
    """get_system should return None for a missing id."""
    assert get_system(999, db_path) is None


def test_delete_system(db_path: Path):
    """delete_system should remove a saved system."""
    system = create_default_system()
    system_json = system.model_dump_json()

    system_id = save_system("to_delete", system_json, db_path)
    assert get_system(system_id, db_path) is not None

    deleted = delete_system(system_id, db_path)
    assert deleted is True
    assert get_system(system_id, db_path) is None


def test_delete_nonexistent_system(db_path: Path):
    """delete_system should return False for a missing id."""
    assert delete_system(999, db_path) is False