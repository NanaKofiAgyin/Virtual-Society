"""Tests for CC0 sprite assets, gene-driven sprite payload fields, and dot-free sprite renderer."""

from __future__ import annotations

import pathlib
import random

from agents.animal import AnimalAgent
from agents.base import Needs
from agents.ecosystem import load_species
from agents.genome import random_genome
from agents.human import HumanAgent, Persona
from agents.lifecycle import FamilyTree, spawn_human_child
from world.map import WorldMap

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_cc0_assets_and_licenses_exist() -> None:
    """CC0 SVG sprite packs and assets/LICENSES.md exist with valid license documentation."""
    lic = ROOT / "assets" / "LICENSES.md"
    assert lic.is_file()
    text = lic.read_text(encoding="utf-8")
    assert "CC0" in text
    for svg_name in ("terrain_props.svg", "buildings.svg"):
        p = ROOT / "assets" / "sprites" / svg_name
        assert p.is_file()
        assert "<svg" in p.read_text(encoding="utf-8")


def test_animal_and_human_serialization_exposes_sprite_genes_stage_sex_and_action() -> None:
    """Backend state includes genome, stage, sex, and animation action for layered sprite rendering."""
    species = load_species()
    wolf = AnimalAgent(
        id="w1", name="Wolf-1", position=(5, 5), species="wolf",
        config=species["wolf"], sex="M", last_action="walk",
    )
    d = wolf.to_dict()
    assert d["species"] == "wolf"
    assert d["sex"] == "M"
    assert d["stage"] in ("baby", "juvenile", "adult", "elder")
    assert d["last_action"] == "walk"
    assert {"size", "speed", "cold_tolerance", "camouflage"}.issubset(d["genome"].keys())

    # Verify human skin_tone adapts gradually toward equatorial sunlight over generations
    world = WorldMap(width=20, height=40, seed=7)
    rng = random.Random(7)
    equator = (10, 20)
    p1 = HumanAgent(
        id="h1", name="Ada Ash", position=equator, home=equator,
        persona=Persona("Ada Ash", 24, "farmer"), needs=Needs(),
        genome=random_genome({"skin_tone": 0.2, "hair_tone": 0.3}, rng=rng, spread=0.0),
        family=FamilyTree(surname="Ash", lineage_id="h1"), sex="F",
    )
    p2 = HumanAgent(
        id="h2", name="Bram Ash", position=equator, home=equator,
        persona=Persona("Bram Ash", 25, "hunter"), needs=Needs(),
        genome=random_genome({"skin_tone": 0.2, "hair_tone": 0.3}, rng=rng, spread=0.0),
        family=FamilyTree(surname="Ash", lineage_id="h2"), sex="M",
    )
    # Equatorial sunlight (~1.0) shifts mean skin_tone darker than 0.20 baseline over a cohort
    children = [spawn_human_child(p1, p2, world, rng, f"h_{i}") for i in range(3, 15)]
    detail = children[0].detail()
    assert detail["sex"] in ("M", "F")
    assert detail["stage"] == "child"
    assert "skin_tone" in detail["genome"] and "hair_tone" in detail["genome"]
    mean_skin = sum(c.genome["skin_tone"] for c in children) / len(children)
    assert mean_skin > 0.23


def test_canvas_uses_cached_sprites_and_frustum_culling_with_zero_entity_dots() -> None:
    """canvas.js renders sprites via WorldSprites/WorldHumanSprites/WorldStructures with frustum culling."""
    js = (ROOT / "server" / "static" / "canvas.js").read_text(encoding="utf-8")
    assert "WorldSprites.getAnimalSprite" in js
    assert "WorldHumanSprites.getHumanSprite" in js
    assert "WorldStructures.renderVisibleStructures" in js
    assert "visibleBounds(" in js
    assert "ctx.arc(" not in js
