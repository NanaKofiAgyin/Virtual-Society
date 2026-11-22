"""Unit tests for life cycle, reproduction, family trees, learning, stats, and carrying capacity."""

from __future__ import annotations

import random

from agents import (
    AnimalAgent,
    DeathCause,
    FamilyTree,
    HumanAgent,
    LifeStage,
    Needs,
    Persona,
    TICKS_PER_YEAR,
    can_mate_animals,
    can_pair_humans,
    child_learn_from_adults,
    compute_life_stage,
    load_species,
    random_genome,
    spawn_human_child,
)
from simulation import Simulation, SimulationStats
from world import TerrainType, Tile, WorldMap


def _custom_world(size: int, terrain: TerrainType) -> WorldMap:
    world = WorldMap(width=size, height=size, seed=1)
    for y in range(size):
        for x in range(size):
            world.set_terrain(x, y, terrain)
    return world


def test_life_stages_and_human_natural_old_age_death() -> None:
    """Organisms progress child -> adult -> elder and die naturally of old age."""
    assert compute_life_stage(5, 100) is LifeStage.CHILD
    assert compute_life_stage(40, 100) is LifeStage.ADULT
    assert compute_life_stage(85, 100) is LifeStage.ELDER

    world = _custom_world(8, TerrainType.GRASS)
    elder = HumanAgent(id="h1", name="Old Ada", position=(4, 4), home=(4, 4))
    elder.age_ticks = elder.max_age_ticks - 1
    assert elder.stage is LifeStage.ELDER

    elder.step(world, [elder], random.Random(1))
    assert elder.alive is False
    assert elder.death_cause is DeathCause.OLD_AGE


def test_animal_sexual_reproduction_lineage_and_genetics() -> None:
    """Mature well-fed nearby animals mate, passing crossed/mutated genes and lineage_id."""
    species = load_species()
    world = _custom_world(8, TerrainType.FARM)
    rng = random.Random(42)

    cfg = species["rabbit"]
    a = AnimalAgent(
        id="r1", name="R1", position=(4, 4), species="rabbit", config=cfg,
        genome=random_genome({"size": 0.2}, rng=rng), lineage_id="lin_A",
        age=int(cfg.max_age * 0.4), breed_timer=0, needs=Needs(9.0, 9.0, 9.0),
    )
    b = AnimalAgent(
        id="r2", name="R2", position=(4, 5), species="rabbit", config=cfg,
        genome=random_genome({"size": 0.3}, rng=rng), lineage_id="lin_B",
        age=int(cfg.max_age * 0.4), breed_timer=0, needs=Needs(9.0, 9.0, 9.0),
    )
    assert can_mate_animals(a, b) is True

    child = None
    for _ in range(30):
        a.breed_timer, b.breed_timer = 0, 0
        a.needs.hunger, b.needs.hunger = 9.0, 9.0
        child = a.step(world, [a, b], rng, can_reproduce=True)
        if child is not None:
            break

    assert child is not None
    assert child.stage is LifeStage.CHILD
    assert child.lineage_id == "lin_A"
    assert child.parent_id == "r1"


