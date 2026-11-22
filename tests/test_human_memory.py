"""Unit tests for `agents/memory.py`, `agents/human.py`, and `agents/utility.py`."""

from __future__ import annotations

import json
import random
from typing import Any

from agents import (
    AnimalAgent,
    HumanAgent,
    MemoryStream,
    Needs,
    Persona,
    load_species,
    score_importance,
)
from agents.utility import HUNTER_MIN_BREEDING_STOCK, SHELTER_WOOD_COST
from llm import LLMClient
from world import TerrainType, Tile, Weather, WorldMap


def _flat_grass_world(size: int = 10) -> WorldMap:
    world = WorldMap(width=size, height=size, seed=1)
    for y in range(size):
        for x in range(size):
            world.set_terrain(x, y, TerrainType.GRASS)
    world.environment.hour = 10  # daytime
    world.environment.weather = Weather.CLEAR
    return world


def test_memory_keyword_importance_and_forgetting() -> None:
    """Free keyword scoring assigns expected weights and forgets least valuable old entries."""
    assert score_importance("A villager died in winter") == 9
    assert score_importance("Saw a wolf near the farm") == 7
    assert score_importance("Gave bread to a neighbor") == 6
    assert score_importance("Shared apples by the fire") == 6
    assert score_importance("Talked with Ada") == 3
    assert score_importance("Walked across the meadow") == 2

    stream = MemoryStream(cap=3)
    stream.add("A villager died", tick=1)         # importance 9 (must survive forgetting)
    stream.add("Walked across grass", tick=2)     # importance 2 (oldest trivial -> forgotten)
    stream.add("Saw a wolf near forest", tick=5)  # importance 7
    stream.add("Talked with Bob", tick=20)        # importance 3, recent

    assert len(stream) == 3
    texts = [m.text for m in stream.recent(3)]
    assert "Walked across grass" not in texts
    assert "A villager died" in texts

    top = stream.retrieve("wolf forest", current_tick=21, k=1)
    assert len(top) == 1
    assert "wolf" in top[0].text.lower()


def test_human_priority_flee_wolf_and_shelter_in_storm() -> None:
    """Priority 1 flees wolves; Priority 2 goes home/shelters during storms or night."""
    world = _flat_grass_world()
    species = load_species()
    rng = random.Random(42)

    human = HumanAgent(id="h1", name="Ada", position=(5, 5), home=(2, 5))
    wolf = AnimalAgent(id="w1", name="Wolf", position=(6, 5), species="wolf", config=species["wolf"])

    action = human.step(world, [human, wolf], rng)
    assert action == "flee_wolf"
    assert human.x < 5
    assert any("wolf" in m.text.lower() for m in human.memory.recent(5))

    # Storm sends human home to shelter
    world.environment.weather = Weather.STORM
    human.position = (3, 5)
    assert human.step(world, [human], rng) == "go_home"
    human.position = human.home
    assert human.step(world, [human], rng) == "shelter"


def test_human_eat_and_share_food_with_hungry_neighbor() -> None:
    """Priority 3 eats when hunger < 4; Priority 4 shares surplus food with hungry neighbor."""
    world = _flat_grass_world()
    rng = random.Random(7)

    ada = HumanAgent(
        id="h1", name="Ada", position=(4, 4),
        needs=Needs(hunger=3.0, energy=8.0, social=8.0),
        inventory={"food": 2.0},
    )
    assert ada.step(world, [ada], rng) == "eat"
    assert ada.needs.hunger > 6.0

    # Now Ada is full with surplus food and Bob is hungry right next to her
    ada.inventory["food"] = 3.0
    ada.needs.hunger = 9.0
    bob = HumanAgent(
        id="h2", name="Bob", position=(5, 4),
        needs=Needs(hunger=3.5, energy=8.0, social=8.0),
    )
    assert ada.step(world, [ada, bob], rng) == "give_food"
    assert bob.inventory.get("food", 0.0) == 1.0
    assert ada.relationships["h2"] > 0.0
    assert bob.relationships["h1"] > 0.0


