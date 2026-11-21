"""Core simulation engine: 1-tick = 1-hour loop for 10 humans, animals, and world."""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from agents.animal import AnimalAgent, load_species, spawn_animals
from agents.base import Needs
from agents.human import HumanAgent, Persona
from llm.client import LLMClient
from simulation.storage import Storage
from world.environment import Environment
from world.map import WorldMap
from world.tile import TerrainType

DEFAULT_PERSONAS: tuple[Persona, ...] = (
    Persona("Ada", 29, "farmer", ("patient", "generous"), "Keep everyone fed"),
    Persona("Bram", 34, "farmer", ("steady", "practical"), "Grow abundant harvests"),
    Persona("Clara", 24, "farmer", ("cheerful", "curious"), "Learn every crop"),
    Persona("Dorian", 38, "woodcutter", ("strong", "quiet"), "Stockpile timber for winter"),
    Persona("Elena", 31, "hunter", ("sharp", "respectful"), "Hunt sustainably"),
    Persona("Finn", 41, "builder", ("methodical", "proud"), "Build sturdy shelters"),
    Persona("Grace", 36, "healer", ("compassionate", "calm"), "Care for the injured"),
    Persona("Hugo", 45, "teacher", ("wise", "kind"), "Share knowledge with villagers"),
    Persona("Iris", 27, "trader", ("clever", "sociable"), "Keep goods flowing"),
    Persona("Jonah", 52, "storyteller", ("warm", "imaginative"), "Keep village spirits high"),
)


