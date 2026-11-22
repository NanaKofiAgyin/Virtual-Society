"""Unit tests for LOD tiers, spatial hash grid, variable time scales, and compressed snapshots."""

from __future__ import annotations

import pickle
import random
import time
from pathlib import Path

from agents import AnimalAgent, load_species
from simulation import (
    LODManager,
    LODTier,
    PopulationGroup,
    Simulation,
    SpatialHashGrid,
    Storage,
    TimeScale,
)


def test_spatial_hash_grid_accuracy_and_5000_agent_speed() -> None:
    """SpatialHashGrid finds exact neighbors and rebuilds/queries 5,000 agents rapidly."""
    species = load_species()
    cfg = species["rabbit"]
    rng = random.Random(42)
    agents = [
        AnimalAgent(id=f"a{i}", name=f"A{i}", position=(rng.randrange(200), rng.randrange(200)),
                    species="rabbit", config=cfg)
        for i in range(5000)
    ]
    grid = SpatialHashGrid(cell_size=8)
    t0 = time.perf_counter()
    grid.rebuild(agents)
    hits = grid.query_radius(100, 100, radius=10)
    elapsed = time.perf_counter() - t0

    expected = [a for a in agents if abs(a.x - 100) <= 10 and abs(a.y - 100) <= 10]
    assert {a.id for a in hits} == {a.id for a in expected}
    assert elapsed < 0.25, f"Spatial hash on 5,000 agents too slow: {elapsed:.3f}s"


def test_tier3_group_growth_and_materialization() -> None:
    """Tier 3 PopulationGroup grows logistically and materializes into AnimalAgent individuals."""
    species = load_species()
    rng = random.Random(7)
    group = PopulationGroup(species="small_fish", x=10, y=10, count=100.0, carrying_capacity=400.0)
    for _ in range(20):
        group.step(hours=24, regrow_mult=1.2, rng=rng)
    assert group.count > 100.0

    before = group.count
    counter = 0

    def gen_id() -> str:
        nonlocal counter
        counter += 1
        return f"fish_{counter}"

    individuals = group.materialize(5, species, rng, gen_id)
    assert len(individuals) == 5
    assert all(isinstance(a, AnimalAgent) and a.species == "small_fish" for a in individuals)
    assert group.count == before - 5


def test_variable_time_scales_and_performance_report() -> None:
    """NORMAL (+1h), FAST (+24h), and GEOLOGICAL (+168h) advance cleanly with perf report."""
    sim = Simulation(seed=42, width=40, height=40)

    sim.lod.time_scale = TimeScale.NORMAL
    sim.tick()
    assert sim.environment.tick == 1

    sim.lod.time_scale = TimeScale.FAST
    sim.tick()
    assert sim.environment.tick == 25

    sim.lod.time_scale = TimeScale.GEOLOGICAL
    t0 = time.perf_counter()
    sim.run(10)
    elapsed = time.perf_counter() - t0
    assert sim.environment.tick == 25 + 10 * 168

    report = sim.lod.format_performance_report(10, elapsed, sim.humans, sim.animals)
    assert "ticks/sec" in report
    assert "Tier 1:" in report and "Tier 2:" in report and "Tier 3:" in report


def test_compressed_snapshots_smaller_than_raw_pickle(tmp_path: Path) -> None:
    """SQLite snapshots are zlib-compressed and restore full simulation state accurately."""
    db_file = tmp_path / "compressed.db"
    storage = Storage(db_file)
    try:
        sim = Simulation(seed=5, width=60, height=60, storage=storage)
        sim.run(5)
        raw_size = len(pickle.dumps(sim))
        storage.save_snapshot(sim)
        comp_size = storage.conn.execute("SELECT LENGTH(data) FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert comp_size < raw_size * 0.5, f"Expected strong compression: {comp_size} vs {raw_size}"

        loaded = storage.load_latest_snapshot()
        assert loaded is not None
        assert loaded.environment.tick == 5
        assert len(loaded.lod.groups) == len(sim.lod.groups)
    finally:
        storage.close()
