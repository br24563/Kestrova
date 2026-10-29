"""
SQLite persistence for optical systems.

This module provides a simple, local-first database for saving and
loading named optical system projects. It uses Python's built-in
sqlite3 module — no external database server or paid service required.

The database stores each system as a JSON string, which is the
serialized form of the Pydantic OpticalSystem model. This keeps the
schema simple and forward-compatible as the data model evolves.

Database file location: ``$KESTROVA_DATA_DIR/optical_systems.db`` when that
variable is set (the desktop app sets it to its user-data folder), the
operating system's per-user data folder in a frozen build, and
backend/optical_systems.db when run from source.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def data_dir() -> Path:
    """Where user data is kept (see the module docstring)."""
    if os.environ.get("KESTROVA_DATA_DIR"):
        base = Path(os.environ["KESTROVA_DATA_DIR"])
    elif getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home())) / "Kestrova"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "Kestrova"
        else:
            xdg = os.environ.get("XDG_DATA_HOME") or str(
                Path.home() / ".local" / "share"
            )
            base = Path(xdg) / "kestrova"
    else:
        return Path(__file__).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    return base


DEFAULT_DB_PATH = data_dir() / "optical_systems.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection to the SQLite database and ensure the schema exists."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS systems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            system_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
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
        row = conn.execute("SELECT id FROM systems WHERE name = ?", (name,)).fetchone()
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
