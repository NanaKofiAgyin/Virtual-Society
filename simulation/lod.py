"""Level-of-Detail (Tier 1/2/3) simulation, variable time scales, and performance report."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from agents.animal import AnimalAgent
from agents.base import Needs
from agents.genome import mutate, random_genome
from simulation.spatial import SpatialHashGrid
from world.biomes import BodyType

if TYPE_CHECKING:
    from agents.base import Agent
    from agents.ecosystem import SpeciesConfig
    from agents.human import HumanAgent
    from simulation.engine import Simulation
    from world.map import WorldMap

TIER3_SPECIES = frozenset({"zooplankton", "krill", "insects", "small_fish", "bacteria", "fungi", "worm"})


class TimeScale(str, Enum):
    """Variable simulation time scales."""

    NORMAL = "normal"          # 1 tick = 1 hour
    FAST = "fast"              # 1 tick = 1 day (24 hours)
    GEOLOGICAL = "geological"  # 1 tick = 1 season (168 hours), group stats only


TIME_SCALE_HOURS: dict[TimeScale, int] = {
    TimeScale.NORMAL: 1,
    TimeScale.FAST: 24,
    TimeScale.GEOLOGICAL: 24 * 7,
}


class LODTier(int, Enum):
    """Three simulation fidelity tiers."""

    TIER_1 = 1  # Notable humans (leaders, discoverers, famous) & rare animals
    TIER_2 = 2  # Ordinary individual animals & humans (cheap rule-based)
    TIER_3 = 3  # Microscopic/huge populations simulated as groups per tile


@dataclass
class PopulationGroup:
    """Tier 3 group simulated via logistic birth/death rates until materialized."""

    species: str
    x: int
    y: int
    count: float
    birth_rate: float = 0.04
    death_rate: float = 0.015
    carrying_capacity: float = 500.0
    mean_genome: dict[str, float] = field(default_factory=dict)

    def step(self, hours: int, regrow_mult: float, rng: random.Random) -> None:
        """Update group size using discrete logistic growth over `hours`."""
        if self.count <= 0.0:
            self.count = 0.0
            return
        dt = max(1, hours) / 24.0
        k = max(1.0, self.carrying_capacity * max(0.2, regrow_mult))
        growth = self.birth_rate * regrow_mult * (1.0 - self.count / k) - self.death_rate
        noise = rng.gauss(0.0, 0.01)
        self.count = max(0.0, self.count * (1.0 + (growth + noise) * dt))

    def materialize(
        self, n: int, species_map: dict[str, SpeciesConfig], rng: random.Random, next_id_fn: Any,
    ) -> list[AnimalAgent]:
        """Convert up to `n` members into concrete `AnimalAgent` individuals."""
        cfg = species_map.get(self.species)
        take = min(int(self.count), max(0, n))
        if cfg is None or take <= 0:
            return []
        self.count -= take
        spawned: list[AnimalAgent] = []
        for _ in range(take):
            aid = next_id_fn()
            g = mutate(self.mean_genome or random_genome(cfg.genome_template, rng=rng), rate=0.1, rng=rng)
            spawned.append(AnimalAgent(
                id=aid, name=f"{self.species.capitalize()}-{aid.split('_')[-1]}",
                position=(self.x, self.y), needs=Needs(7.5, 8.0, 8.0),
                species=self.species, config=cfg, genome=g, lineage_id=aid,
                age=rng.randrange(int(cfg.max_age * 0.2), int(cfg.max_age * 0.5)),
            ))
        return spawned


def classify_tier(agent: Agent, notable_ids: set[str], species_counts: dict[str, int]) -> LODTier:
    """Assign Tier 1 to notable humans / rare animals, otherwise Tier 2."""
    if agent.id in notable_ids:
        return LODTier.TIER_1
    if isinstance(agent, AnimalAgent) and species_counts.get(agent.species, 0) <= 4:
        return LODTier.TIER_1
    return LODTier.TIER_2


class LODManager:
    """Coordinates spatial hashing, Tier 1/2/3 updates, variable time scales, and perf reports."""

    def __init__(self, cell_size: int = 8) -> None:
        self.spatial = SpatialHashGrid(cell_size=cell_size)
        self.groups: list[PopulationGroup] = []
        self.time_scale: TimeScale = TimeScale.NORMAL
        self.notable_ids: set[str] = set()
        self.camera_rect: tuple[int, int, int, int] | None = None

    def seed_tier3_groups(
        self, world: WorldMap, species_map: dict[str, SpeciesConfig], rng: random.Random,
    ) -> None:
        """Seed Tier 3 background population groups for microscopic and schooling species."""
        pools = {bt: world.positions_for_body(bt) for bt in BodyType}
        for name in sorted(TIER3_SPECIES):
            cfg = species_map.get(name)
            if cfg is None:
                continue
            pool = pools.get(BodyType(cfg.body_type)) or pools[BodyType.FLYING]
            if not pool:
                continue
            for _ in range(3):
                x, y = rng.choice(pool)
                self.groups.append(PopulationGroup(
                    species=name, x=x, y=y, count=float(rng.randint(80, 250)),
                    carrying_capacity=600.0,
                    mean_genome=random_genome(cfg.genome_template, rng=rng),
                ))

    def refresh_notables(self, humans: list[HumanAgent], settlements: list[dict[str, Any]]) -> None:
        """Mark settlement leaders, tech discoverers, and high-affinity humans as Tier 1."""
        notables = {s["leader_id"] for s in settlements if s.get("leader_id")}
        for h in humans:
            if not h.alive:
                continue
            if h.culture.known_techs or sum(1 for v in h.relationships.values() if v >= 5.0) >= 3:
                notables.add(h.id)
        self.notable_ids = notables

    def step_tier3(self, world: WorldMap, hours: int, rng: random.Random) -> None:
        """Advance all Tier 3 population groups by `hours`."""
        mult = world.environment.regrow_multiplier()
        for g in self.groups:
            g.step(hours, mult, rng)
        self.groups = [g for g in self.groups if g.count >= 1.0]

    def materialize_near(
        self, x: int, y: int, radius: int, species_map: dict[str, SpeciesConfig],
        rng: random.Random, next_id_fn: Any, max_new: int = 4,
    ) -> list[AnimalAgent]:
        """Materialize individuals from any Tier 3 group near `(x, y)` (camera or interaction)."""
        spawned: list[AnimalAgent] = []
        for g in self.groups:
            if len(spawned) >= max_new:
                break
            if abs(g.x - x) <= radius and abs(g.y - y) <= radius and g.count >= 1.0:
                spawned.extend(g.materialize(max_new - len(spawned), species_map, rng, next_id_fn))
        return spawned

    def tier_counts(self, humans: list[HumanAgent], animals: list[AnimalAgent]) -> dict[str, int]:
        """Count live agents in Tier 1, Tier 2, and Tier 3 (groups & total individuals)."""
        sp_counts: dict[str, int] = {}
        for a in animals:
            if a.alive:
                sp_counts[a.species] = sp_counts.get(a.species, 0) + 1
        t1, t2 = 0, 0
        for ag in (*humans, *animals):
            if not ag.alive:
                continue
            if classify_tier(ag, self.notable_ids, sp_counts) is LODTier.TIER_1:
                t1 += 1
            else:
                t2 += 1
        t3_pop = int(sum(g.count for g in self.groups))
        return {"tier_1": t1, "tier_2": t2, "tier_3_groups": len(self.groups), "tier_3_pop": t3_pop}

    def format_performance_report(
        self, ticks: int, elapsed_sec: float, humans: list[HumanAgent], animals: list[AnimalAgent],
    ) -> str:
        """Return a readable performance report with ticks/sec and counts per LOD tier."""
        tps = ticks / max(1e-6, elapsed_sec)
        c = self.tier_counts(humans, animals)
        return (
            f"Performance Report ({self.time_scale.value} scale): {tps:.1f} ticks/sec "
            f"({ticks} ticks in {elapsed_sec:.2f}s) | "
            f"Tier 1: {c['tier_1']} | Tier 2: {c['tier_2']} | "
            f"Tier 3: {c['tier_3_groups']} groups ({c['tier_3_pop']} individuals)"
        )
