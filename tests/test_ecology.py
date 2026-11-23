"""Tests for tiered ecosystem stability, energy pyramid, MVP, refuges, disease, and 200-year runs."""

from __future__ import annotations

import random

from agents.ecosystem import allee_effect_factor, inbreeding_depression_factor, load_species
from simulation.disease import DiseaseEngine
from simulation.ecology import TieredEcosystem
from world.density import DensityGrid
from world.map import WorldMap


def test_tiered_species_config_and_energy_pyramid_founding() -> None:
    """Tiny/numerous species use density tier; larger animals found in viable herds/packs (30-150)."""
    species = load_species()
    for base in ("grasses", "algae", "phytoplankton", "insects", "zooplankton", "worm", "bacteria", "fungi", "bee", "butterfly"):
        assert species[base].is_density_tier
        assert species[base].founding_max == 0
        assert species[base].density_k > 0.0

    for apex in ("wolf", "lion", "bear", "shark", "orca", "eagle", "crocodile"):
        cfg = species[apex]
        assert not cfg.is_density_tier
        assert 30 <= cfg.founding_min <= cfg.founding_max <= 100
        assert cfg.home_range >= 20


def test_inbreeding_depression_and_allee_effect_mechanisms() -> None:
    """Small genetically bottlenecked pops suffer inbreeding; social species suffer Allee effect."""
    assert inbreeding_depression_factor(pop_size=60, genetic_diversity=0.12) == 1.0
    assert inbreeding_depression_factor(pop_size=8, genetic_diversity=0.03) < 0.65

    assert allee_effect_factor(local_count=2, social=False) == 1.0
    assert allee_effect_factor(local_count=12, social=True, threshold=8) == 1.0
    assert allee_effect_factor(local_count=2, social=True, threshold=8) < 0.5


def test_density_grid_logistic_growth_and_recolonization() -> None:
    """DensityGrid sustains base-web species via logistic growth and recolonizes depleted tiles."""
    species = load_species()
    world = WorldMap(width=24, height=24, seed=9)
    grid = DensityGrid(world, species, random.Random(9))

    # Wipe out half the map for insects and verify neighbors recolonize it
    insects = grid.densities["insects"]
    insects[:, :12] = 0.0
    before = float(insects[:, :12].sum())
    assert before == 0.0

    for _ in range(12):
        grid.step(dt_days=1.0, env_mult=1.0)
    assert float(grid.densities["insects"][:, :12].sum()) > 0.0
    assert grid.pollinator_index() > 0.3
    assert grid.has_decomposers()


def test_disease_is_density_dependent_and_mutates_slowly() -> None:
    """Contact-based disease spreads faster in dense populations and mutates pathogen traits."""
    eng_high = DiseaseEngine(random.Random(11))
    eng_low = DiseaseEngine(random.Random(11))

    inf_hi, inf_lo = 0.05, 0.05
    for _ in range(15):
        inf_hi, _ = eng_high.step_regional_outbreak("deer", pop=300.0, infected_frac=inf_hi, region_area=80.0, mean_resistance=0.3, social=True)
        inf_lo, _ = eng_low.step_regional_outbreak("deer", pop=10.0, infected_frac=inf_lo, region_area=80.0, mean_resistance=0.3, social=True)

    assert inf_hi > inf_lo
    assert eng_high.strains["deer"].generation > 0


def test_200_year_ecosystem_keeps_food_web_base_stable() -> None:
    """Over 200 simulated years, base food web stays intact and energy pyramid holds."""
    eco = TieredEcosystem(seed=42, width=48, height=48)
    metrics = eco.run_years(200)

    # All non-specialist density-tier base species must survive 200 years
    for name in ("grasses", "algae", "phytoplankton", "insects", "zooplankton", "worm", "bacteria", "fungi", "bee", "butterfly"):
        assert metrics[name].extinct_year is None, f"Base species {name} went extinct!"
        assert metrics[name].final_pop > 1000.0

    # Energy pyramid: primary consumers > secondary consumers > apex predators
    assert metrics["rabbit"].median_pop > metrics["fox"].median_pop > metrics["wolf"].median_pop
    assert metrics["wolf"].median_pop >= 30.0
    assert eco.recolonizations > 0
