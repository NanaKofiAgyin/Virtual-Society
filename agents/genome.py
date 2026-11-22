"""Genome representation, reproduction operators, and phenotypic trade-offs.

Every living thing (animals, humans, plants) carries a dict of numeric genes in
[0.0, 1.0]. Fitness is never computed directly; it emerges from survival and
reproduction under real metabolic, combat, lifespan, and environmental costs.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping

GENES: tuple[str, ...] = (
    "size",
    "metabolism",
    "speed",
    "vision",
    "fertility",
    "lifespan",
    "aggression",
    "sociability",
    "intelligence",
    "endurance",
    "cold_tolerance",
    "heat_tolerance",
    "disease_resistance",
    "camouflage",
    "habitat_preference",
)

Genome = dict[str, float]


def _clamp01(value: float) -> float:
    """Clamp a gene value strictly into [0.0, 1.0]."""
    return max(0.0, min(1.0, float(value)))


def random_genome(
    species_template: Mapping[str, float] | None = None,
    rng: random.Random | None = None,
    spread: float = 0.08,
) -> Genome:
    """Create a genome centered on `species_template` with small Gaussian variation."""
    gen = rng if rng is not None else random.Random()
    template = species_template or {}
    keys = list(dict.fromkeys((*GENES, *template.keys())))
    return {
        key: _clamp01(template.get(key, 0.5) + gen.gauss(0.0, spread))
        for key in keys
    }


def crossover(
    parent_a: Mapping[str, float],
    parent_b: Mapping[str, float],
    rng: random.Random | None = None,
) -> Genome:
    """Combine two parent genomes by randomly inheriting each gene from A or B."""
    gen = rng if rng is not None else random.Random()
    keys = list(dict.fromkeys((*parent_a.keys(), *parent_b.keys())))
    child: Genome = {}
    for key in keys:
        a_val = parent_a.get(key, 0.5)
        b_val = parent_b.get(key, 0.5)
        child[key] = _clamp01(a_val if gen.random() < 0.5 else b_val)
    return child


def mutate(
    genome: Mapping[str, float],
    rate: float = 0.15,
    rng: random.Random | None = None,
    small_sigma: float = 0.05,
    jump_prob: float = 0.05,
    jump_sigma: float = 0.25,
) -> Genome:
    """Return a mutated copy of `genome` using small Gaussian steps and rare jumps."""
    gen = rng if rng is not None else random.Random()
    mutated: Genome = {}
    for key, val in genome.items():
        if gen.random() < rate:
            sigma = jump_sigma if gen.random() < jump_prob else small_sigma
            mutated[key] = _clamp01(val + gen.gauss(0.0, sigma))
        else:
            mutated[key] = _clamp01(val)
    return mutated


def genetic_distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Return normalized RMS genetic distance in [0.0, 1.0] between two genomes."""
    keys = list(dict.fromkeys((*a.keys(), *b.keys())))
    if not keys:
        return 0.0
    sq_sum = sum((a.get(k, 0.5) - b.get(k, 0.5)) ** 2 for k in keys)
    return math.sqrt(sq_sum / len(keys))


@dataclass(frozen=True)
class Phenotype:
    """Expressed physical and behavioral traits with real resource trade-offs."""

    food_need: float
    energy_cost: float
    combat_strength: float
    breed_cooldown_factor: float
    offspring_potential: float
    effective_lifespan_factor: float
    move_speed: int
    vision_radius: int
    learning_rate: float
    cold_drain_factor: float
    heat_drain_factor: float
    stealth: float


def express_phenotype(genome: Mapping[str, float]) -> Phenotype:
    """Translate raw [0, 1] genes into traits where every benefit carries a cost.

    Trade-offs:
    - Bigger `size` raises combat strength, but demands more food and slows breeding.
    - Higher `speed` and `vision` improve movement/sight, but burn extra energy.
    - Higher `intelligence` raises learning ability, but has a heavy energy cost.
    - Higher `fertility` increases offspring potential, but shortens lifespan.
    """
    size = _clamp01(genome.get("size", 0.5))
    metabolism = _clamp01(genome.get("metabolism", 0.5))
    speed = _clamp01(genome.get("speed", 0.5))
    vision = _clamp01(genome.get("vision", 0.5))
    fertility = _clamp01(genome.get("fertility", 0.5))
    lifespan = _clamp01(genome.get("lifespan", 0.5))
    aggression = _clamp01(genome.get("aggression", 0.5))
    intelligence = _clamp01(genome.get("intelligence", 0.5))
    cold_tol = _clamp01(genome.get("cold_tolerance", 0.5))
    heat_tol = _clamp01(genome.get("heat_tolerance", 0.5))
    disease_res = _clamp01(genome.get("disease_resistance", 0.5))
    camouflage = _clamp01(genome.get("camouflage", 0.5))

    food_need = 0.5 + 1.5 * size + 0.6 * metabolism
    energy_cost = (
        0.2
        + 0.6 * speed
        + 0.4 * vision
        + 1.2 * intelligence
        + 0.3 * metabolism
        + 0.2 * disease_res
    )
    combat_strength = 0.4 + 1.6 * size + 0.8 * aggression
    breed_cooldown_factor = 0.6 + 1.4 * size
    offspring_potential = 0.5 + 2.5 * fertility
    effective_lifespan_factor = (0.5 + 1.0 * lifespan) * (1.15 - 0.55 * fertility)

    return Phenotype(
        food_need=round(food_need, 4),
        energy_cost=round(energy_cost, 4),
        combat_strength=round(combat_strength, 4),
        breed_cooldown_factor=round(breed_cooldown_factor, 4),
        offspring_potential=round(offspring_potential, 4),
        effective_lifespan_factor=round(effective_lifespan_factor, 4),
        move_speed=1 + int(round(speed * 3)),
        vision_radius=2 + int(round(vision * 8)),
        learning_rate=round(0.1 + 0.9 * intelligence, 4),
        cold_drain_factor=round(1.4 - 1.1 * cold_tol, 4),
        heat_drain_factor=round(1.4 - 1.1 * heat_tol, 4),
        stealth=round(camouflage * (1.0 - 0.4 * size), 4),
    )
