"""Unit tests for biological & cultural human evolution (`agents/culture.py`, `data/tech.json`)."""

from __future__ import annotations

import random

from agents import GENES, HumanAgent, Needs, Persona, random_genome
from agents.culture import (
    CulturalProfile,
    attempt_discovery,
    cultural_distance,
    determine_era,
    inherit_culture,
    load_techs,
    spread_knowledge,
    step_society,
)


def test_tech_tree_and_biological_human_genes() -> None:
    """data/tech.json loads full tech tree and GENES includes biological human selection traits."""
    techs = load_techs()
    for required in ("fire", "stone_tools", "shelter", "spears", "fishing", "boats",
                     "farming", "pottery", "weaving", "the_wheel", "bronze", "iron",
                     "writing", "medicine", "sailing", "irrigation"):
        assert required in techs
    assert {"cold_tolerance", "heat_tolerance", "disease_resistance", "intelligence", "endurance"}.issubset(GENES)


def test_tech_discovery_teaching_and_knowledge_loss_on_death() -> None:
    """Tech is discovered with prereqs/materials, spreads via teaching, and is LOST if last knower dies."""
    techs = load_techs()
    rng = random.Random(7)

    ada = HumanAgent(
        id="h1", name="Ada", position=(5, 5),
        persona=Persona("Ada", 25, "farmer", ("curious",)),
        genome=random_genome({"intelligence": 0.95}, rng=rng, spread=0.0),
        inventory={"wood": 5.0, "food": 5.0}, skills={"farmer": 3.0},
    )
    bram = HumanAgent(
        id="h2", name="Bram", position=(6, 5),
        persona=Persona("Bram", 26, "builder", ("steady",)),
        genome=random_genome({"intelligence": 0.85}, rng=rng, spread=0.0),
        skills={"builder": 2.0},
    )

    discovered = None
    for _ in range(600):
        discovered = attempt_discovery(ada, [bram], group_size=15, techs=techs, rng=rng)
        if discovered is not None:
            break
    assert discovered in techs
    assert discovered in ada.culture.known_techs

    # Spread to Bram via teaching
    taught = None
    for _ in range(15):
        taught = spread_knowledge(ada, bram, rng)
        if taught is not None:
            break
    assert taught == discovered
    assert discovered in bram.culture.known_techs

    # If both people who know a unique tech die, it becomes LOST
    ever = {discovered, "writing"}
    ada.culture.known_techs.add("writing")
    ada.alive = False  # Ada was the ONLY person who knew "writing"
    summary, _ = step_society([ada, bram], techs, ever, rng, tick=100)
    assert "writing" in summary["lost_techs"]
    assert "writing" not in summary["known_techs"]
    assert discovered in summary["known_techs"]


def test_isolated_groups_drift_culturally_over_generations() -> None:
    """Passing language and norms across isolated generations causes cultural distance to grow."""
    rng = random.Random(42)
    group_a = [HumanAgent(id=f"a{i}", name=f"A{i}", position=(5, 5), culture=CulturalProfile(group_id="A")) for i in range(2)]
    group_b = [HumanAgent(id=f"b{i}", name=f"B{i}", position=(90, 90), culture=CulturalProfile(group_id="B")) for i in range(2)]
    assert cultural_distance(group_a[0].culture, group_b[0].culture) == 0.0

    for _ in range(12):
        c_a = inherit_culture(group_a[0], group_a[1], rng)
        c_b = inherit_culture(group_b[0], group_b[1], rng)
        group_a[0].culture, group_a[1].culture = c_a, inherit_culture(group_a[0], group_a[1], rng)
        group_b[0].culture, group_b[1].culture = c_b, inherit_culture(group_b[0], group_b[1], rng)

    assert cultural_distance(group_a[0].culture, group_b[0].culture) > 0.20


def test_settlements_leaders_laws_and_era_tracking() -> None:
    """Clustering humans forms settlements with leaders, laws, population counts, and era names."""
    techs = load_techs()
    rng = random.Random(3)
    villagers = [
        HumanAgent(
            id=f"h{i}", name=f"V{i}", position=(10 + (i % 3), 10),
            needs=Needs(8, 8, 8), inventory={"food": 5.0},
            culture=CulturalProfile(known_techs={"fire", "pottery", "bronze"} if i == 0 else set()),
        )
        for i in range(6)
    ]
    summary, _ = step_society(villagers, techs, {"fire", "pottery", "bronze"}, rng, tick=24)
    assert len(summary["settlements"]) == 1
    st = summary["settlements"][0]
    assert st["population"] == 6
    assert st["leader_id"] is not None
    assert len(st["laws"]) >= 1
    assert summary["era"] == "Bronze Age"
    assert determine_era({"iron"}, techs) == "Iron Age"
