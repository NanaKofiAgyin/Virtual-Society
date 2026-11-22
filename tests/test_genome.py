"""Unit tests for `agents/genome.py` (genetics, trade-offs, emergent selection)."""

from __future__ import annotations

import random

from agents.genome import (
    GENES,
    crossover,
    express_phenotype,
    genetic_distance,
    mutate,
    random_genome,
)


def test_random_genome_range_and_seed_reproducibility() -> None:
    """random_genome populates all genes in [0, 1] and is reproducible with a seed."""
    template = {"size": 0.8, "cold_tolerance": 0.2}
    g1 = random_genome(template, rng=random.Random(42))
    g2 = random_genome(template, rng=random.Random(42))

    assert g1 == g2
    assert set(GENES).issubset(g1.keys())
    assert all(0.0 <= v <= 1.0 for v in g1.values())


def test_crossover_mixes_genes_from_both_parents() -> None:
    """Crossover produces children carrying genes inherited from both parent A and B."""
    parent_a = {g: 0.1 for g in GENES}
    parent_b = {g: 0.9 for g in GENES}
    rng = random.Random(7)

    child = crossover(parent_a, parent_b, rng=rng)
    assert set(child.keys()) == set(GENES)
    from_a = sum(1 for v in child.values() if v == 0.1)
    from_b = sum(1 for v in child.values() if v == 0.9)
    assert from_a > 0 and from_b > 0
    assert from_a + from_b == len(GENES)


def test_mutate_stays_in_range_and_produces_small_and_large_changes() -> None:
    """Mutation keeps all genes in [0, 1] and includes rare larger jumps."""
    base = {g: 0.5 for g in GENES}
    rng = random.Random(123)

    deltas: list[float] = []
    for _ in range(300):
        m = mutate(base, rate=0.5, rng=rng)
        assert all(0.0 <= v <= 1.0 for v in m.values())
        deltas.extend(abs(m[g] - base[g]) for g in GENES if m[g] != base[g])

    assert deltas
    assert any(d > 0.15 for d in deltas), "Expected at least one rare larger jump"
    assert any(0.0 < d < 0.08 for d in deltas), "Expected small Gaussian mutations"

    # Boundary clamping check
    extreme = {g: 0.0 if i % 2 == 0 else 1.0 for i, g in enumerate(GENES)}
    for _ in range(50):
        m = mutate(extreme, rate=1.0, rng=rng)
        assert all(0.0 <= v <= 1.0 for v in m.values())


def test_genetic_distance_properties() -> None:
    """genetic_distance is 0 for identical genomes, symmetric, and bounded in [0, 1]."""
    a = {g: 0.2 for g in GENES}
    b = {g: 0.8 for g in GENES}
    c = {g: 0.25 for g in GENES}

    assert genetic_distance(a, a) == 0.0
    assert genetic_distance(a, b) == genetic_distance(b, a)
    assert 0.0 < genetic_distance(a, c) < genetic_distance(a, b) <= 1.0


def test_gene_tradeoffs_have_real_costs_and_benefits() -> None:
    """Every beneficial gene carries a corresponding resource or life-history cost."""
    base = {g: 0.5 for g in GENES}
    p_base = express_phenotype(base)

    # Bigger size -> more food needed, stronger fights, slower breeding
    p_big = express_phenotype({**base, "size": 0.9})
    assert p_big.food_need > p_base.food_need
    assert p_big.combat_strength > p_base.combat_strength
    assert p_big.breed_cooldown_factor > p_base.breed_cooldown_factor

    # Higher speed & vision -> extra energy cost
    p_fast = express_phenotype({**base, "speed": 0.95, "vision": 0.95})
    assert p_fast.move_speed > p_base.move_speed
    assert p_fast.vision_radius > p_base.vision_radius
    assert p_fast.energy_cost > p_base.energy_cost

    # Higher intelligence -> heavy energy cost + higher learning ability
    p_smart = express_phenotype({**base, "intelligence": 0.95})
    assert p_smart.learning_rate > p_base.learning_rate
    assert p_smart.energy_cost > p_base.energy_cost + 0.4

    # Higher fertility -> more offspring potential, shorter lifespan
    p_fertile = express_phenotype({**base, "fertility": 0.95})
    assert p_fertile.offspring_potential > p_base.offspring_potential
    assert p_fertile.effective_lifespan_factor < p_base.effective_lifespan_factor


def test_cold_tolerance_evolves_over_200_generations_in_harsh_cold_biome() -> None:
    """Over 200 generations in a cold biome, average cold_tolerance rises purely via survival."""
    rng = random.Random(42)
    pop_size = 60
    population = [random_genome({"cold_tolerance": 0.35}, rng=rng, spread=0.12) for _ in range(pop_size)]
    initial_avg = sum(g["cold_tolerance"] for g in population) / len(population)

    # Harsh cold environment: energy left after cold drain funds survival & reproduction
    for gen in range(200):
        # Occasional harsh winter snaps test thin energy reserves
        cold_severity = 1.45 if gen % 4 == 0 else 1.25
        energy_supply = 1.75
        breeders: list[dict[str, float]] = []
        for g in population:
            pheno = express_phenotype(g)
            surplus = energy_supply - cold_severity * pheno.cold_drain_factor - 0.12 * pheno.energy_cost
            if surplus > 0.0:
                # Each 0.25 unit of surplus energy can fund a breeding attempt
                attempts = max(1, int(surplus / 0.25))
                breeders.extend([g] * attempts)

        assert len(breeders) >= 2, "Population collapsed in cold biome test"
        next_gen = []
        while len(next_gen) < pop_size:
            p1, p2 = rng.choice(breeders), rng.choice(breeders)
            next_gen.append(mutate(crossover(p1, p2, rng=rng), rate=0.15, rng=rng))
        population = next_gen

    final_avg = sum(g["cold_tolerance"] for g in population) / len(population)
    assert final_avg > initial_avg + 0.30, f"Expected cold_tolerance to evolve: {initial_avg:.3f} -> {final_avg:.3f}"
