"""Per-tile logistic population density grids for microscopic & numerous base-web species."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np

from world.biomes import BIOMES_BY_NAME, BodyType

if TYPE_CHECKING:
    from agents.ecosystem import SpeciesConfig
    from world.map import WorldMap

LAND_WATER_IDS = frozenset({
    BIOMES_BY_NAME["deep_ocean"].id, BIOMES_BY_NAME["shallow_sea"].id,
    BIOMES_BY_NAME["coral_reef"].id, BIOMES_BY_NAME["river"].id, BIOMES_BY_NAME["lake"].id,
})
FRESH_IDS = frozenset({
    BIOMES_BY_NAME["river"].id, BIOMES_BY_NAME["lake"].id, BIOMES_BY_NAME["wetland"].id,
})
SEA_IDS = frozenset({
    BIOMES_BY_NAME["deep_ocean"].id, BIOMES_BY_NAME["shallow_sea"].id, BIOMES_BY_NAME["coral_reef"].id,
})


def _habitat_mask(world: WorldMap, cfg: SpeciesConfig) -> np.ndarray:
    """Return boolean (H, W) mask of habitable tiles for a density-tier species."""
    bid = world.biome_id
    if cfg.habitat == "sea":
        mask = np.isin(bid, list(SEA_IDS))
        if cfg.name == "coral":
            coral_m = (bid == BIOMES_BY_NAME["coral_reef"].id) | (
                (bid == BIOMES_BY_NAME["shallow_sea"].id) & (world.temperature > 0.55)
            )
            mask = coral_m if np.any(coral_m) else (bid == BIOMES_BY_NAME["shallow_sea"].id)
        return mask if np.any(mask) else np.isin(bid, list(LAND_WATER_IDS))
    if cfg.habitat == "fresh_water":
        mask = np.isin(bid, list(FRESH_IDS))
        return mask if np.any(mask) else np.isin(bid, list(LAND_WATER_IDS))
    # Land / air / burrower: non-water, non-glacier tiles (fallback to any non-water)
    land = ~np.isin(bid, list(LAND_WATER_IDS))
    non_ice = land & (bid != BIOMES_BY_NAME["glacier"].id)
    return non_ice if np.any(non_ice) else land


class DensityGrid:
    """Vectorized per-tile logistic growth + refuge + diffusion model for tiny/numerous species."""

    def __init__(
        self,
        world: WorldMap,
        species_map: dict[str, SpeciesConfig],
        rng: random.Random,
    ) -> None:
        self.height, self.width = world.height, world.width
        self.configs: dict[str, SpeciesConfig] = {
            k: v for k, v in species_map.items() if v.is_density_tier
        }
        self.densities: dict[str, np.ndarray] = {}
        self.capacity: dict[str, np.ndarray] = {}
        self.refuges: dict[str, np.ndarray] = {}
        self._init_grids(world, rng)

    def _init_grids(self, world: WorldMap, rng: random.Random) -> None:
        h, w = self.height, self.width
        # Suitability weighted by food_max + moisture so fertile biomes hold higher densities
        suit = np.clip(0.35 + 0.65 * (world.food_max / max(1.0, float(world.food_max.max()))), 0.2, 1.0)
        for name, cfg in self.configs.items():
            mask = _habitat_mask(world, cfg)
            k_grid = np.where(mask, cfg.density_k * suit, 0.0).astype(np.float32)
            # Refuges: top ~15% most suitable habitable tiles buffer local shocks
            hab_vals = k_grid[mask]
            ref_thresh = float(np.percentile(hab_vals, 85)) if hab_vals.size > 0 else 1e9
            refuge = mask & (k_grid >= ref_thresh)
            jitter = np.array(
                [[rng.uniform(0.55, 0.85) for _ in range(w)] for _ in range(h)], dtype=np.float32,
            )
            self.capacity[name] = k_grid
            self.refuges[name] = refuge
            self.densities[name] = np.where(mask, k_grid * jitter, 0.0).astype(np.float32)

    def step(
        self,
        dt_days: float = 1.0,
        env_mult: float = 1.0,
        predation_pressure: dict[str, float] | None = None,
        climate_stress: float = 0.0,
        ocean_anoxia: float = 0.0,
    ) -> None:
        """Advance all per-tile density grids via logistic growth, refuges, and spatial diffusion."""
        pred = predation_pressure or {}
        dt = max(0.04, min(2.0, dt_days))
        for name, cfg in self.configs.items():
            grid = self.densities[name]
            k = self.capacity[name]
            refuge = self.refuges[name]
            if not np.any(k > 0.0):
                continue

            # Physical stress: specialists (e.g. coral) suffer much more from climate/anoxia
            stress = climate_stress * (2.6 if cfg.specialist else 0.45)
            if cfg.habitat == "sea" and ocean_anoxia > 0.0:
                stress += ocean_anoxia * (2.2 if cfg.specialist else 0.9)

            eff_k = np.maximum(1.0, k * max(0.15, env_mult * (1.0 - 0.55 * stress)))
            grazing = min(0.65, max(0.0, pred.get(name, 0.0)))
            r = cfg.growth_rate * max(0.25, env_mult)

            # Logistic growth: dN/dt = r * N * (1 - N/K) - mortality * N
            # Refuges reduce external predation/stress mortality by 60%
            mort = np.where(refuge, (grazing + stress * 0.35) * 0.40, grazing + stress * 0.35)
            growth = r * grid * (1.0 - grid / eff_k) - mort * grid
            updated = np.maximum(0.0, grid + growth * dt)

            # Spatial diffusion / recolonization from 4 neighbors along habitable corridors
            nbr_mean = 0.25 * (
                np.roll(updated, 1, 0) + np.roll(updated, -1, 0)
                + np.roll(updated, 1, 1) + np.roll(updated, -1, 1)
            )
            diffused = np.where(k > 0.0, updated * 0.94 + nbr_mean * 0.06, 0.0)
            # Refuge seed bank floor for non-specialist base species unless extreme physical shock
            if not cfg.specialist and stress < 0.75:
                diffused = np.where(refuge, np.maximum(diffused, k * 0.02), diffused)
            self.densities[name] = np.minimum(diffused, k * 1.25).astype(np.float32)

    def total_population(self, species: str) -> float:
        """Return total population across all tiles for a density-tier species."""
        grid = self.densities.get(species)
        return float(grid.sum()) if grid is not None else 0.0

    def all_totals(self) -> dict[str, float]:
        """Return `{species: total_population}` for every density-tier species."""
        return {name: float(grid.sum()) for name, grid in self.densities.items()}

    def harvest(self, species: str, x: int, y: int, amount: float) -> float:
        """Consume up to `amount` from tile `(x, y)` density; returns actual harvested amount."""
        grid = self.densities.get(species)
        if grid is None or not (0 <= y < self.height and 0 <= x < self.width):
            return 0.0
        avail = float(grid[y, x])
        taken = min(avail, max(0.0, amount))
        grid[y, x] = avail - taken
        return taken

    def pollinator_index(self) -> float:
        """Return normalized [0, 1.5] index of density-tier pollinators (`bee`, `butterfly`)."""
        cur, cap = 0.0, 0.0
        for name, cfg in self.configs.items():
            if cfg.trophic_level == "pollinator":
                cur += float(self.densities[name].sum())
                cap += float(self.capacity[name].sum())
        return min(1.5, (cur / max(1.0, cap)) * 1.5) if cap > 0.0 else 0.0

    def has_decomposers(self) -> bool:
        """Return True if soil/marine decomposers (`bacteria`, `fungi`, `worm`) remain active."""
        return any(
            float(self.densities[n].sum()) >= 1.0
            for n, c in self.configs.items()
            if c.trophic_level == "decomposer"
        )
