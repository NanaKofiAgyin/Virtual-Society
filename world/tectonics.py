"""Simplified plate tectonics, isostasy, volcanism, sea-level cycles, and geological time."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from world.erosion import count_continents, hydraulic_erosion, thermal_erosion

YEARS_PER_GEOLOGICAL_TICK = 1000


def _fractal_noise(rng: np.random.Generator, height: int, width: int) -> np.ndarray:
    """Generate wrapping multi-octave fractal noise in [0, 1]."""
    total = np.zeros((height, width), dtype=np.float32)
    amp, weight_sum = 1.0, 0.0
    for passes in (10, 5, 2):
        g = rng.random((height, width), dtype=np.float32)
        for _ in range(passes):
            g = (
                g + np.roll(g, 1, 0) + np.roll(g, -1, 0)
                + np.roll(g, 1, 1) + np.roll(g, -1, 1)
            ) / 5.0
        lo, hi = float(g.min()), float(g.max())
        norm = (g - lo) / (hi - lo) if hi > lo else g
        total += norm * amp
        weight_sum += amp
        amp *= 0.5
    return (total / weight_sum).astype(np.float32)


@dataclass
class Plate:
    """A single continental or oceanic tectonic plate."""

    id: int
    is_continental: bool
    cx: float
    cy: float
    vx: float
    vy: float
    base_thickness: float


class TectonicWorld:
    """Wrapping plate-tectonic world with mountain belts, trenches, rifts, erosion & sea level."""

    def __init__(
        self,
        width: int = 128,
        height: int = 128,
        seed: int = 42,
        n_plates: int | None = None,
    ) -> None:
        self.width, self.height, self.seed = width, height, seed
        self.rng = np.random.default_rng(seed)
        self.years_elapsed: int = 0
        self.base_sea_level: float = 0.48
        self.sea_level: float = self.base_sea_level
        self.timeline: list[dict[str, Any]] = []

        count = int(self.rng.integers(8, 16)) if n_plates is None else max(8, min(15, n_plates))
        n_cont = max(3, int(round(count * 0.34)))
        types = [True] * n_cont + [False] * (count - n_cont)
        self.rng.shuffle(types)

        self.plates: list[Plate] = []
        for pid, is_cont in enumerate(types):
            ang = float(self.rng.uniform(0.0, 2.0 * math.pi))
            spd = float(self.rng.uniform(0.35, 1.15))
            self.plates.append(Plate(
                id=pid, is_continental=is_cont,
                cx=float(self.rng.uniform(0, width)), cy=float(self.rng.uniform(0, height)),
                vx=math.cos(ang) * spd, vy=math.sin(ang) * spd,
                base_thickness=0.62 if is_cont else 0.24,
            ))

        self.hotspots: list[tuple[int, int]] = [
            (int(self.rng.integers(0, width)), int(self.rng.integers(0, height)))
            for _ in range(3)
        ]

        self._yy, self._xx = np.mgrid[0:height, 0:width].astype(np.float32)
        self.plate_id = np.zeros((height, width), dtype=np.int16)
        self.boundary_mask = np.zeros((height, width), dtype=bool)
        self.volcano_mask = np.zeros((height, width), dtype=bool)
        self.fault_mask = np.zeros((height, width), dtype=bool)

        self._assign_plates()
        fractal = _fractal_noise(self.rng, height, width)
        self.crust_thickness = np.zeros((height, width), dtype=np.float32)
        for p in self.plates:
            self.crust_thickness[self.plate_id == p.id] = p.base_thickness
        # Interior relief stays below mountain threshold (0.76) so mountains form only at boundaries
        self.elevation = np.clip(self.crust_thickness + (fractal - 0.5) * 0.20, 0.05, 0.72).astype(np.float32)
        self._calibrate_sea_level()
        self._last_continents = count_continents(self.elevation > self.sea_level)

    def _assign_plates(self) -> None:
        """Assign each cell to its nearest plate center using wrapping torus distance."""
        best_d2 = np.full((self.height, self.width), 1e18, dtype=np.float32)
        for p in self.plates:
            dx = np.abs(self._xx - p.cx)
            dx = np.minimum(dx, self.width - dx)
            dy = np.abs(self._yy - p.cy)
            dy = np.minimum(dy, self.height - dy)
            d2 = dx * dx + dy * dy
            closer = d2 < best_d2
            self.plate_id[closer] = p.id
            best_d2[closer] = d2[closer]

    def _calibrate_sea_level(self) -> None:
        """Keep base sea level tuned so global land fraction stays naturally within 25–40%."""
        land_frac = self.land_fraction()
        if land_frac < 0.28 or land_frac > 0.37:
            self.base_sea_level = float(np.quantile(self.elevation, 0.67))
            self.sea_level = self.base_sea_level

    def land_fraction(self) -> float:
        """Return fraction of world tiles above current global sea level."""
        return float(np.mean(self.elevation > self.sea_level))

    def _apply_boundaries(self) -> None:
        """Compute convergent (collision/subduction), divergent (rift), and transform boundaries."""
        vx_arr = np.array([p.vx for p in self.plates], dtype=np.float32)
        vy_arr = np.array([p.vy for p in self.plates], dtype=np.float32)
        cont_arr = np.array([p.is_continental for p in self.plates], dtype=bool)

        p0 = self.plate_id
        self.boundary_mask.fill(False)
        self.volcano_mask.fill(False)
        self.fault_mask.fill(False)
        uplift = np.zeros_like(self.elevation)

        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p1 = np.roll(np.roll(p0, -dy, axis=0), -dx, axis=1)
            diff = p0 != p1
            if not np.any(diff):
                continue
            self.boundary_mask |= diff

            # Relative velocity projected onto normal (dx, dy): positive = converging
            rel_n = (vx_arr[p0] - vx_arr[p1]) * dx + (vy_arr[p0] - vy_arr[p1]) * dy
            rel_t = np.abs((vx_arr[p0] - vx_arr[p1]) * (-dy) + (vy_arr[p0] - vy_arr[p1]) * dx)
            c0, c1 = cont_arr[p0], cont_arr[p1]

            converge = diff & (rel_n > 0.15)
            diverge = diff & (rel_n < -0.15)
            transform = diff & (~converge) & (~diverge) & (rel_t > 0.15)

            # Cont-Cont collision -> folded mountain belts
            cont_col = converge & c0 & c1
            uplift[cont_col] += 0.085
            self.crust_thickness[cont_col] = np.minimum(0.95, self.crust_thickness[cont_col] + 0.03)

            # Subduction (oceanic meets another plate) -> trench + coastal/volcanic arc
            subduct_ocean = converge & (~c0)
            uplift[subduct_ocean] -= 0.055  # deep ocean trench
            override_arc = converge & c0 & (~c1)
            uplift[override_arc] += 0.065   # coastal range / volcanic arc
            self.volcano_mask |= override_arc

            # Divergent -> mid-ocean ridge or continental rift valley
            uplift[diverge & c0] -= 0.045
            uplift[diverge & (~c0)] += 0.015
            self.crust_thickness[diverge] = np.maximum(0.18, self.crust_thickness[diverge] - 0.015)

            # Transform -> fault lines & earthquakes
            self.fault_mask |= transform

        # Spread mountain/trench deformation 1 cell wide for realistic belts
        belt = (
            uplift
            + 0.35 * (np.roll(uplift, 1, 0) + np.roll(uplift, -1, 0)
                      + np.roll(uplift, 1, 1) + np.roll(uplift, -1, 1))
        )
        self.boundary_mask |= (
            np.roll(self.boundary_mask, 1, 0) | np.roll(self.boundary_mask, -1, 0)
            | np.roll(self.boundary_mask, 1, 1) | np.roll(self.boundary_mask, -1, 1)
        )
        self.elevation = np.clip(self.elevation + belt, 0.0, 1.0)

    def _apply_hotspots_and_isostasy(self) -> None:
        """Apply mantle hotspot volcanism and isostatic buoyancy adjustment."""
        for hx, hy in self.hotspots:
            self.volcano_mask[hy, hx] = True
            self.elevation[hy, hx] = min(0.96, float(self.elevation[hy, hx]) + 0.03)
        # Isostasy: crust thickness gently buoys elevation toward equilibrium
        self.elevation = np.clip(self.elevation + (self.crust_thickness - self.elevation) * 0.04, 0.0, 1.0)

    def step(self, geological_ticks: int = 1) -> None:
        """Advance geological time (`1 tick = 1,000 years`): drift, boundaries, erosion, sea level."""
        for _ in range(max(0, geological_ticks)):
            self.years_elapsed += YEARS_PER_GEOLOGICAL_TICK
            for p in self.plates:
                p.cx = (p.cx + p.vx) % self.width
                p.cy = (p.cy + p.vy) % self.height

            self._assign_plates()
            self._apply_boundaries()
            self._apply_hotspots_and_isostasy()

            # Thermal & hydraulic erosion wears down old mountain ranges
            self.elevation = thermal_erosion(self.elevation, iterations=2)
            self.elevation = hydraulic_erosion(self.elevation, sea_level=self.sea_level, iterations=2)

            # Climate-driven global sea level oscillation (100k-year glacial cycle)
            cycle = 0.025 * math.sin(2.0 * math.pi * self.years_elapsed / 100_000.0)
            self.sea_level = float(np.clip(self.base_sea_level + cycle, 0.25, 0.75))
            # Keep long-run land area within plausible Earth-like 25-40% bounds
            if self.land_fraction() < 0.26 or self.land_fraction() > 0.39:
                self._calibrate_sea_level()

            continents = count_continents(self.elevation > self.sea_level)
            if continents < self._last_continents:
                self.timeline.append({
                    "year": self.years_elapsed, "kind": "continent_merge",
                    "message": f"Continents merged ({self._last_continents} -> {continents})",
                })
            elif continents > self._last_continents:
                self.timeline.append({
                    "year": self.years_elapsed, "kind": "continent_split",
                    "message": f"Continent split ({self._last_continents} -> {continents})",
                })
            self._last_continents = continents

    def fast_forward(self, years: int) -> dict[str, Any]:
        """Fast-forward geological time by `years` (1 tick = 1,000 years)."""
        ticks = max(1, years // YEARS_PER_GEOLOGICAL_TICK)
        self.step(ticks)
        return {
            "years_elapsed": self.years_elapsed,
            "land_fraction": round(self.land_fraction(), 3),
            "sea_level": round(self.sea_level, 3),
            "continents": self._last_continents,
            "events": len(self.timeline),
        }
