"""Unit tests for `simulation/evolution.py` (speciation, phylo tree, extinctions, niche shifts)."""

from __future__ import annotations

import random
from pathlib import Path

from agents import AnimalAgent, Needs, crossover, load_species, mutate, random_genome
from simulation import SpeciationEngine, Storage
from world import BodyType, TerrainType, WorldMap


def _barrier_world() -> WorldMap:
    """Create a 40x20 grassland world split down the middle by an impassable mountain wall."""
    world = WorldMap(width=40, height=20, seed=1)
    for y in range(20):
        for x in range(40):
            world.set_terrain(x, y, TerrainType.MOUNTAIN if 18 <= x <= 21 else TerrainType.GRASSLAND)
    return world


def test_isolated_populations_speciate_and_persist_to_phylo_tree(tmp_path: Path) -> None:
    """Two isolated populations in different climates diverge into a new species stored in SQLite."""
    species = load_species()
    cfg = species["deer"]
    world = _barrier_world()
    storage = Storage(tmp_path / "phylo.db")
    rng = random.Random(42)

    try:
        engine = SpeciationEngine(
            {"deer": cfg}, tick=0, storage=storage,
            isolation_distance=15.0, genetic_threshold=0.16, divergence_generations=3,
        )

        # West group (cold-adapted) vs East group (heat-adapted) separated by mountain barrier
        west = [
            AnimalAgent(
                id=f"w{i}", name=f"W{i}", position=(5, 10), species="deer", config=cfg,
                genome=random_genome({"cold_tolerance": 0.90, "heat_tolerance": 0.15, "size": 0.80}, rng=rng, spread=0.03),
                needs=Needs(8, 8, 8),
            )
            for i in range(6)
        ]
        east = [
            AnimalAgent(
                id=f"e{i}", name=f"E{i}", position=(34, 10), species="deer", config=cfg,
                genome=random_genome({"cold_tolerance": 0.15, "heat_tolerance": 0.90, "size": 0.30}, rng=rng, spread=0.03),
                needs=Needs(8, 8, 8),
            )
            for i in range(6)
        ]

        sp_map = {"deer": cfg}
        speciation_events = []
        for gen in range(1, 6):
            # Reproduce within each isolated group (no gene flow across the barrier)
            west = [
                AnimalAgent(
                    id=f"w_{gen}_{i}", name=f"W{i}", position=(5, 10), species=west[0].species,
                    config=west[0].config,
                    genome=mutate(crossover(west[i % 6].genome, west[(i + 1) % 6].genome, rng=rng), rate=0.05, rng=rng),
                )
                for i in range(6)
            ]
            east = [
                AnimalAgent(
                    id=f"e_{gen}_{i}", name=f"E{i}", position=(34, 10), species=east[0].species,
                    config=east[0].config,
                    genome=mutate(crossover(east[i % 6].genome, east[(i + 1) % 6].genome, rng=rng), rate=0.05, rng=rng),
                )
                for i in range(6)
            ]
            evs = engine.step_year(tick=gen * 672, animals=[*west, *east], species_map=sp_map, world=world, storage=storage)
            speciation_events.extend(e for e in evs if e["kind"] == "speciation")

        assert len(speciation_events) >= 1
        assert len(sp_map) >= 2
        tree_rows = storage.load_phylo_tree()
        child_nodes = [r for r in tree_rows if r["parent_species"] == "deer"]
        assert len(child_nodes) >= 1
        assert child_nodes[0]["born_tick"] > 0
    finally:
        storage.close()


def test_extinction_and_mass_extinction_recorded(tmp_path: Path) -> None:
    """Extinctions record extinct_tick in SQLite; mass_extinction requires a physical cause."""
    species = load_species()
    sp_map = {k: species[k] for k in ("deer", "rabbit", "wolf")}
    world = _barrier_world()
    storage = Storage(tmp_path / "extinct.db")
    try:
        # Without a physical cause, extinctions never trigger a random mass_extinction event
        no_cause_engine = SpeciationEngine(sp_map, tick=0)
        wolves = [AnimalAgent(id="w1", name="W1", position=(5, 5), species="wolf", config=sp_map["wolf"])]
        evs_no_cause = no_cause_engine.step_year(tick=672, animals=wolves, species_map=sp_map, world=world)
        assert "mass_extinction" not in [e["kind"] for e in evs_no_cause]

        engine = SpeciationEngine(sp_map, tick=0, storage=storage)
        # Only wolf survives during a volcanic winter (2/3 = 66% -> physical mass extinction)
        evs = engine.step_year(
            tick=672, animals=wolves, species_map=sp_map, world=world,
            storage=storage, physical_cause="volcanic_winter",
        )

        kinds = [e["kind"] for e in evs]
        assert kinds.count("extinction") == 2
        assert "mass_extinction" in kinds

        rows = {r["species_id"]: r for r in storage.load_phylo_tree()}
        assert rows["deer"]["extinct_tick"] == 672
        assert rows["rabbit"]["extinct_tick"] == 672
        assert rows["wolf"]["extinct_tick"] is None
    finally:
        storage.close()


def test_niche_shift_from_land_to_shoreline_to_water() -> None:
    """Drifting habitat_preference shifts a land species to amphibian, then aquatic."""
    species = load_species()
    sp_map = {"deer": species["deer"]}
    world = _barrier_world()
    engine = SpeciationEngine(sp_map, tick=0)

    # Drift habitat_preference >= 0.72 -> land shifts to amphibian (shoreline)
    herd = [
        AnimalAgent(
            id=f"d{i}", name=f"D{i}", position=(5, 5), species="deer", config=sp_map["deer"],
            genome=random_genome({"habitat_preference": 0.78}, rng=random.Random(i), spread=0.01),
        )
        for i in range(4)
    ]
    evs1 = engine.step_year(tick=672, animals=herd, species_map=sp_map, world=world)
    assert any(e["kind"] == "niche_shift" for e in evs1)
    assert sp_map["deer"].body_type == "amphibian"
    assert all(a.body_type is BodyType.AMPHIBIAN for a in herd)

    # Drift further >= 0.88 -> amphibian shifts to aquatic (water)
    for a in herd:
        a.genome["habitat_preference"] = 0.92
    evs2 = engine.step_year(tick=1344, animals=herd, species_map=sp_map, world=world)
    assert any(e["kind"] == "niche_shift" for e in evs2)
    assert sp_map["deer"].body_type == "aquatic"
    assert all(a.body_type is BodyType.AQUATIC for a in herd)