def test_human_speech_template_vs_live_llm_and_detail() -> None:
    """Speech uses templates in mock mode and live model with memories when is_live()."""
    world = _flat_grass_world()
    rng = random.Random(1)
    ada = HumanAgent(
        id="h1", name="Ada", position=(4, 4),
        persona=Persona(name="Ada", age=28, job="farmer", traits=("warm",), goal="Grow crops"),
        needs=Needs(hunger=8.0, energy=8.0, social=3.0),
    )
    bob = HumanAgent(id="h2", name="Bob", position=(5, 4), persona=Persona(name="Bob", job="healer"))

    # Mock client (is_live() == False) -> uses template line depending on weather/job
    mock_client = LLMClient(mode="mock")
    world.environment.weather = Weather.RAIN
    line = ada.speak(bob, world, mock_client, rng)
    assert "rain" in line.lower()

    # Live Ollama client (mocked HTTP) -> uses model reply
    class _FakeResp:
        def read(self) -> bytes:
            return json.dumps({"message": {"content": '{"speech": "Harvest is looking great, Bob!"}'}}).encode()
        def __enter__(self) -> _FakeResp:
            return self
        def __exit__(self, *args: Any) -> None:
            return None

    live_client = LLMClient(mode="ollama", urlopen_fn=lambda *a, **k: _FakeResp(), sleep_fn=lambda _: None)
    assert live_client.is_live() is True
    live_line = ada.speak(bob, world, live_client, rng)
    assert live_line == "Harvest is looking great, Bob!"

    info = ada.detail()
    assert info["persona"]["job"] == "farmer"
    assert info["last_speech"] == live_line
    assert len(info["memories"]) >= 2


def test_hunter_breeding_stock_and_builder_wood_cost() -> None:
    """Hunters spare prey at/below breeding stock; builders require SHELTER_WOOD_COST wood."""
    world = _flat_grass_world()
    species = load_species()
    rng = random.Random(2)

    hunter = HumanAgent(
        id="h1", name="Rex", position=(4, 4),
        persona=Persona(name="Rex", job="hunter"),
        needs=Needs(hunger=9.0, energy=9.0, social=9.0),
    )
    rabbits = [
        AnimalAgent(id=f"r{i}", name=f"R{i}", position=(5, 4), species="rabbit", config=species["rabbit"])
        for i in range(HUNTER_MIN_BREEDING_STOCK)
    ]
    action = hunter.step(world, [hunter, *rabbits], rng)
    assert not action.startswith("hunt")
    assert all(r.alive for r in rabbits)

    builder = HumanAgent(
        id="h2", name="Bea", position=(3, 3),
        persona=Persona(name="Bea", job="builder"),
        needs=Needs(hunger=9.0, energy=9.0, social=9.0),
        inventory={"wood": SHELTER_WOOD_COST - 1.0},
    )
    assert builder.step(world, [builder], rng) != "build_shelter"
    assert world.get_tile(3, 3).terrain == TerrainType.GRASS  # type: ignore[union-attr]

    builder.inventory["wood"] = SHELTER_WOOD_COST
    assert builder.step(world, [builder], rng) == "build_shelter"
    assert world.get_tile(*builder.position).terrain == TerrainType.HOUSE  # type: ignore[union-attr]
    assert builder.inventory.get("wood", 0.0) == 0.0


def test_daily_plan_at_06_and_reflection_at_23_template_and_live() -> None:
    """06:00 creates a daily plan and 23:00 writes a reflection, both saved as memories."""
    world = _flat_grass_world()
    rng = random.Random(5)
    ada = HumanAgent(
        id="h1", name="Ada", position=(4, 4), home=(4, 4),
        persona=Persona(name="Ada", age=30, job="farmer", traits=("steady",), goal="Feed village"),
        needs=Needs(hunger=8.0, energy=8.0, social=8.0),
    )

    # Template mode at 06:00
    world.environment.hour = 6
    ada.step(world, [ada], rng, llm_client=LLMClient(mode="mock"))
    assert "farmer" in ada.daily_plan.lower()
    assert any(m.text.startswith("Daily plan:") for m in ada.memory.recent(5))

    # Add a notable daytime memory, then reflect at 23:00 (template mode)
    world.environment.tick = 12
    ada.memory.add("Saw a wolf near the north farm", tick=12)
    world.environment.tick = 17
    world.environment.hour = 23
    ada.step(world, [ada], rng, llm_client=LLMClient(mode="mock"))
    assert "wolf" in ada.last_reflection.lower()
    assert any(m.text.startswith("Reflection:") for m in ada.memory.recent(5))

    # Live Ollama mode (mocked HTTP) for next day's plan & reflection
    class _FakeResp:
        def __init__(self, payload: dict[str, str]) -> None:
            self._data = json.dumps({"message": {"content": json.dumps(payload)}}).encode()
        def read(self) -> bytes:
            return self._data
        def __enter__(self) -> _FakeResp:
            return self
        def __exit__(self, *args: Any) -> None:
            return None

    responses = iter([
        _FakeResp({"plan": "Tend the south farm and share bread with neighbors."}),
        _FakeResp({"reflection": "Today's hard work kept the village well fed."}),
    ])
    live = LLMClient(mode="ollama", enable_cache=False, urlopen_fn=lambda *a, **k: next(responses))

    world.environment.day = 2
    world.environment.hour = 6
    assert ada.make_daily_plan(world, llm_client=live) == "Tend the south farm and share bread with neighbors."
    world.environment.hour = 23
    assert ada.write_reflection(world, llm_client=live) == "Today's hard work kept the village well fed."
    assert ada.detail()["last_reflection"] == "Today's hard work kept the village well fed."
