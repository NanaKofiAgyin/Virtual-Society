"""SQLite persistence for simulation events and pickled world snapshots (stdlib only)."""

from __future__ import annotations

import pickle
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from simulation.engine import Simulation


class Storage:
    """Manages SQLite tables for event logs and full-world pickled snapshots."""

    def __init__(self, db_path: str | Path = "virtual_society.db") -> None:
        """Open SQLite database at `db_path` and ensure schema tables exist."""
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create `events` and `snapshots` tables if they do not exist."""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    data BLOB NOT NULL
                )
                """
            )

    def log_event(self, tick: int, kind: str, message: str) -> None:
        """Insert a single simulation event row."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO events (tick, kind, message) VALUES (?, ?, ?)",
                (tick, kind, message),
            )

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return up to `limit` most recent events in chronological order."""
        cur = self.conn.execute(
            "SELECT tick, kind, message FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = [{"tick": r[0], "kind": r[1], "message": r[2]} for r in cur.fetchall()]
        rows.reverse()
        return rows

    def save_snapshot(self, sim: Simulation) -> int:
        """Pickle the simulation (excluding DB connection) and store it in SQLite."""
        blob = pickle.dumps(sim)
        created_at = datetime.now(timezone.utc).isoformat()
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO snapshots (tick, created_at, data) VALUES (?, ?, ?)",
                (sim.environment.tick, created_at, sqlite3.Binary(blob)),
            )
            return int(cur.lastrowid or 0)

    def load_latest_snapshot(self) -> Simulation | None:
        """Load and return the most recent pickled Simulation, reattaching this Storage."""
        cur = self.conn.execute(
            "SELECT data FROM snapshots ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            return None
        sim: Simulation = pickle.loads(row[0])
        sim.storage = self
        return sim

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()
