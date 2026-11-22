"""Unit tests for `simulation/engine.py` and `simulation/storage.py`."""

from __future__ import annotations

import json
from pathlib import Path

from simulation import Simulation, Storage


def test_founding_humans_survive_a_month() -> None:
    """Founding humans survive 30 simulated days (720 ticks) and log midnight summaries."""
    sim = Simulation(seed=42, founding_humans=12)
    assert len(sim.humans) == 12
    assert len({h.persona.name for h in sim.humans}) == 12

    sim.run(ticks=30 * 24)

    alive_humans = [h for h in sim.humans if h.alive]
    assert len(alive_humans) >= 10
    summaries = [e for e in sim.events if e["kind"] == "summary"]
    assert len(summaries) >= 5


def test_converse_updates_social_relationships_memories_and_logs() -> None:
    """converse(a, b) exchanges one line each and updates social, affinity, memories, and log."""
    sim = Simulation(seed=7)
    ada, bram = sim.humans[0], sim.humans[1]
    ada.needs.social = 3.0
    bram.needs.social = 3.0

    line_a, line_b = sim.converse(ada, bram)
    assert line_a and line_b
    assert ada.needs.social > 3.0
    assert bram.needs.social > 3.0
    assert ada.relationships[bram.id] > 0.0
    assert bram.relationships[ada.id] > 0.0
    assert any("Talked with" in m.text for m in ada.memory.recent(5))
    dialogue_events = [e for e in sim.events if e["kind"] == "dialogue"]
    assert len(dialogue_events) == 2


def test_state_is_json_serializable() -> None:
    """Simulation.state() returns a clean JSON-serializable viewer dictionary."""
    sim = Simulation(seed=3, width=20, height=20, founding_humans=12)
    sim.run(ticks=5)
    payload = sim.state()
    encoded = json.dumps(payload)
    assert len(encoded) > 0
    assert payload["counts"]["humans"] == 12
    assert payload["environment"]["tick"] == 5


def test_sqlite_save_and_load_round_trip(tmp_path: Path) -> None:
    """Storage saves events and pickled snapshots (excluding DB connection) and restores them."""
    db_file = tmp_path / "test_world.db"
    storage = Storage(db_file)
    try:
        sim = Simulation(seed=99, width=20, height=20, storage=storage)
        sim.run(ticks=24)
        snap_id = storage.save_snapshot(sim)
        assert snap_id > 0

        loaded = storage.load_latest_snapshot()
        assert loaded is not None
        assert loaded.storage is storage
        assert loaded.environment.tick == sim.environment.tick
        assert loaded.seed == sim.seed
        assert len(loaded.humans) == len(sim.humans)
        assert [h.position for h in loaded.humans] == [h.position for h in sim.humans]
        assert len(loaded.animals) == len(sim.animals)
        assert len(storage.recent_events()) >= 1
    finally:
        storage.close()
