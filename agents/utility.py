"""Rule-based human priority brain and job execution (free, stdlib only)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from agents.animal import AnimalAgent
from world.environment import Weather
from world.tile import ResourceType, TerrainType, Tile

if TYPE_CHECKING:
    from agents.base import Agent
    from agents.human import HumanAgent
    from llm.client import LLMClient
    from world.map import WorldMap

HUNTER_MIN_BREEDING_STOCK = 4
SHELTER_WOOD_COST = 40.0
SOCIAL_JOBS = frozenset({"healer", "teacher", "trader", "storyteller"})


def _dist(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _nearest_wolf(human: HumanAgent, agents: list[Agent], radius: int = 4) -> AnimalAgent | None:
    wolves = [
        a for a in agents
        if a.alive and isinstance(a, AnimalAgent) and a.species == "wolf"
        and _dist(human.position, a.position) <= radius
    ]
    return min(wolves, key=lambda w: _dist(human.position, w.position)) if wolves else None


def _other_humans(human: HumanAgent, agents: list[Agent]) -> list[HumanAgent]:
    from agents.human import HumanAgent as HumanCls

    return [a for a in agents if a is not human and a.alive and isinstance(a, HumanCls)]


def _eat_or_forage(human: HumanAgent, world: WorldMap, rng: random.Random) -> str:
    if human.inventory.get("food", 0.0) >= 1.0:
        human.remove_item("food", 1.0)
        human.needs.adjust(hunger=5.0)
        human.health = min(10.0, human.health + 0.5)
        return "eat"
    tile = world.get_tile(human.x, human.y)
    if tile is not None and tile.get_resource(ResourceType.FOOD) >= 0.5:
        taken = tile.deplete(ResourceType.FOOD, 1.0)
        human.needs.adjust(hunger=taken * 5.0)
        return "eat"
    nearest = world.find_nearest(human.x, human.y, ResourceType.FOOD, min_amount=0.5)
    if nearest is not None and human.goto(world, (nearest.x, nearest.y)):
        return "seek_food"
    human.wander(world, rng)
    return "wander"


def _gather_resource(human: HumanAgent, world: WorldMap, res: ResourceType, rng: random.Random) -> str:
    tile = world.get_tile(human.x, human.y)
    if tile is not None and tile.get_resource(res) >= 0.5:
        taken = tile.deplete(res, 2.0)
        human.add_item(res.value, taken)
        return f"gather_{res.value}"
    nearest = world.find_nearest(human.x, human.y, res, min_amount=0.5)
    if nearest is not None and human.goto(world, (nearest.x, nearest.y)):
        return f"goto_{res.value}"
    human.wander(world, rng)
    return "wander"


def _do_hunter_job(human: HumanAgent, world: WorldMap, agents: list[Agent], rng: random.Random) -> str:
    prey_counts: dict[str, int] = {}
    prey_list: list[AnimalAgent] = []
    for a in agents:
        if a.alive and isinstance(a, AnimalAgent) and a.species in ("rabbit", "deer"):
            prey_counts[a.species] = prey_counts.get(a.species, 0) + 1
            prey_list.append(a)

    # Leave a breeding stock of every prey species
    huntable = [p for p in prey_list if prey_counts.get(p.species, 0) > HUNTER_MIN_BREEDING_STOCK]
    if not huntable:
        return _gather_resource(human, world, ResourceType.FOOD, rng)

    target = min(huntable, key=lambda p: _dist(human.position, p.position))
    if _dist(human.position, target.position) <= human.speed:
        if rng.random() < 0.35:
            target.alive = False
            human.add_item("food", 4.0)
            human.memory.add(f"Hunted a {target.species} for food", world.environment.tick)
            return "hunt_success"
        return "hunt_miss"
    human.goto(world, target.position)
    return "hunt_track"


def _do_builder_job(human: HumanAgent, world: WorldMap, rng: random.Random) -> str:
    if human.inventory.get("wood", 0.0) < SHELTER_WOOD_COST:
        return _gather_resource(human, world, ResourceType.WOOD, rng)
    tile = world.get_tile(human.x, human.y)
    if tile is not None and tile.terrain == TerrainType.GRASS:
        human.remove_item("wood", SHELTER_WOOD_COST)
        world.set_terrain(human.x, human.y, TerrainType.HOUSE)
        human.memory.add("Built a new shelter for the village", world.environment.tick, importance=6)
        return "build_shelter"
    grass = [t for t in world.get_nearby(human.x, human.y, radius=4) if t.terrain == TerrainType.GRASS]
    if grass:
        human.goto(world, (grass[0].x, grass[0].y))
        return "seek_build_site"
    human.wander(world, rng)
    return "wander"


def _do_social_job(
    human: HumanAgent,
    world: WorldMap,
    others: list[HumanAgent],
    llm_client: LLMClient | None,
    rng: random.Random,
) -> str:
    job = human.persona.job.lower()
    if job == "healer":
        injured = [o for o in others if o.health < 9.5]
        if injured:
            patient = min(injured, key=lambda o: _dist(human.position, o.position))
            if _dist(human.position, patient.position) <= 2:
                patient.health = min(10.0, patient.health + 2.0)
                human.adjust_affinity(patient.id, 1.0)
                patient.adjust_affinity(human.id, 1.5)
                human.memory.add(f"Healed {patient.name}", world.environment.tick, importance=5)
                return "heal"
            human.goto(world, patient.position)
            return "goto_patient"

    if others:
        partner = min(others, key=lambda o: _dist(human.position, o.position))
        if _dist(human.position, partner.position) <= 2:
            human.speak(partner, world, llm_client, rng)
            return f"work_{job}"
        human.goto(world, partner.position)
        return f"seek_{job}"
    human.wander(world, rng)
    return "wander"


def run_human_tick(
    human: HumanAgent,
    world: WorldMap,
    agents: list[Agent],
    rng: random.Random,
    llm_client: LLMClient | None = None,
) -> str:
    """Execute the 7-step rule-based priority brain for one hourly tick."""
    tick = world.environment.tick

    # 1) Flee wolves (unless already safely sheltered inside a house)
    cur_tile = world.get_tile(human.x, human.y)
    in_house = cur_tile is not None and cur_tile.terrain == TerrainType.HOUSE
    wolf = None if in_house else _nearest_wolf(human, agents)
    if wolf is not None:
        human.flee_from(world, wolf.position, rng)
        human.memory.add("Fled from a wolf nearby", tick)
        return "flee_wolf"

    # 2) Sleep at night or shelter in storms (go home); eat/forage if critically starving
    in_storm = world.environment.weather == Weather.STORM
    if world.environment.is_night or in_storm or human.needs.energy < 2.0:
        if human.needs.hunger < 1.5:
            return _eat_or_forage(human, world, rng)
        if human.position == human.home or in_house:
            human.needs.adjust(energy=2.5)
            human.health = min(10.0, human.health + 0.5)
            return "shelter" if in_storm else "sleep"
        if human.exhausted:
            human.needs.adjust(energy=2.0)
            return "rest"
        human.goto(world, human.home)
        return "go_home"

    # 3) Eat when hunger < 4 (or stock up a meal if carrying no food and getting hungry)
    if human.needs.hunger < 4.0:
        return _eat_or_forage(human, world, rng)
    if human.inventory.get("food", 0.0) < 1.0 and human.needs.hunger < 6.0:
        return _gather_resource(human, world, ResourceType.FOOD, rng)

    others = _other_humans(human, agents)
    nearby = [o for o in others if _dist(human.position, o.position) <= 2]

    # 4) Give food to a hungry neighbor
    if human.inventory.get("food", 0.0) >= 2.0:
        hungry = [
            o for o in others
            if _dist(human.position, o.position) <= 4
            and (o.needs.hunger < 5.5 or o.inventory.get("food", 0.0) < 1.0)
        ]
        if hungry:
            recipient = min(hungry, key=lambda o: o.needs.hunger)
            gift = 2.0 if human.inventory.get("food", 0.0) >= 4.0 else 1.0
            human.remove_item("food", gift)
            recipient.add_item("food", gift)
            human.adjust_affinity(recipient.id, 1.5)
            recipient.adjust_affinity(human.id, 2.0)
            human.memory.add(f"Gave food to {recipient.name}", tick)
            recipient.memory.add(f"{human.name} shared food with me", tick)
            return "give_food"

    # 5) Talk to someone nearby when social is low
    if human.needs.social < 5.0 and nearby:
        partner = min(nearby, key=lambda o: _dist(human.position, o.position))
        human.speak(partner, world, llm_client, rng)
        return "talk"

    # 6) Seek company when social is low
    if human.needs.social < 5.0 and others:
        target = min(others, key=lambda o: _dist(human.position, o.position))
        if human.goto(world, target.position):
            return "seek_company"

    # 7) Do the job
    job = human.persona.job.lower()
    if job == "farmer":
        return _gather_resource(human, world, ResourceType.FOOD, rng)
    if job == "woodcutter":
        return _gather_resource(human, world, ResourceType.WOOD, rng)
    if job == "hunter":
        return _do_hunter_job(human, world, agents, rng)
    if job == "builder":
        return _do_builder_job(human, world, rng)
    if job in SOCIAL_JOBS:
        return _do_social_job(human, world, others, llm_client, rng)

    human.wander(world, rng)
    return "wander"
