"""Unit tests for the `agents` package (base Agent, movement, and animals)."""

from __future__ import annotations

import random

import pytest

from agents import (
    ActionType,
    Agent,
    AnimalAgent,
    DeathCause,
    HumanAgent,
    Needs,
    load_species,
    spawn_animals,
)
from world import TerrainType, Tile, WorldMap


def test_base_agent_is_abstract() -> None:
    """Base Agent cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Agent(id="a0", name="Abstract", position=(0, 0))  # type: ignore[abstract]


def test_needs_decay_starvation_and_exhaustion() -> None:
    """Needs stay in 0-10, decay each tick, and trigger starvation/exhaustion."""
    human = HumanAgent(id="h1", name="Ada", position=(0, 0), needs=Needs(15.0, -2.0, 5.0))
    assert (human.needs.hunger, human.needs.energy, human.needs.social) == (10.0, 0.0, 5.0)

    events = human.update_needs()
    assert "exhausted" in events
    assert human.exhausted is True
    assert human.can_perform(ActionType.MOVE) is False
    assert human.can_perform(ActionType.SLEEP) is True

    starving = HumanAgent(id="h2", name="Low", position=(0, 0), needs=Needs(0.1, 10.0, 10.0))
    all_events: list[str] = []
    for _ in range(15):
        if not starving.alive:
            break
        all_events.extend(starving.update_needs())
    assert "starving" in all_events and "died" in all_events
    assert starving.alive is False


def test_goto_wander_and_flee_from() -> None:
    """goto() uses map path(), wander() moves validly, and flee_from() increases distance."""
    world = WorldMap(width=7, height=7, seed=1)
    for y in range(7):
        for x in range(7):
            world.set_terrain(x, y, TerrainType.GRASS)
    for y in range(5):
        world.set_terrain(3, y, TerrainType.MOUNTAIN)

    walker = HumanAgent(id="h1", name="Walker", position=(1, 1), speed=2)
    assert walker.goto(world, (5, 1)) is True
    assert world.get_tile(*walker.position).walkable  # type: ignore[union-attr]

    rng = random.Random(42)
    assert walker.wander(world, rng) is True
    assert world.get_tile(*walker.position).walkable  # type: ignore[union-attr]

    prey = HumanAgent(id="h2", name="Prey", position=(2, 3), speed=1)
    threat = (1, 3)
    old_dist = (prey.x - threat[0]) ** 2 + (prey.y - threat[1]) ** 2
    assert prey.flee_from(world, threat, rng) is True
    assert (prey.x - threat[0]) ** 2 + (prey.y - threat[1]) ** 2 > old_dist


def test_bird_flies_over_water_and_mountain() -> None:
    """Birds with flies=True can traverse water and mountain tiles."""
    species = load_species()
    assert species["bird"].flies is True

    world = WorldMap(width=5, height=5, seed=1)
    for y in range(5):
        for x in range(5):
            world.set_terrain(x, y, TerrainType.WATER)

    bird = AnimalAgent(id="b1", name="Bird-1", position=(0, 0), species="bird", config=species["bird"])
    assert bird.goto(world, (4, 0)) is True
    assert bird.position == (3, 0)


def test_animal_old_age_and_starvation_record_death_cause() -> None:
    """Animals die of old age at effective_max_age and starve when hunger hits 0."""
    species = load_species()
    world = WorldMap(width=5, height=5, seed=1)
    rng = random.Random(1)

    old_rabbit = AnimalAgent(
        id="r1", name="Old", position=(2, 2), species="rabbit", config=species["rabbit"],
    )
    old_rabbit.age = old_rabbit.effective_max_age - 1
    old_rabbit.step(world, [old_rabbit], rng)
    assert old_rabbit.alive is False
    assert old_rabbit.death_cause is DeathCause.OLD_AGE

    hungry_deer = AnimalAgent(
        id="d1", name="Hungry", position=(2, 2), species="deer", config=species["deer"],
        needs=Needs(hunger=0.05, energy=8.0, social=8.0),
    )
    hungry_deer.step(world, [hungry_deer], rng)
    assert hungry_deer.alive is False
    assert hungry_deer.death_cause is DeathCause.STARVATION


def test_spawn_animals_uses_founding_range_and_seed() -> None:
    """spawn_animals spawns reproducible founding populations within species.json bounds."""
    species = load_species()
    world = WorldMap(width=25, height=25, seed=7)
    a1 = spawn_animals(world, species, random.Random(7))
    a2 = spawn_animals(world, species, random.Random(7))
    assert [(a.id, a.position, a.species) for a in a1] == [(a.id, a.position, a.species) for a in a2]
    for name, cfg in species.items():
        n = sum(1 for a in a1 if a.species == name)
        assert cfg.founding_min <= n <= cfg.founding_max
