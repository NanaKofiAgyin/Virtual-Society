"""Core simulation engine: founding populations, reproduction, life cycle, and stats."""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from agents.animal import AnimalAgent, load_species, spawn_animals
from agents.base import Needs
from agents.culture import load_techs, step_society
from agents.ecosystem import Carcass, decompose_carcasses, pollination_multiplier
from agents.genome import random_genome
from agents.human import HumanAgent, Persona
from agents.lifecycle import (
    TICKS_PER_YEAR, DeathCause, FamilyTree, LifeStage,
    can_pair_humans, child_learn_from_adults, spawn_human_child,
)
from config import settings
from llm.client import LLMClient
from simulation.evolution import SpeciationEngine
from simulation.history import HistoryTracker
from simulation.lod import TIME_SCALE_HOURS, LODManager, TimeScale
from simulation.stats import SimulationStats
from simulation.storage import Storage
from world.environment import Environment
from world.map import WorldMap
from world.tile import TerrainType

FOUNDER_GIVEN = ("Ada", "Bram", "Clara", "Dorian", "Elena", "Finn", "Grace", "Hugo", "Iris", "Jonah",
                 "Kira", "Liam", "Mira", "Nolan", "Orla", "Piers", "Quinn", "Rosa", "Silas", "Talia")
FOUNDER_SURNAMES = ("Ash", "Brook", "Cedar", "Dale", "Elm", "Flint", "Grove", "Heath", "Moss", "Oak", "Reed", "Stone")
FOUNDER_JOBS = ("farmer", "farmer", "farmer", "woodcutter", "hunter", "builder", "healer", "teacher", "trader", "storyteller")
HUMAN_BREED_COOLDOWN = TICKS_PER_YEAR