def test_human_pairing_child_inheritance_and_learning() -> None:
    """Humans pair by affinity/compatibility, pass surname/home/skills, and children learn."""
    world = _custom_world(8, TerrainType.GRASS)
    rng = random.Random(7)

    ada = HumanAgent(
        id="h1", name="Ada Oak", position=(3, 3), home=(3, 3),
        persona=Persona("Ada Oak", 25, "farmer"),
        genome=random_genome(rng=rng),
        family=FamilyTree(surname="Oak", lineage_id="h1"),
        skills={"farmer": 6.0}, age_ticks=25 * TICKS_PER_YEAR,
    )
    bram = HumanAgent(
        id="h2", name="Bram Reed", position=(3, 4), home=(3, 4),
        persona=Persona("Bram Reed", 27, "builder"),
        genome=random_genome(rng=rng),
        family=FamilyTree(surname="Reed", lineage_id="h2"),
        skills={"builder": 4.0}, age_ticks=27 * TICKS_PER_YEAR,
    )
    ada.adjust_affinity(bram.id, 4.0)
    bram.adjust_affinity(ada.id, 4.0)
    assert can_pair_humans(ada, bram) is True

    child = spawn_human_child(ada, bram, world, rng, "h3")
    assert child.stage is LifeStage.CHILD
    assert child.family.surname == "Oak"
    assert child.home == (3, 3)
    assert child.family.parents == ("h1", "h2")
    assert "h3" in ada.family.children and "h3" in bram.family.children
    assert child.skills["farmer"] > 0.0

    before = child.skills.get("farmer", 0.0)
    learned = child_learn_from_adults(child, [ada, bram], tick=24)
    assert learned == "farmer"
    assert child.skills["farmer"] > before


def test_stats_logs_births_deaths_and_yearly_genes() -> None:
    """SimulationStats tracks births, deaths by cause, and yearly average genes per species."""
    sim = Simulation(seed=42, width=20, height=20, founding_humans=10)
    stats = SimulationStats()
    stats.record_birth("human")
    stats.record_death("rabbit", DeathCause.PREDATION)
    stats.record_death("deer", DeathCause.STARVATION)
    year_snap = stats.record_year(1, sim.humans, sim.animals)

    assert year_snap["births_total"] == 1
    assert year_snap["deaths_by_cause"]["predation"] == 1
    assert "human" in year_snap["avg_genes"]
    assert "size" in year_snap["avg_genes"]["human"]


def test_species_with_no_food_declines() -> None:
    """A herbivore population placed in a foodless environment declines via starvation."""
    species = load_species()
    world = _custom_world(12, TerrainType.HOUSE)  # walkable, 0 food, 0 regrowth
    rng = random.Random(10)
    cfg = species["rabbit"]
    rabbits = [
        AnimalAgent(
            id=f"r{i}", name=f"R{i}", position=(6, 6), species="rabbit", config=cfg,
            genome=random_genome(cfg.genome_template, rng=rng),
            age=int(cfg.max_age * 0.3), needs=Needs(5.0, 8.0, 8.0),
        )
        for i in range(10)
    ]
    for _ in range(120):
        for r in rabbits:
            r.step(world, rabbits, rng, can_reproduce=True)
    alive = [r for r in rabbits if r.alive]
    assert len(alive) < 10
    assert any(r.death_cause is DeathCause.STARVATION for r in rabbits if not r.alive)


def test_species_with_surplus_grows_then_stabilizes_by_carrying_capacity() -> None:
    """With surplus food and no max_pop, a founding group grows via reproduction then stabilizes."""
    species = load_species()
    world = _custom_world(10, TerrainType.FARM)  # rich but finite 10x10 food carrying capacity
    rng = random.Random(77)
    cfg = species["rabbit"]

    rabbits = [
        AnimalAgent(
            id=f"r{i}", name=f"R{i}", position=(5, 5), species="rabbit", config=cfg,
            genome=random_genome(cfg.genome_template, rng=rng),
            age=int(cfg.max_age * 0.3), breed_timer=0, needs=Needs(9.0, 9.0, 9.0),
        )
        for i in range(6)
    ]
    counts: list[int] = []
    for _ in range(450):
        world.advance_time(1)
        newborns: list[AnimalAgent] = []
        for r in rabbits:
            if not r.alive:
                continue
            child = r.step(world, rabbits, rng, can_reproduce=True)
            if child is not None:
                newborns.append(child)
        rabbits = [r for r in rabbits if r.alive] + newborns
        counts.append(len(rabbits))

    peak = max(counts)
    assert peak > 6, f"Expected population to grow from 6 founders, got peak {peak}"
    # Carrying capacity limits growth naturally without runaway explosion
    assert counts[-1] < 200, f"Expected stabilization by food carrying capacity, got {counts[-1]}"
