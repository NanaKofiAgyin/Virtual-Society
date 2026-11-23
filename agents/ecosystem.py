"""Trophic food web mechanics: 10% energy flow, carcasses, pollination, co-evolution, migration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from world.environment import Season

if TYPE_CHECKING:
    from agents.animal import AnimalAgent
    from world.map import WorldMap

DEFAULT_SPECIES_PATH = Path(__file__).resolve().parent.parent / "data" / "species.json"
TROPHIC_TRANSFER_EFFICIENCY = 0.10  # ~10% energy passes up each trophic level
CARCASS_DECAY_TICKS = 48


@dataclass(frozen=True)
class SpeciesConfig:
    """Data-driven trophic species configuration loaded from `data/species.json`."""

    name: str
    trophic_level: str
    habitat: str
    body_type: str
    diet: str
    speed: int
    max_age: int
    litter_size: tuple[int, int]
    hunger_rate: float
    energy_value: float
    migrates: bool
    fears: tuple[str, ...]
    prey: tuple[str, ...]
    eaten_by: tuple[str, ...]
    flies: bool
    parental_care: bool
    founding_min: int
    founding_max: int
    breed_cooldown: int
    breed_chance: float
    genome_ranges: dict[str, tuple[float, float]]
    simulation_tier: str = "individual"
    density_k: float = 0.0
    growth_rate: float = 0.0
    home_range: int = 8
    social: bool = False
    specialist: bool = False

    @property
    def is_density_tier(self) -> bool:
        return self.simulation_tier == "density"

    @property
    def genome_template(self) -> dict[str, float]:
        return {k: (lo + hi) / 2.0 for k, (lo, hi) in self.genome_ranges.items()}


def load_species(path: Path | str = DEFAULT_SPECIES_PATH) -> dict[str, SpeciesConfig]:
    """Load species configurations from JSON into typed `SpeciesConfig` objects."""
    raw: dict[str, dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, SpeciesConfig] = {}
    for name, c in raw.items():
        bt = str(c.get("body_type", "flying" if c.get("flies") else "land"))
        lit = c.get("litter_size", [1, 1])
        ranges = {k: (float(v[0]), float(v[1])) for k, v in c.get("genome_ranges", {}).items()}
        out[name] = SpeciesConfig(
            name=name, trophic_level=str(c.get("trophic_level", "primary_consumer")),
            habitat=str(c.get("habitat", "land")), body_type=bt, diet=str(c["diet"]),
            speed=int(c["speed"]), max_age=int(c.get("lifespan", c.get("max_age", 1500))),
            litter_size=(int(lit[0]), int(lit[1])), hunger_rate=float(c["hunger_rate"]),
            energy_value=float(c.get("energy_value", 30.0)), migrates=bool(c.get("migrates", False)),
            fears=tuple(c.get("fears", ())), prey=tuple(c.get("prey", ())),
            eaten_by=tuple(c.get("eaten_by", ())), flies=(bt == "flying"),
            parental_care=bool(c.get("parental_care", False)),
            founding_min=int(c.get("founding_min", 0)), founding_max=int(c.get("founding_max", 0)),
            breed_cooldown=int(c.get("breed_cooldown", 96)), breed_chance=float(c.get("breed_chance", 0.2)),
            genome_ranges=ranges,
            simulation_tier=str(c.get("simulation_tier", "individual")),
            density_k=float(c.get("density_k", 0.0)),
            growth_rate=float(c.get("growth_rate", 0.0)),
            home_range=int(c.get("home_range", 8)),
            social=bool(c.get("social", False)),
            specialist=bool(c.get("specialist", False)),
        )
    return out


@dataclass
class Carcass:
    """Remains of a dead animal consumed by scavengers and decomposed into soil nutrients."""

    x: int
    y: int
    species: str
    energy: float
    age: int = 0


def trophic_energy_gain(prey_energy_value: float) -> float:
    """Return predator energy gained from eating prey (~10% trophic transfer efficiency)."""
    return max(0.4, round(prey_energy_value * TROPHIC_TRANSFER_EFFICIENCY, 3))


def predator_prey_capture_prob(predator: AnimalAgent, prey: AnimalAgent) -> float:
    """Compute capture probability from predator vs prey genes (drives co-evolution).

    Prey speed, camouflage, and vision lower capture chance; predator speed,
    vision, and combat strength raise it.
    """
    pg = predator.genome
    qg = prey.genome
    pred_score = 0.45 * pg.get("speed", 0.5) + 0.35 * pg.get("vision", 0.5) + 0.20 * pg.get("size", 0.5)
    prey_score = 0.40 * qg.get("speed", 0.5) + 0.35 * qg.get("camouflage", 0.5) + 0.25 * qg.get("vision", 0.5)
    prob = 0.25 + 0.45 * (pred_score - prey_score)
    return max(0.05, min(0.75, round(prob, 4)))


def inbreeding_depression_factor(pop_size: int, genetic_diversity: float) -> float:
    """Return survival/fertility multiplier [0.35, 1.0]; drops when pop & diversity are low."""
    if pop_size >= 30 or genetic_diversity >= 0.10:
        return 1.0
    pop_deficit = max(0.0, (30.0 - pop_size) / 30.0)
    div_deficit = max(0.0, (0.10 - genetic_diversity) / 0.10)
    penalty = 0.65 * pop_deficit * (0.35 + 0.65 * div_deficit)
    return round(max(0.35, 1.0 - penalty), 4)


def allee_effect_factor(local_count: int, social: bool, threshold: int = 8) -> float:
    """Return reproductive/foraging multiplier [0.25, 1.0] for social species below pack/herd size."""
    if not social or local_count >= threshold:
        return 1.0
    if local_count <= 1:
        return 0.25
    ratio = local_count / float(max(1, threshold))
    return round(0.25 + 0.75 * ratio, 4)


def pollination_multiplier(
    animals: list[AnimalAgent], baseline_pollinators: int = 8, density_grid: Any = None,
) -> float:
    """Compute plant regrowth multiplier based on active individual + density-tier pollinators.

    With zero pollinators, only wind-pollinated regrowth (0.25x) remains; healthy
    pollinator populations boost plant reproduction up to 1.35x.
    """
    n_poll = sum(
        1 for a in animals
        if a.alive and a.config is not None and a.config.trophic_level == "pollinator"
    )
    if density_grid is not None:
        n_poll += int(density_grid.pollinator_index() * baseline_pollinators)
    if n_poll <= 0:
        return 0.25
    ratio = min(1.5, n_poll / max(1, baseline_pollinators))
    return round(0.35 + 0.67 * ratio, 3)


def decompose_carcasses(carcasses: list[Carcass], world: WorldMap, has_decomposers: bool = True) -> list[Carcass]:
    """Age carcasses, return nutrients to soil food layer, and drop fully decomposed ones."""
    remaining: list[Carcass] = []
    rate = 0.12 if has_decomposers else 0.03
    for c in carcasses:
        c.age += 1
        released = min(c.energy, max(0.2, c.energy * rate))
        c.energy -= released
        if world.in_bounds(c.x, c.y):
            nutrients = released * 0.08
            world.food[c.y, c.x] = min(
                float(world.food_max[c.y, c.x]) + 1.0,
                float(world.food[c.y, c.x]) + nutrients,
            )
        if c.energy > 0.1 and c.age < CARCASS_DECAY_TICKS:
            remaining.append(c)
    return remaining


def migration_target(animal: AnimalAgent, world: WorldMap) -> tuple[int, int] | None:
    """Return a seasonal migration target for migratory herds, birds, and whales."""
    if animal.config is None or not animal.config.migrates:
        return None
    season = world.environment.season
    equator_y = world.height // 2
    if season in (Season.AUTUMN, Season.WINTER):
        target_y = equator_y
    else:
        # Move poleward in spring/summer toward rich seasonal feeding grounds
        target_y = max(2, world.height // 5) if animal.y <= equator_y else min(world.height - 3, (world.height * 4) // 5)
    if abs(animal.y - target_y) <= 2:
        return None
    step_y = animal.y + (1 if target_y > animal.y else -1)
    if world.can_enter(animal.x, step_y, animal.effective_body_type):
        return (animal.x, step_y)
    return None