class Simulation:
    """Owns world map, clock, founding humans & animals, reproduction, events, and stats."""

    def __init__(
        self, seed: int = 42, width: int = 50, height: int = 50,
        founding_humans: int | None = None, max_total_agents: int | None = None,
        llm_client: LLMClient | None = None, storage: Storage | None = None,
    ) -> None:
        self.seed, self.rng = seed, random.Random(seed)
        self.max_total_agents = max_total_agents or settings.max_total_agents
        n_founders = founding_humans if founding_humans is not None else settings.founding_humans
        self.world = WorldMap(width=width, height=height, seed=seed)
        self.world.place_village(n_houses=max(10, n_founders), n_farms=max(10, n_founders))
        self.llm_client = llm_client if llm_client is not None else LLMClient(mode="mock")
        self.storage, self.events, self.stats = storage, deque(maxlen=200), SimulationStats()
        self.species, self.techs, self.ever_discovered_techs = load_species(), load_techs(), set()
        self.humans: list[HumanAgent] = self._spawn_founders(n_founders)
        self.animals: list[AnimalAgent] = spawn_animals(self.world, self.species, self.rng)
        self.carcasses, self.history = [], HistoryTracker()
        self.evolution = SpeciationEngine(self.species, tick=0, storage=self.storage)
        self.lod = LODManager(cell_size=8)
        self.lod.seed_tier3_groups(self.world, self.species, self.rng)
        self._next_human_id, self._next_animal_id, self._last_year = len(self.humans), len(self.animals), self.environment.year

    @property
    def environment(self) -> Environment:
        return self.world.environment

    def _spawn_founders(self, count: int) -> list[HumanAgent]:
        import numpy as np
        from world.biomes import BIOMES_BY_NAME, BodyType

        houses = [(int(x), int(y)) for y, x in np.argwhere(self.world.biome_id == BIOMES_BY_NAME["house"].id)]
        homes = houses if len(houses) >= count else self.world.positions_for_body(BodyType.LAND)
        humans: list[HumanAgent] = []
        for idx in range(count):
            given, surname = FOUNDER_GIVEN[idx % len(FOUNDER_GIVEN)], FOUNDER_SURNAMES[idx % len(FOUNDER_SURNAMES)]
            full_name, job = f"{given} {surname}", FOUNDER_JOBS[idx % len(FOUNDER_JOBS)]
            age_years, home_pos, hid = self.rng.randint(18, 32), homes[idx % len(homes)], f"h_{idx + 1}"
            humans.append(HumanAgent(
                id=hid, name=full_name, position=home_pos, home=home_pos,
                persona=Persona(full_name, age_years, job, ("resilient", "curious"), "Help the village thrive"),
                needs=Needs(hunger=8.5, energy=8.5, social=8.0), inventory={"food": 4.0},
                genome=random_genome({"intelligence": 0.7, "sociability": 0.7}, rng=self.rng),
                family=FamilyTree(surname=surname, lineage_id=hid),
                skills={job: 3.0}, age_ticks=age_years * TICKS_PER_YEAR,
            ))
        return humans

    def _gen_human_id(self) -> str:
        self._next_human_id += 1
        return f"h_{self._next_human_id}"

    def _gen_animal_id(self) -> str:
        self._next_animal_id += 1
        return f"a_{self._next_animal_id}"

    def log_event(self, kind: str, message: str) -> None:
        tick = self.environment.tick
        self.events.append({"tick": tick, "kind": kind, "message": message})
        if self.storage is not None:
            self.storage.log_event(tick, kind, message)

    def converse(self, a: HumanAgent, b: HumanAgent) -> tuple[str, str]:
        la, lb = a.speak(b, self.world, self.llm_client, self.rng), b.speak(a, self.world, self.llm_client, self.rng)
        self.log_event("dialogue", f"{a.name} -> {b.name}: {la}")
        self.log_event("dialogue", f"{b.name} -> {a.name}: {lb}")
        return la, lb

    def population_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"humans": sum(1 for h in self.humans if h.alive), **{k: 0 for k in self.species}}
        for a in self.animals:
            if a.alive:
                counts[a.species] = counts.get(a.species, 0) + 1
        return counts

    def _total_live_agents(self) -> int:
        return sum(1 for h in self.humans if h.alive) + sum(1 for a in self.animals if a.alive)

    def _step_human_reproduction_and_learning(self) -> None:
        """Handle human pairing, births (under carrying capacity & budget), and child learning."""
        live = [h for h in self.humans if h.alive]
        by_id, newborns = {h.id: h for h in live}, []
        for h in live:
            if h.stage is LifeStage.CHILD:
                child_learn_from_adults(h, live, self.environment.tick)
                continue
            if h.stage is not LifeStage.ADULT:
                continue
            if h.family.partner is None:
                cands = [o for o in live if can_pair_humans(h, o)]
                if cands:
                    p = max(cands, key=lambda o: h.relationships.get(o.id, 0.0))
                    h.family.partner, p.family.partner = p.id, h.id
                    self.log_event("family", f"{h.name} and {p.name} formed a partnership")
            elif (
                h.breed_timer <= 0 and h.needs.hunger >= 5.5 and h.inventory.get("food", 0.0) >= 2.0
                and self._total_live_agents() + len(newborns) < self.max_total_agents
            ):
                p = by_id.get(h.family.partner)
                if p and p.alive and p.breed_timer <= 0 and p.needs.hunger >= 5.5 and self.rng.random() < 0.02:
                    h.remove_item("food", 1.5)
                    h.breed_timer = p.breed_timer = HUMAN_BREED_COOLDOWN
                    child = spawn_human_child(h, p, self.world, self.rng, self._gen_human_id())
                    newborns.append(child)
                    self.stats.record_birth("human")
                    self.log_event("birth", f"{child.name} was born to {h.name} & {p.name}")
        self.humans.extend(newborns)

    def _step_year_rollover(self, ev_name: str | None) -> None:
        if self.environment.year <= self._last_year:
            return
        self.stats.record_year(self._last_year, self.humans, self.animals)
        for ev in self.evolution.step_year(self.environment.tick, self.animals, self.species, self.world, self.storage):
            self.log_event(ev["kind"], ev["message"])
            self.history.observe_event(ev, self._last_year, self.stats.society["era"])
        warn = self.history.record_year_metrics(self._last_year, self.humans, self.animals, self.stats.society, ev_name)
        if warn:
            self.log_event("stagnation", f"Stagnation ({warn['quiet_years']}y): {warn['cause']}")
        self._last_year = self.environment.year

    def tick(self) -> dict[str, Any]:
        """Advance simulation according to `self.lod.time_scale` (normal/fast/geological)."""
        hours = TIME_SCALE_HOURS[self.lod.time_scale]
        self.environment.advance_time(hours)
        self.world.regrow(self.environment.regrow_multiplier() * pollination_multiplier(self.animals) * hours)
        self.lod.step_tier3(self.world, hours, self.rng)
        ev_name = self.environment.active_event.name if self.environment.active_event else None
        self.history.observe_environment(ev_name, self.environment.tick, self.environment.year, self.stats.society["era"])

        if self.lod.time_scale is TimeScale.GEOLOGICAL:
            self._step_year_rollover(ev_name)
            return {"tick": self.environment.tick, "counts": self.population_counts()}

        self.lod.spatial.rebuild([*self.humans, *self.animals])
        for human in self.humans:
            if not human.alive:
                continue
            action = human.step(self.world, self.lod.spatial.query_radius(human.x, human.y, 10), self.rng, self.llm_client)
            if not human.alive:
                cause = human.death_cause or DeathCause.STARVATION
                self.stats.record_death("human", cause)
                self.log_event("death", f"{human.name} died ({cause.value})")
            elif action == "talk" and human.last_speech:
                self.log_event("dialogue", f"{human.name}: {human.last_speech}")

        self._step_human_reproduction_and_learning()
        if self.environment.tick % 6 == 0 or hours >= 24:
            soc, soc_events = step_society(self.humans, self.techs, self.ever_discovered_techs, self.rng, self.environment.tick)
            self.stats.update_society(soc)
            self.lod.refresh_notables(self.humans, soc["settlements"])
            for ev in soc_events:
                self.log_event(ev["kind"], ev["message"])
                self.history.observe_event(ev, self.environment.year, soc["era"])

        live_total = self._total_live_agents()
        alive_before = {a.id for a in self.animals if a.alive}
        newborns: list[AnimalAgent] = []
        for a in self.animals:
            if not a.alive:
                continue
            child = a.step(
                self.world, self.lod.spatial.query_radius(a.x, a.y, 10), self.rng,
                can_reproduce=(live_total + len(newborns) < self.max_total_agents),
                next_id_fn=self._gen_animal_id, carcasses=self.carcasses,
            )
            if child is not None:
                newborns.append(child)
                self.stats.record_birth(a.species)

        for a in self.animals:
            if not a.alive and a.id in alive_before:
                self.stats.record_death(a.species, a.death_cause or DeathCause.STARVATION)
                self.carcasses.append(Carcass(a.x, a.y, a.species, a.config.energy_value if a.config else 25.0))
        has_decomp = any(a.alive and a.config and a.config.trophic_level == "decomposer" for a in self.animals)
        self.carcasses = decompose_carcasses(self.carcasses, self.world, has_decomposers=has_decomp)
        self.animals = [a for a in self.animals if a.alive] + newborns
        self._step_year_rollover(ev_name)
        if self.environment.hour == 0 or hours >= 24:
            pop = self.population_counts()
            animals = ", ".join(f"{k}={pop[k]}" for k in self.species if pop.get(k, 0) > 0)
            self.log_event("summary", f"Y{self.environment.year} {self.environment.season.value} D{self.environment.day}: humans={pop['humans']} | {animals}")
        return {"tick": self.environment.tick, "counts": self.population_counts()}

    def run(self, ticks: int) -> None:
        for _ in range(ticks):
            self.tick()

    def state(self) -> dict[str, Any]:
        return {
            "seed": self.seed, "environment": self.environment.to_dict(),
            "world": self.world.to_compact_dict(), "humans": [h.detail() for h in self.humans],
            "animals": [a.to_dict() for a in self.animals], "counts": self.population_counts(),
            "stats": self.stats.summary(), "events": list(self.events)[-30:],
            "llm_usage": self.llm_client.usage.summary(),
        }

    def summary(self) -> str:
        env, pop = self.environment, self.population_counts()
        animals = ", ".join(f"{k}: {pop[k]}" for k in self.species if pop.get(k, 0) > 0)
        return (
            f"Virtual Society (seed={self.seed}) Y{env.year} {env.season.value} D{env.day} "
            f"{env.hour:02d}:00 ({env.tick} ticks) | Weather: {env.weather.value}\n"
            f"Humans: {pop['humans']} | Animals: {animals}\n"
            f"Births: {self.stats.births_total} | Deaths: {dict(self.stats.deaths_by_cause)}"
        )

    def __getstate__(self) -> dict[str, Any]:
        return {**self.__dict__, "storage": None}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
