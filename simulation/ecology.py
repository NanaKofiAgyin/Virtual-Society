"""Tiered regional + per-tile ecosystem simulator (energy pyramid, MVP, refuges, disease)."""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from typing import Any

import numpy as np

from agents.ecosystem import (
    TROPHIC_TRANSFER_EFFICIENCY, SpeciesConfig,
    allee_effect_factor, inbreeding_depression_factor, load_species,
)
from simulation.disease import DiseaseEngine
from simulation.evolution import PHYSICAL_MASS_EXTINCTION_CAUSES
from world.biomes import BodyType
from world.climate import glacial_cycle
from world.density import DensityGrid
from world.map import WorldMap

N_ROWS, N_COLS = 3, 3
N_REGIONS = N_ROWS * N_COLS


@dataclass
class SpeciesMetrics:
    """Long-horizon summary statistics for a single species."""

    species: str
    tier: str
    trophic_level: str
    specialist: bool
    min_pop: float
    median_pop: float
    max_pop: float
    final_pop: float
    extinct_year: int | None = None


def _region_corridors() -> list[list[int]]:
    """Build 4-neighbor migration corridors across a 3x3 wrapping regional grid."""
    adj: list[list[int]] = [[] for _ in range(N_REGIONS)]
    for r in range(N_ROWS):
        for c in range(N_COLS):
            idx = r * N_COLS + c
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, (c + dc) % N_COLS
                if 0 <= nr < N_ROWS:
                    adj[idx].append(nr * N_COLS + nc)
    return adj


