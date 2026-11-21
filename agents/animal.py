"""Rule-based animal agents configured from `data/species.json`."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents.base import Action, ActionType, Agent, Needs
from world.tile import ResourceType

if TYPE_CHECKING:
    from world.map import WorldMap

DEFAULT_SPECIES_PATH = Path(__file__).resolve().parent.parent / "data" / "species.json"
KILL_SUCCESS_RATE = 0.25


@dataclass(frozen=True)
class SpeciesConfig:
    """Configuration parameters for a single animal species."""

    name: str
    diet: str
    speed: int
    max_age: int
    hunger_rate: float
    fears: tuple[str, ...]
    prey: tuple[str, ...]
    flies: bool
    max_pop: int
    initial: int
    breed_cooldown: int
    breed_chance: float


def load_species(path: Path | str = DEFAULT_SPECIES_PATH) -> dict[str, SpeciesConfig]:
    """Load species configurations from JSON into typed `SpeciesConfig` objects."""
    raw: dict[str, dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: SpeciesConfig(
            name=name, diet=str(c["diet"]), speed=int(c["speed"]),
            max_age=int(c["max_age"]), hunger_rate=float(c["hunger_rate"]),
            fears=tuple(c["fears"]), prey=tuple(c["prey"]), flies=bool(c["flies"]),
            max_pop=int(c["max_pop"]), initial=int(c["initial"]),
            breed_cooldown=int(c["breed_cooldown"]), breed_chance=float(c["breed_chance"]),
        )
        for name, c in raw.items()
    }


def _agent_kind(agent: Agent) -> str:
    """Return species name for animals or 'human' for humans."""
    return agent.species if isinstance(agent, AnimalAgent) else "human"


@dataclass
class AnimalAgent(Agent):
    """Lightweight rule-based animal agent with zero LLM calls."""

    species: str = "deer"
    config: SpeciesConfig | None = None
    age: int = 0
    breed_timer: int = 0
    vision_radius: int = 5
    available_actions: list[ActionType] = field(
        default_factory=lambda: [ActionType.MOVE, ActionType.EAT, ActionType.SLEEP, ActionType.GATHER]
    )

    def __post_init__(self) -> None:
        if self.config is not None:
            self.species = self.config.name
            self.speed = self.config.speed
            self.flies = self.config.flies
            self.hunger_decay = self.config.hunger_rate

    def decide(self, world: WorldMap, nearby_agents: list[Agent]) -> Action:
        """Choose the next action using simple rules (placeholder)."""
        if self.exhausted:
            return Action(type=ActionType.SLEEP)
        return Action(type=ActionType.MOVE)
        """Return the high-level action type this animal intends to take."""
        if self.config is not None and self._find_threat(nearby_agents) is not None:
            return Action(type=ActionType.MOVE, params={"intent": "flee"})
        if self.needs.hunger < 6.0:
            return Action(type=ActionType.EAT)
        return Action(type=ActionType.MOVE, params={"intent": "wander"})

    def _find_threat(self, agents: list[Agent]) -> Agent | None:
        """Find the nearest alive feared agent within vision radius."""
        if self.config is None or not self.config.fears:
            return None
        threats = [
            (abs(o.x - self.x) + abs(o.y - self.y), o)
            for o in agents
            if o is not self and o.alive and _agent_kind(o) in self.config.fears
        ]
        in_range = [pair for pair in threats if pair[0] <= self.vision_radius]
        return min(in_range, key=lambda pair: pair[0])[1] if in_range else None

    def _find_prey(self, agents: list[Agent]) -> AnimalAgent | None:
        """Find the nearest alive prey animal."""
        if self.config is None or not self.config.prey:
            return None
        candidates = [
            (abs(o.x - self.x) + abs(o.y - self.y), o)
            for o in agents
            if o is not self and o.alive and isinstance(o, AnimalAgent) and o.species in self.config.prey
        ]
        return min(candidates, key=lambda pair: pair[0])[1] if candidates else None

    def _step_toward(self, world: WorldMap, target: tuple[int, int]) -> bool:
        """Take greedy walkable steps toward `target` (fast fallback for long distances)."""
        tx, ty = target
        moved = False
        for _ in range(max(1, self.speed)):
            neighbors = self._valid_neighbors(world)
            if not neighbors:
                break
            best = min(neighbors, key=lambda p: (abs(p[0] - tx) + abs(p[1] - ty), p[1], p[0]))
            if abs(best[0] - tx) + abs(best[1] - ty) >= abs(self.x - tx) + abs(self.y - ty):
                break
            self.position = best
            moved = True
        return moved

    def _forage(self, world: WorldMap, rng: random.Random) -> None:
        """Eat food on current tile or move toward nearby food."""
        tile = world.get_tile(self.x, self.y)
        if tile is not None and tile.get_resource(ResourceType.FOOD) >= 0.2:
            taken = tile.deplete(ResourceType.FOOD, 1.5)
            self.needs.adjust(hunger=taken * 4.5)
            return
        nearby = [
            t for t in world.get_nearby(self.x, self.y, radius=self.vision_radius)
            if (self.flies or t.walkable) and t.get_resource(ResourceType.FOOD) >= 0.2
        ]
        if nearby:
            target = min(nearby, key=lambda t: (abs(t.x - self.x) + abs(t.y - self.y), t.y, t.x))
            if not self.goto(world, (target.x, target.y)):
                self.wander(world, rng)
        else:
            self.wander(world, rng)

    def _hunt(
        self,
        world: WorldMap,
        agents: list[Agent],
        rng: random.Random,
        species_counts: dict[str, int],
    ) -> None:
        """Chase nearest prey and attempt a 25% kill when in range."""
        prey = self._find_prey(agents)
        if prey is None:
            self.wander(world, rng)
            return
        dist = abs(prey.x - self.x) + abs(prey.y - self.y)
        if dist <= self.speed:
            self.position = prey.position
            if rng.random() < KILL_SUCCESS_RATE:
                prey.alive = False
                species_counts[prey.species] = max(0, species_counts.get(prey.species, 1) - 1)
                self.needs.adjust(hunger=7.5)
            else:
                prey.flee_from(world, self.position, rng)
        elif dist <= 10:
            if not self.goto(world, prey.position):
                self.wander(world, rng)
        elif not self._step_toward(world, prey.position):
            self.wander(world, rng)

    def step(
        self,
        world: WorldMap,
        agents: list[Agent],
        rng: random.Random,
        species_counts: dict[str, int],
        next_id_fn: Any = None,
    ) -> AnimalAgent | None:
        """Run one hourly tick for this animal; returns a newborn if it reproduced."""
        if not self.alive or self.config is None:
            return None
        self.age += 1
        self.breed_timer = max(0, self.breed_timer - 1)
        self.needs.adjust(hunger=-self.config.hunger_rate)
        if self.age >= self.config.max_age or self.needs.hunger <= 0.0:
            self.alive = False
            self.starving = self.needs.hunger <= 0.0
            species_counts[self.species] = max(0, species_counts.get(self.species, 1) - 1)
            return None

        threat = self._find_threat(agents)
        if threat is not None:
            self.flee_from(world, threat.position, rng)
        elif self.config.diet == "carnivore" and self.needs.hunger < 6.5:
            self._hunt(world, agents, rng, species_counts)
        elif self.config.diet == "herbivore" and self.needs.hunger < 7.0:
            self._forage(world, rng)
        else:
            self.wander(world, rng)

        if (
            self.alive
            and self.needs.hunger >= 5.0
            and self.breed_timer <= 0
            and species_counts.get(self.species, 0) < self.config.max_pop
            and rng.random() < self.config.breed_chance
        ):
            self.breed_timer = self.config.breed_cooldown
            self.needs.adjust(hunger=-1.0)
            species_counts[self.species] = species_counts.get(self.species, 0) + 1
            cid = next_id_fn() if next_id_fn else f"{self.species}_{rng.randrange(10**9)}"
            return AnimalAgent(
                id=cid,
                name=f"{self.species.capitalize()}-{cid.split('_')[-1]}",
                position=self.position,
                needs=Needs(hunger=7.0, energy=8.0, social=8.0),
                species=self.species,
                config=self.config,
                breed_timer=self.config.breed_cooldown,
            )
        return None


def spawn_animals(
    world: WorldMap,
    species_map: dict[str, SpeciesConfig],
    rng: random.Random,
) -> list[AnimalAgent]:
    """Spawn initial populations for all configured species on valid tiles."""
    walkable = [t for row in world.tiles for t in row if t.walkable]
    all_tiles = [t for row in world.tiles for t in row]
    animals: list[AnimalAgent] = []
    counter = 0
    for name, cfg in species_map.items():
        pool = all_tiles if cfg.flies else walkable
        for _ in range(cfg.initial):
            counter += 1
            tile = rng.choice(pool)
            animals.append(AnimalAgent(
                id=f"{name}_{counter}", name=f"{name.capitalize()}-{counter}",
                position=(tile.x, tile.y),
                needs=Needs(hunger=rng.uniform(6.5, 9.5), energy=8.0, social=8.0),
                species=name, config=cfg,
                age=rng.randrange(0, max(1, cfg.max_age // 3)),
                breed_timer=rng.randrange(0, max(1, cfg.breed_cooldown)),
            ))
    return animals
