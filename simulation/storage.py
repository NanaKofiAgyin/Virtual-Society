"""SQLite persistence for simulation events and pickled world snapshots (stdlib only)."""

from __future__ import annotations

import json
import pickle
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from simulation.engine import Simulation
    from simulation.evolution import SpeciesNode


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
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS phylo_tree (
                    species_id TEXT PRIMARY KEY,
                    parent_species TEXT,
                    born_tick INTEGER NOT NULL,
                    extinct_tick INTEGER,
                    peak_population INTEGER NOT NULL DEFAULT 0,
                    key_gene_averages TEXT NOT NULL,
                    habitat TEXT NOT NULL
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
        """Pickle and zlib-compress the simulation (excluding DB connection) into SQLite."""
        blob = zlib.compress(pickle.dumps(sim, protocol=pickle.HIGHEST_PROTOCOL), level=6)
        created_at = datetime.now(timezone.utc).isoformat()
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO snapshots (tick, created_at, data) VALUES (?, ?, ?)",
                (sim.environment.tick, created_at, sqlite3.Binary(blob)),
            )
            return int(cur.lastrowid or 0)

    def load_latest_snapshot(self) -> Simulation | None:
        """Load and decompress the most recent pickled Simulation, reattaching this Storage."""
        cur = self.conn.execute(
            "SELECT data FROM snapshots ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            return None
        raw = bytes(row[0])
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass
        sim: Simulation = pickle.loads(raw)
        sim.storage = self
        return sim

    def upsert_species(self, node: SpeciesNode) -> None:
        """Insert or update a phylogenetic tree node in SQLite."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO phylo_tree
                    (species_id, parent_species, born_tick, extinct_tick,
                     peak_population, key_gene_averages, habitat)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(species_id) DO UPDATE SET
                    extinct_tick = excluded.extinct_tick,
                    peak_population = MAX(phylo_tree.peak_population, excluded.peak_population),
                    key_gene_averages = excluded.key_gene_averages,
                    habitat = excluded.habitat
                """,
                (
                    node.species_id,
                    node.parent_species,
                    node.born_tick,
                    node.extinct_tick,
                    node.peak_population,
                    json.dumps(node.key_gene_averages),
                    node.habitat,
                ),
            )

    def load_phylo_tree(self) -> list[dict[str, Any]]:
        """Load all phylogenetic tree nodes ordered by `born_tick`."""
        cur = self.conn.execute(
            """
            SELECT species_id, parent_species, born_tick, extinct_tick,
                   peak_population, key_gene_averages, habitat
            FROM phylo_tree ORDER BY born_tick ASC, species_id ASC
            """
        )
        return [
            {
                "species_id": r[0], "parent_species": r[1], "born_tick": r[2],
                "extinct_tick": r[3], "peak_population": r[4],
                "key_gene_averages": json.loads(r[5]), "habitat": r[6],
            }
            for r in cur.fetchall()
        ]

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()