class TieredEcosystem:
    """Combines per-tile `DensityGrid` (base web) with regional viable herds/packs (larger animals)."""

    def __init__(self, seed: int = 42, width: int = 60, height: int = 60) -> None:
        self.seed, self.rng = seed, random.Random(seed)
        self.world = WorldMap(width=width, height=height, seed=seed)
        self.species: dict[str, SpeciesConfig] = load_species()
        self.density = DensityGrid(self.world, self.species, self.rng)
        self.disease = DiseaseEngine(self.rng)
        self.corridors = _region_corridors()
        self.region_area = float((width * height) / N_REGIONS)

        self.ind_species = [k for k, v in self.species.items() if not v.is_density_tier]
        self.pop: dict[str, list[float]] = {}
        self.infected: dict[str, list[float]] = {}
        self.diversity: dict[str, float] = {}
        self.resistance: dict[str, float] = {}
        self.allowed_regions: dict[str, set[int]] = {}
        self.refuge_regions: dict[str, set[int]] = {}
        self.extinct_year: dict[str, int | None] = {k: None for k in self.species}
        self.mass_extinctions: list[dict[str, Any]] = []
        self.recolonizations: int = 0
        self._init_individual_species()

    def _suitable_regions(self, cfg: SpeciesConfig) -> list[int]:
        """Rank regions by habitable tile count for `cfg`."""
        bt = BodyType(cfg.body_type)
        scores: list[tuple[int, int]] = []
        for r in range(N_REGIONS):
            ry, rx = divmod(r, N_COLS)
            y0, y1 = (ry * self.world.height) // N_ROWS, ((ry + 1) * self.world.height) // N_ROWS
            x0, x1 = (rx * self.world.width) // N_COLS, ((rx + 1) * self.world.width) // N_COLS
            cnt = sum(1 for y in range(y0, y1, 2) for x in range(x0, x1, 2) if self.world.can_enter(x, y, bt))
            scores.append((cnt, r))
        scores.sort(reverse=True)
        valid = [r for cnt, r in scores if cnt > 0]
        return valid if valid else list(range(N_REGIONS))

    def _init_individual_species(self) -> None:
        """Found viable herds/packs (30-150) in habitat-matched regions with refuges."""
        for name in self.ind_species:
            cfg = self.species[name]
            ranked = self._suitable_regions(cfg)
            n_niche = min(len(ranked), 3 if cfg.specialist else N_REGIONS)
            allowed = ranked[:max(2, n_niche)]
            self.allowed_regions[name] = set(allowed)
            n_occ = min(len(allowed), 3 if cfg.specialist else (6 if cfg.trophic_level == "apex_predator" else 7))
            chosen = allowed[:n_occ]
            self.refuge_regions[name] = set(chosen[:1] if cfg.specialist else chosen[:2])
            total = float(self.rng.randint(cfg.founding_min, cfg.founding_max))
            regs = [0.0] * N_REGIONS
            for r in chosen:
                regs[r] = total / len(chosen)
            self.pop[name] = regs
            self.infected[name] = [0.0] * N_REGIONS
            self.diversity[name] = 0.065 if cfg.specialist else 0.14
            self.resistance[name] = cfg.genome_template.get("disease_resistance", 0.5)

    def _region_density_energy(self, species: str, region_idx: int) -> float:
        grid = self.density.densities.get(species)
        if grid is None:
            return 0.0
        r, c = divmod(region_idx, N_COLS)
        y0, y1 = (r * self.world.height) // N_ROWS, ((r + 1) * self.world.height) // N_ROWS
        x0, x1 = (c * self.world.width) // N_COLS, ((c + 1) * self.world.width) // N_COLS
        return float(grid[y0:y1, x0:x1].sum()) * self.species[species].energy_value

    def _available_prey_energy(self, cfg: SpeciesConfig, r: int) -> float:
        """Compute available prey energy in `r` (apex predators pool across their home range)."""
        scope = [r, *self.corridors[r]] if cfg.home_range >= 18 else [r]
        energy = 0.0
        for prey_name in (cfg.prey if cfg.prey else ("grasses", "insects")):
            pcfg = self.species.get(prey_name)
            if pcfg is None:
                continue
            if pcfg.is_density_tier:
                energy += sum(self._region_density_energy(prey_name, s) for s in scope) * 0.002
            else:
                energy += sum(self.pop[prey_name][s] for s in scope) * pcfg.energy_value
        if cfg.diet == "scavenger":
            energy += sum(self.pop[sp][s] * self.species[sp].energy_value for sp in self.ind_species for s in scope) * 0.06
        return energy

    def _step_physical_driver(self, year: int) -> tuple[str | None, float, float]:
        """Compute physical climate/volcanic/anoxia stress; never random mass extinctions."""
        g_temp, _ = glacial_cycle(year * 15)
        climate_stress = max(0.0, abs(g_temp) / 14.0)
        roll = self.rng.random()
        if roll < 0.004:
            return "volcanic_winter", climate_stress + 0.40, 0.0
        if roll < 0.007:
            return "ocean_anoxia", climate_stress + 0.12, 0.50
        return (None, climate_stress, 0.0)

    def step_year(self, year: int) -> dict[str, float]:
        """Advance all 47 species by 1 simulated year (4 seasons) and return total populations."""
        physical_cause, climate_stress, ocean_anoxia = self._step_physical_driver(year)
        live_before = {k for k, v in self.extinct_year.items() if v is None}

        for season_idx in range(4):
            env_mult = (1.12, 1.20, 0.95, 0.78)[season_idx]
            self.density.step(dt_days=1.5, env_mult=env_mult, climate_stress=climate_stress, ocean_anoxia=ocean_anoxia)
            poll_mult = 0.65 + 0.35 * self.density.pollinator_index()

            for name in self.ind_species:
                cfg, regs = self.species[name], self.pop[name]
                total_pop = sum(regs)
                if total_pop < 1.0:
                    self.pop[name] = [0.0] * N_REGIONS
                    continue

                self.diversity[name] = max(0.015, self.diversity[name] * 0.95) if total_pop < 28.0 else min(0.18, self.diversity[name] + 0.0015)
                inbreed = inbreeding_depression_factor(int(total_pop), self.diversity[name])
                n_allowed = max(1, len(self.allowed_regions[name]))
                # Energy-pyramid regional cap: apex ~45-95 total, secondary ~140-260, primary ~350-650
                trophic_scale = 2.0 if cfg.trophic_level == "apex_predator" else (3.0 if cfg.trophic_level in ("secondary_consumer", "scavenger") else 4.2)
                reg_cap = ((cfg.founding_max * trophic_scale) / n_allowed) * env_mult * poll_mult
                next_regs = list(regs)

                for r in range(N_REGIONS):
                    n = regs[r]
                    if n < 0.5 or r not in self.allowed_regions[name]:
                        next_regs[r] = 0.0
                        continue
                    prey_e = self._available_prey_energy(cfg, r)
                    k_energy = (prey_e * TROPHIC_TRANSFER_EFFICIENCY) / max(8.0, cfg.energy_value * 0.35)
                    k_reg = max(1.5, min(reg_cap, k_energy if prey_e > 0 else 0.0))

                    allee = allee_effect_factor(int(n), cfg.social, threshold=7)
                    r_grow = 0.28 if cfg.trophic_level == "primary_consumer" else (0.20 if cfg.trophic_level != "apex_predator" else 0.14)
                    inf_f, dis_mort = self.disease.step_regional_outbreak(
                        name, n, self.infected[name][r], self.region_area, self.resistance[name], cfg.social,
                    )
                    self.infected[name][r] = inf_f
                    if dis_mort > 0.01:
                        self.resistance[name] = min(0.95, self.resistance[name] + 0.004)

                    stress = climate_stress * (2.2 if cfg.specialist else 0.35)
                    if cfg.habitat == "sea" and ocean_anoxia > 0.0:
                        stress += ocean_anoxia * (2.2 if cfg.specialist else 0.55)
                    if r in self.refuge_regions[name]:
                        stress *= 0.45

                    noise = self.rng.gauss(0.0, 0.085 if cfg.specialist else 0.025)
                    dn = (r_grow * inbreed * allee) * n * (1.0 - n / k_reg) - (dis_mort + stress * 0.50) * n + noise * n
                    next_regs[r] = 0.0 if (n + dn) < 1.5 else (n + dn)

                for r in self.allowed_regions[name]:
                    if next_regs[r] < 1.0:
                        donors = [nb for nb in self.corridors[r] if next_regs[nb] >= (12.0 if cfg.specialist else 7.0)]
                        if donors and self.rng.random() < (0.14 if cfg.specialist else 0.42):
                            d = self.rng.choice(donors)
                            migrants = min(4.0, next_regs[d] * 0.15)
                            next_regs[d] -= migrants
                            next_regs[r] += migrants
                            self.recolonizations += 1
                self.pop[name] = next_regs

        totals = self.population_totals()
        extinct_now = 0
        for name, tot in totals.items():
            if self.extinct_year[name] is None and tot < 1.0:
                self.extinct_year[name] = year
                extinct_now += 1
        if physical_cause in PHYSICAL_MASS_EXTINCTION_CAUSES and extinct_now >= max(2, int(len(live_before) * 0.25)):
            self.mass_extinctions.append({"year": year, "cause": physical_cause, "count": extinct_now})
        return totals

    def population_totals(self) -> dict[str, float]:
        totals = self.density.all_totals()
        for name in self.ind_species:
            totals[name] = sum(self.pop[name])
        return totals

    def run_years(self, years: int = 200) -> dict[str, SpeciesMetrics]:
        series: dict[str, list[float]] = {k: [] for k in self.species}
        for yr in range(1, years + 1):
            tots = self.step_year(yr)
            for k, v in tots.items():
                series[k].append(v)
        return {
            name: SpeciesMetrics(
                species=name, tier=cfg.simulation_tier, trophic_level=cfg.trophic_level,
                specialist=cfg.specialist, min_pop=min(series[name]), median_pop=statistics.median(series[name]),
                max_pop=max(series[name]), final_pop=series[name][-1], extinct_year=self.extinct_year[name],
            )
            for name, cfg in self.species.items()
        }