class Simulation:
    """Owns the world map, clock, 10 humans, animals, event log, and optional SQLite storage."""

    def __init__(
        self,
        seed: int = 42,
        width: int = 50,
        height: int = 50,
        llm_client: LLMClient | None = None,
        storage: Storage | None = None,
    ) -> None:
        """Initialize a reproducible world with a central village, 10 humans, and wildlife."""
        self.seed = seed
        self.rng = random.Random(seed)
        self.world = WorldMap(width=width, height=height, seed=seed)
        self.world.place_village(n_houses=10, n_farms=10)
        self.llm_client = llm_client if llm_client is not None else LLMClient(mode="mock")
        self.storage = storage
        self.events: deque[dict[str, Any]] = deque(maxlen=200)

        self.species = load_species()
        self.humans: list[HumanAgent] = self._spawn_humans()
        self.animals: list[AnimalAgent] = spawn_animals(self.world, self.species, self.rng)
        self._next_animal_id = len(self.animals)

    @property
    def environment(self) -> Environment:
        """Expose the world's Environment clock/season/weather controller."""
        return self.world.environment

    def _spawn_humans(self) -> list[HumanAgent]:
        """Spawn the 10 distinct personas at village houses with starter food."""
        houses = [t for row in self.world.tiles for t in row if t.terrain == TerrainType.HOUSE]
        walkable = [t for row in self.world.tiles for t in row if t.walkable]
        homes = houses if len(houses) >= len(DEFAULT_PERSONAS) else walkable

        humans: list[HumanAgent] = []
        for idx, persona in enumerate(DEFAULT_PERSONAS):
            home_tile = homes[idx % len(homes)]
            humans.append(
                HumanAgent(
                    id=f"h_{idx + 1}",
                    name=persona.name,
                    position=(home_tile.x, home_tile.y),
                    home=(home_tile.x, home_tile.y),
                    persona=persona,
                    needs=Needs(hunger=8.5, energy=8.5, social=8.0),
                    inventory={"food": 4.0},
                )
            )
        return humans

    def _gen_animal_id(self) -> str:
        self._next_animal_id += 1
        return f"a_{self._next_animal_id}"

    def log_event(self, kind: str, message: str) -> None:
        """Append an event to the in-memory deque and optional SQLite storage."""
        tick = self.environment.tick
        entry = {"tick": tick, "kind": kind, "message": message}
        self.events.append(entry)
        if self.storage is not None:
            self.storage.log_event(tick, kind, message)

    def converse(self, a: HumanAgent, b: HumanAgent) -> tuple[str, str]:
        """Exchange one line each between two humans, updating needs, affinity, and logs."""
        line_a = a.speak(b, self.world, self.llm_client, self.rng)
        line_b = b.speak(a, self.world, self.llm_client, self.rng)
        self.log_event("dialogue", f"{a.name} -> {b.name}: {line_a}")
        self.log_event("dialogue", f"{b.name} -> {a.name}: {line_b}")
        return line_a, line_b

    def population_counts(self) -> dict[str, int]:
        """Return live counts of humans and each animal species."""
        counts: dict[str, int] = {
            "humans": sum(1 for h in self.humans if h.alive),
            **{name: 0 for name in self.species},
        }
        for animal in self.animals:
            if animal.alive:
                counts[animal.species] = counts.get(animal.species, 0) + 1
        return counts

    def tick(self) -> dict[str, Any]:
        """Advance the simulation by 1 hour: clock, regrowth, humans, animals, midnight log."""
        self.world.advance_time(1)
        all_agents = [*self.humans, *self.animals]

        for human in self.humans:
            if not human.alive:
                continue
            was_alive = human.alive
            human.step(self.world, all_agents, self.rng, llm_client=self.llm_client)
            if was_alive and not human.alive:
                self.log_event("death", f"{human.name} ({human.persona.job}) died")

        counts = {name: 0 for name in self.species}
        for animal in self.animals:
            if animal.alive:
                counts[animal.species] += 1

        newborns: list[AnimalAgent] = []
        for animal in self.animals:
            if not animal.alive:
                continue
            child = animal.step(
                self.world, all_agents, self.rng, counts, next_id_fn=self._gen_animal_id
            )
            if child is not None:
                newborns.append(child)

        self.animals = [a for a in self.animals if a.alive] + newborns

        if self.environment.hour == 0:
            pop = self.population_counts()
            animal_str = ", ".join(f"{k}={pop[k]}" for k in self.species)
            msg = (
                f"Year {self.environment.year} {self.environment.season.value.capitalize()} "
                f"Day {self.environment.day}: humans={pop['humans']}/{len(self.humans)} | {animal_str}"
            )
            self.log_event("summary", msg)

        return {"tick": self.environment.tick, "counts": self.population_counts()}

    def run(self, ticks: int) -> None:
        """Advance the simulation by `ticks` hours."""
        for _ in range(ticks):
            self.tick()

    def state(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot of the entire simulation for the viewer."""
        return {
            "seed": self.seed,
            "environment": self.environment.to_dict(),
            "world": {
                "width": self.world.width,
                "height": self.world.height,
                "tiles": [[t.to_dict() for t in row] for row in self.world.tiles],
            },
            "humans": [h.detail() for h in self.humans],
            "animals": [a.to_dict() for a in self.animals],
            "counts": self.population_counts(),
            "events": list(self.events)[-30:],
            "llm_usage": self.llm_client.usage.summary(),
        }

    def summary(self) -> str:
        """Return a concise text summary for headless CLI runs."""
        env = self.environment
        pop = self.population_counts()
        animal_str = ", ".join(f"{k}: {pop[k]}" for k in self.species)
        return (
            f"Virtual Society Summary (seed={self.seed})\n"
            f"Time: Year {env.year}, {env.season.value.capitalize()} Day {env.day}, "
            f"{env.hour:02d}:00 ({env.tick} ticks) | Weather: {env.weather.value}\n"
            f"Humans alive: {pop['humans']}/{len(self.humans)}\n"
            f"Animals: {animal_str}\n"
            f"Events logged: {len(self.events)} | LLM calls: {self.llm_client.usage.total_calls}"
        )

    def __getstate__(self) -> dict[str, Any]:
        """Exclude the live SQLite Storage connection when pickling."""
        state = self.__dict__.copy()
        state["storage"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore pickled simulation state."""
        self.__dict__.update(state)
