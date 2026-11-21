"""Unit tests for the `agents` package (base Agent, movement, and animals)."""

from __future__ import annotations

import random

import pytest

from agents import (
    ALL_ACTIONS,
    ActionType,
    Agent,
    AnimalAgent,
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

    # Starve until death
    starving = HumanAgent(id="h2", name="Low", position=(0, 0), needs=Needs(0.1, 10.0, 10.0))
    all_events: list[str] = []
    for _ in range(15):
        if not starving.alive:
            break
        all_events.extend(starving.update_needs())
    assert "starving" in all_events
    assert "died" in all_events
    assert starving.alive is False


def test_goto_wander_and_flee_from() -> None:
    """goto() uses map path(), wander() moves validly, and flee_from() increases distance."""
    world = WorldMap(width=7, height=7, seed=1)
    for y in range(7):
        for x in range(7):
            world.tiles[y][x] = Tile.from_terrain(x, y, TerrainType.GRASS)
    for y in range(5):
        world.tiles[y][3] = Tile.from_terrain(3, y, TerrainType.MOUNTAIN)

    walker = HumanAgent(id="h1", name="Walker", position=(1, 1), speed=2)
    assert walker.goto(world, (5, 1)) is True
    assert walker.position != (1, 1)
    assert world.get_tile(*walker.position).walkable  # type: ignore[union-attr]

    rng = random.Random(42)
    before = walker.position
    assert walker.wander(world, rng) is True
    assert world.get_tile(*walker.position).walkable  # type: ignore[union-attr]
    assert walker.position != before or world.in_bounds(*walker.position)

    prey = HumanAgent(id="h2", name="Prey", position=(2, 3), speed=1)
    threat = (1, 3)
    old_dist = (prey.x - threat[0]) ** 2 + (prey.y - threat[1]) ** 2
    assert prey.flee_from(world, threat, rng) is True
    new_dist = (prey.x - threat[0]) ** 2 + (prey.y - threat[1]) ** 2
    assert new_dist > old_dist


def test_bird_flies_over_water_and_mountain() -> None:
    """Birds with flies=True can traverse water and mountain tiles."""
    species = load_species()
    assert species["bird"].flies is True
    assert species["wolf"].max_pop == 4

    world = WorldMap(width=5, height=5, seed=1)
    for y in range(5):
        for x in range(5):
            world.tiles[y][x] = Tile.from_terrain(x, y, TerrainType.WATER)

    bird = AnimalAgent(id="b1", name="Bird-1", position=(0, 0), species="bird", config=species["bird"])
    assert bird.goto(world, (4, 0)) is True
    assert bird.position == (3, 0)  # speed is 3


def test_animal_old_age_and_starvation() -> None:
    """Animals die of old age at max_age and starve when hunger hits 0."""
    species = load_species()
    world = WorldMap(width=5, height=5, seed=1)
    rng = random.Random(1)

    old_rabbit = AnimalAgent(
        id="r1",
        name="Old",
        position=(2, 2),
        species="rabbit",
        config=species["rabbit"],
        age=species["rabbit"].max_age - 1,
    )
    counts = {"rabbit": 1}
    old_rabbit.step(world, [old_rabbit], rng, counts)
    assert old_rabbit.alive is False

    hungry_deer = AnimalAgent(
        id="d1",
        name="Hungry",
        position=(2, 2),
        species="deer",
        config=species["deer"],
        needs=Needs(hunger=0.05, energy=8.0, social=8.0),
    )
    counts = {"deer": 1}
    hungry_deer.step(world, [hungry_deer], rng, counts)
    assert hungry_deer.alive is False


@pytest.mark.parametrize("seed", [1, 42, 99])
def test_ecosystem_90_days_no_extinction_no_overpopulation(seed: int) -> None:
    """Over 90 simulated days (2160 ticks), no species goes extinct or exceeds max_pop."""
    species = load_species()
    world = WorldMap(width=50, height=50, seed=seed)
    rng = random.Random(seed + 1000)
    animals = spawn_animals(world, species, rng)
    next_id = len(animals)

    def gen_id() -> str:
        nonlocal next_id
        next_id += 1
        return f"a_{next_id}"

    ticks = 90 * 24  # 2,160 hourly ticks
    for _ in range(ticks):
        world.advance_time(1)
        counts: dict[str, int] = {name: 0 for name in species}
        for a in animals:
            if a.alive:
                counts[a.species] += 1

        newborns: list[AnimalAgent] = []
        for animal in animals:
            if not animal.alive:
                continue
            child = animal.step(world, animals, rng, counts, next_id_fn=gen_id)
            if child is not None:
                newborns.append(child)

        animals = [a for a in animals if a.alive] + newborns

        live_counts = {name: 0 for name in species}
        for a in animals:
            live_counts[a.species] += 1
        for name, cfg in species.items():
            assert live_counts[name] <= cfg.max_pop, f"{name} exceeded max_pop on seed {seed}"

    final_counts = {name: 0 for name in species}
    for a in animals:
        final_counts[a.species] += 1
    for name, cfg in species.items():
        assert final_counts[name] > 0, f"{name} went extinct on seed {seed}: {final_counts}"
        assert final_counts[name] <= cfg.max_pop
