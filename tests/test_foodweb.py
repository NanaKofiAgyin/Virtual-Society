"""Unit tests for the trophic food web, 10% energy rule, carcasses, migration, and cascades."""

from __future__ import annotations

import random

from agents import AnimalAgent, Needs, load_species, random_genome
from agents.ecosystem import (
    Carcass,
    decompose_carcasses,
    migration_target,
    pollination_multiplier,
    predator_prey_capture_prob,
    trophic_energy_gain,
)
from world import Season, TerrainType, WorldMap


def test_species_json_covers_all_trophic_levels_and_habitats() -> None:
    """data/species.json defines all trophic levels, all 4 habitats, and required fields."""
    species = load_species()
    levels = {c.trophic_level for c in species.values()}
    habitats = {c.habitat for c in species.values()}

    assert {"producer", "primary_consumer", "secondary_consumer",
            "apex_predator", "scavenger", "decomposer", "pollinator"}.issubset(levels)
    assert {"sea", "fresh_water", "land", "air"}.issubset(habitats)
    for cfg in species.values():
        assert cfg.max_age > 0
        assert cfg.litter_size[0] >= 1 and cfg.litter_size[1] >= cfg.litter_size[0]
        assert isinstance(cfg.eaten_by, tuple)
        assert isinstance(cfg.genome_ranges, dict)


def test_ten_percent_trophic_transfer_and_carcass_decomposition() -> None:
    """Predators gain ~10% of prey energy; dead carcasses return nutrients to soil."""
    assert trophic_energy_gain(100.0) == 10.0
    assert trophic_energy_gain(25.0) == 2.5

    world = WorldMap(width=10, height=10, seed=1)
    world.set_terrain(5, 5, TerrainType.GRASSLAND)
    world.food[5, 5] = 0.2
    carcasses = [Carcass(x=5, y=5, species="deer", energy=60.0)]
    carcasses = decompose_carcasses(carcasses, world, has_decomposers=True)
    assert float(world.food[5, 5]) > 0.2
    assert carcasses[0].energy < 60.0


def test_coevolution_capture_probability_and_seasonal_migration() -> None:
    """Faster/camouflaged prey evade better; migratory species move toward equator in winter."""
    species = load_species()
    wolf = AnimalAgent(id="w1", name="W", position=(5, 5), species="wolf", config=species["wolf"],
                       genome=random_genome({"speed": 0.5, "vision": 0.5}, rng=random.Random(1), spread=0.0))
    slow_prey = AnimalAgent(id="r1", name="Slow", position=(5, 5), species="rabbit", config=species["rabbit"],
                            genome=random_genome({"speed": 0.2, "camouflage": 0.2, "vision": 0.2}, rng=random.Random(1), spread=0.0))
    fast_prey = AnimalAgent(id="r2", name="Fast", position=(5, 5), species="rabbit", config=species["rabbit"],
                            genome=random_genome({"speed": 0.9, "camouflage": 0.9, "vision": 0.9}, rng=random.Random(1), spread=0.0))
    assert predator_prey_capture_prob(wolf, fast_prey) < predator_prey_capture_prob(wolf, slow_prey)

    world = WorldMap(width=20, height=20, seed=1)
    for y in range(20):
        for x in range(20):
            world.set_terrain(x, y, TerrainType.GRASSLAND)
    deer = AnimalAgent(id="d1", name="Deer", position=(10, 2), species="deer", config=species["deer"])
    world.environment.season_index = 3  # WINTER -> move south toward equator (y=10)
    assert world.environment.season is Season.WINTER
    target = migration_target(deer, world)
    assert target == (10, 3)


def test_remove_predators_herbivores_overshoot_and_crash() -> None:
    """Without predators on a finite patch, herbivores overshoot carrying capacity then crash."""
    species = load_species()
    cfg = species["rabbit"]
    world = WorldMap(width=6, height=6, seed=1)
    for y in range(6):
        for x in range(6):
            world.set_terrain(x, y, TerrainType.GRASSLAND)
            world.food[y, x] = 2.0  # initial boom surplus, low regrowth
            world.food_max[y, x] = 0.5
            world.food_regen[y, x] = 0.02

    rng = random.Random(42)
    rabbits = [
        AnimalAgent(
            id=f"r{i}", name=f"R{i}", position=(3, 3), species="rabbit", config=cfg,
            genome=random_genome(cfg.genome_template, rng=rng),
            age=int(cfg.max_age * 0.25), breed_timer=0, needs=Needs(9.5, 9.0, 9.0),
        )
        for i in range(10)
    ]
    history: list[int] = []
    for _ in range(360):
        world.regrow(0.5)
        newborns: list[AnimalAgent] = []
        for r in rabbits:
            if not r.alive:
                continue
            child = r.step(world, rabbits, rng, can_reproduce=True)
            if child is not None:
                newborns.append(child)
        rabbits = [r for r in rabbits if r.alive] + newborns
        history.append(len(rabbits))

    peak = max(history)
    final = history[-1]
    assert peak > 14, f"Expected herbivore overshoot above 10 founders, got peak={peak}"
    assert final < peak * 0.75, f"Expected crash after overshoot: peak={peak}, final={final}"


def test_remove_pollinators_plant_populations_drop() -> None:
    """Removing pollinators causes plant/food populations to drop compared to pollinated world."""
    species = load_species()
    w_with = WorldMap(width=12, height=12, seed=5)
    w_none = WorldMap(width=12, height=12, seed=5)
    for w in (w_with, w_none):
        for y in range(12):
            for x in range(12):
                w.set_terrain(x, y, TerrainType.GRASSLAND)
                w.food[y, x] = 0.2  # depleted plants needing regrowth

    bees = [
        AnimalAgent(id=f"b{i}", name=f"Bee{i}", position=(6, 6), species="bee", config=species["bee"])
        for i in range(10)
    ]
    for _ in range(24):
        w_with.regrow(pollination_multiplier(bees))
        w_none.regrow(pollination_multiplier([]))

    assert float(w_with.food.sum()) > float(w_none.food.sum()) * 1.5
