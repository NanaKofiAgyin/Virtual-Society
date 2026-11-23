"""Tests for slow realistic human progress, Tasmania effect, domestication, migration, and tech tree."""

from __future__ import annotations

import pathlib
import random

from agents.culture import load_techs
from simulation.progress import (
    DomesticatedLineage,
    ProgressTracker,
    classify_social_structure,
    culture_era_name,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_slow_millennial_discovery_and_farming_writing_gates() -> None:
    """Fire/stone tools take many generations; farming needs domestication; writing needs large settled pop."""
    techs = load_techs()
    tracker = ProgressTracker(techs, random.Random(42))
    g = tracker.add_group(10, 10, "savanna", pop=24, has_wild_crops=False)

    # First 20 generations (500 years): too early for fire/stone_tools (requires 35-45 practice gens)
    for gen in range(1, 21):
        tracker.step_generation(year=gen * 25)
    assert not g.known_techs

    # Over 120 generations (3,000 years), stone-age techs emerge, but NOT farming (no wild crops) or writing (pop<80)
    for gen in range(21, 121):
        tracker.step_generation(year=gen * 25)
    assert "fire" in g.known_techs or "stone_tools" in g.known_techs
    assert "farming" not in g.known_techs
    assert "writing" not in g.known_techs
    assert tracker.tech_origins, "First-appearance date & place must be recorded"
    orig = next(iter(tracker.tech_origins.values()))
    assert orig.year >= 500 and orig.place == "savanna"


def test_tasmania_effect_loses_complex_techs_when_connected_pop_drops() -> None:
    """Small isolated groups below min_learners lose complex techs via imperfect transmission."""
    techs = load_techs()
    tracker = ProgressTracker(techs, random.Random(7))
    island = tracker.add_group(5, 5, "island", pop=6, has_wild_crops=False)
    island.known_techs.update({"boats", "bronze", "writing", "pottery"})

    for gen in range(1, 35):
        tracker.step_generation(year=gen * 25)
    assert len(island.lost_techs) >= 1
    assert any(t not in island.known_techs for t in ("boats", "bronze", "writing", "pottery"))


def test_domestication_artificial_selection_shifts_genes() -> None:
    """Breeding wild plants/animals shifts docility and yield_size upward via artificial selection."""
    rng = random.Random(11)
    wheat = DomesticatedLineage("wild_grain", "plant")
    assert not wheat.is_domesticated
    for _ in range(16):
        wheat.breed_generation(rng)
    assert wheat.docility > 0.65 and wheat.yield_size > 0.60
    assert wheat.is_domesticated


def test_scarcity_migration_land_bridges_isolation_and_per_culture_eras() -> None:
    """Food scarcity splits bands, crosses low-sea-level land bridges, and cultures progress at different speeds."""
    techs = load_techs()
    tracker = ProgressTracker(techs, random.Random(19))
    g1 = tracker.add_group(20, 20, "grassland", pop=30, has_wild_crops=True)
    g1.food_store = 10.0  # scarcity (< 1.5 per capita)

    evs = tracker.step_generation(year=1000, sea_level=0.40)
    assert len(tracker.groups) == 2
    assert any(e["kind"] == "migration" and e["via_bridge"] for e in evs)

    # Per-culture eras & emergent social tiers
    assert culture_era_name(set()) == "Early Foragers"
    assert culture_era_name({"fire", "stone_tools"}) == "Stone-Age Hunter-Gatherers"
    assert culture_era_name({"fire", "stone_tools", "pottery", "farming"}) == "Neolithic Farmers"
    assert culture_era_name({"fire", "bronze"}) == "Bronze-Age Metal-Users"
    assert culture_era_name({"iron"}) == "Iron-Age Metal-Users"

    assert classify_social_structure(15, 5.0, set())["tier"] == "band"
    assert classify_social_structure(40, 10.0, {"fire"})["tier"] == "tribe"
    assert classify_social_structure(120, 60.0, {"farming"})["tier"] == "village"
    assert classify_social_structure(300, 150.0, {"farming", "writing", "bronze"})["tier"] == "city"

    tree = tracker.to_tech_tree_dict()
    assert "cultures" in tree and "origins" in tree and "tech_specs" in tree
    html = (ROOT / "server" / "static" / "index.html").read_text(encoding="utf-8")
    assert "tech-tree-box" in html
