"""
SQLite persistence for optical systems.

This module provides a simple, local-first database for saving and
loading named optical system projects. It uses Python's built-in
sqlite3 module — no external database server or paid service required.

The database stores each system as a JSON string, which is the
serialized form of the Pydantic OpticalSystem model. This keeps the
schema simple and forward-compatible as the data model evolves.

Database file location: backend/optical_systems.db (configurable).
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Default database location (relative to this file's directory)
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "optical_systems.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection to the SQLite database and ensure the schema exists."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS systems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            system_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _now() -> str:
    """Return the current UTC timestamp as an ISO string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_system(
    name: str,
    system_json: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """
    Save an optical system to the database.

    If a system with the same name already exists, it is updated
    (the name acts as a unique key for simplicity).

    Args:
        name: A human-readable name for the project.
        system_json: The serialized OpticalSystem (JSON string).
        db_path: Path to the SQLite database file.

    Returns:
        The id of the saved system.
    """
    conn = _connect(db_path)
    try:
        now = _now()
        # Check if a system with this name already exists
        row = conn.execute(
            "SELECT id FROM systems WHERE name = ?", (name,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE systems SET system_json = ?, updated_at = ? WHERE id = ?",
                (system_json, now, row["id"]),
            )
            conn.commit()
            return row["id"]
        else:
            cur = conn.execute(
                "INSERT INTO systems (name, system_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (name, system_json, now, now),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def list_systems(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """
    List all saved systems (metadata only, not the full system JSON).

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A list of dicts with keys: id, name, created_at, updated_at.
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at FROM systems ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_system(system_id: int, db_path: Path = DEFAULT_DB_PATH) -> Optional[dict]:
    """
    Load a saved system by id.

    Args:
        system_id: The id of the system to load.
        db_path: Path to the SQLite database file.

    Returns:
        A dict with keys: id, name, system_json, created_at, updated_at.
        Returns None if the id does not exist.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, name, system_json, created_at, updated_at FROM systems WHERE id = ?",
            (system_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_system(system_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """
    Delete a saved system by id.

    Args:
        system_id: The id of the system to delete.
        db_path: Path to the SQLite database file.

    Returns:
        True if a system was deleted, False if the id did not exist.
    """
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM systems WHERE id = ?", (system_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()