"""Layered 200x200 NumPy world map: elevation, temperature, moisture, rivers, biomes."""

from __future__ import annotations

import random
from collections import deque
from typing import Any

import numpy as np

from world.biomes import BIOMES_BY_ID, BIOMES_BY_NAME, BodyType, can_traverse, classify_biome
from world.environment import Environment
from world.tile import ResourceType, TerrainType, Tile

SEA_LEVEL = 0.30


def _smoothed_noise(rng: np.random.Generator, height: int, width: int, passes: int = 6) -> np.ndarray:
    """Generate smooth 2D noise in [0, 1] using vectorized box-blur passes."""
    grid = rng.random((height, width), dtype=np.float32)
    for _ in range(passes):
        padded = np.pad(grid, 1, mode="edge")
        grid = (
            padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:]
            + padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:]
            + padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
        ) / 9.0
    lo, hi = float(grid.min()), float(grid.max())
    return (grid - lo) / (hi - lo) if hi > lo else grid


class WorldMap:
    """Seeded, NumPy-backed layered world with 17 biomes, rivers, and body-type movement."""

    def __init__(self, width: int = 200, height: int = 200, seed: int | None = None) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive integers")
        self.width = width
        self.height = height
        self.seed = seed
        self.rng = random.Random(seed)
        self.environment = Environment(rng=self.rng)

        np_seed = seed if seed is not None else self.rng.randrange(2**32)
        np_rng = np.random.default_rng(np_seed)

        self.elevation = _smoothed_noise(np_rng, height, width, passes=8)
        self.moisture = _smoothed_noise(np_rng, height, width, passes=6)
        self.ocean_depth = np.clip((SEA_LEVEL - self.elevation) / SEA_LEVEL, 0.0, 1.0).astype(np.float32)

        # Latitude-driven temperature (warm equator at y=H/2, cold poles at y=0 & y=H-1)
        y_coords = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
        latitude_temp = 1.0 - np.abs(y_coords)
        temp_noise = _smoothed_noise(np_rng, height, width, passes=5)
        lapse = np.clip(self.elevation - SEA_LEVEL, 0.0, 1.0) * 0.45
        self.temperature = np.clip(0.65 * latitude_temp + 0.35 * temp_noise - lapse, 0.0, 1.0).astype(np.float32)

        self.biome_id = np.zeros((height, width), dtype=np.uint8)
        self.food = np.zeros((height, width), dtype=np.float32)
        self.food_max, self.food_regen = self.food.copy(), self.food.copy()
        self.wood, self.wood_max, self.wood_regen = self.food.copy(), self.food.copy(), self.food.copy()
        self._classify_all(np_rng)

    def _trace_rivers(self, np_rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        """Trace rivers downhill from high peaks to ocean, forming lakes in inland basins."""
        rivers = np.zeros((self.height, self.width), dtype=bool)
        lakes = np.zeros((self.height, self.width), dtype=bool)
        peaks = np.argwhere(self.elevation > 0.76)
        if len(peaks) == 0:
            return rivers, lakes
        n_rivers = max(2, min(14, (self.width * self.height) // 2500))
        chosen = peaks[np_rng.choice(len(peaks), size=min(n_rivers, len(peaks)), replace=False)]

        for sy, sx in chosen:
            y, x = int(sy), int(sx)
            visited: set[tuple[int, int]] = set()
            for _ in range(self.width + self.height):
                if self.ocean_depth[y, x] > 0.0 or (y, x) in visited:
                    break
                visited.add((y, x))
                rivers[y, x] = True
                best_e = float(self.elevation[y, x])
                nxt: tuple[int, int] | None = None
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < self.height and 0 <= nx < self.width and (ny, nx) not in visited:
                        e = float(self.elevation[ny, nx])
                        if e < best_e:
                            best_e, nxt = e, (ny, nx)
                if nxt is None:
                    lakes[y, x] = True
                    break
                y, x = nxt
        return rivers, lakes

    def _classify_all(self, np_rng: np.random.Generator) -> None:
        """Assign biome IDs and initial resource arrays from the climate/elevation layers."""
        rivers, lakes = self._trace_rivers(np_rng)
        caves = (self.elevation > 0.70) & (self.elevation <= 0.83) & (np_rng.random((self.height, self.width)) < 0.015)

        for y in range(self.height):
            for x in range(self.width):
                name = classify_biome(
                    float(self.elevation[y, x]), float(self.temperature[y, x]),
                    float(self.moisture[y, x]), float(self.ocean_depth[y, x]),
                    is_river=bool(rivers[y, x]), is_lake=bool(lakes[y, x]), is_cave=bool(caves[y, x]),
                )
                spec = BIOMES_BY_NAME[name]
                self.biome_id[y, x] = spec.id
                self.food[y, x] = self.food_max[y, x] = spec.food_max
                self.food_regen[y, x] = spec.food_regen
                self.wood[y, x] = self.wood_max[y, x] = spec.wood_max
                self.wood_regen[y, x] = spec.wood_regen

    def set_terrain(self, x: int, y: int, terrain: TerrainType | str) -> Tile:
        """Change the biome/terrain at `(x, y)` and reset its resource capacities."""
        t = TerrainType(terrain)
        spec = BIOMES_BY_NAME[t.value]
        self.biome_id[y, x] = spec.id
        self.food[y, x] = self.food_max[y, x] = spec.food_max
        self.food_regen[y, x] = spec.food_regen
        self.wood[y, x] = self.wood_max[y, x] = spec.wood_max
        self.wood_regen[y, x] = spec.wood_regen
        return self.get_tile(x, y)  # type: ignore[return-value]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def can_enter(self, x: int, y: int, body_type: BodyType = BodyType.LAND) -> bool:
        """Return True if an organism with `body_type` can enter tile `(x, y)`."""
        if not self.in_bounds(x, y):
            return False
        return can_traverse(BIOMES_BY_ID[int(self.biome_id[y, x])], body_type)

    def get_tile(self, x: int, y: int) -> Tile | None:
        """Return a `Tile` view at `(x, y)`, or None if out of bounds."""
        if not self.in_bounds(x, y):
            return None
        spec = BIOMES_BY_ID[int(self.biome_id[y, x])]
        return Tile(
            x=x, y=y, terrain=TerrainType(spec.name), walkable=spec.walkable,
            resources={ResourceType.FOOD: float(self.food[y, x]), ResourceType.WOOD: float(self.wood[y, x])},
            max_resources={ResourceType.FOOD: float(self.food_max[y, x]), ResourceType.WOOD: float(self.wood_max[y, x])},
            regen_rates={ResourceType.FOOD: float(self.food_regen[y, x]), ResourceType.WOOD: float(self.wood_regen[y, x])},
            elevation=float(self.elevation[y, x]), temperature=float(self.temperature[y, x]),
            moisture=float(self.moisture[y, x]), ocean_depth=float(self.ocean_depth[y, x]),
            plants=spec.plants, _map=self,
        )

    def get_nearby(self, x: int, y: int, radius: int, include_self: bool = False) -> list[Tile]:
        if radius < 0:
            raise ValueError("radius must be non-negative")
        tiles: list[Tile] = []
        for ty in range(max(0, y - radius), min(self.height, y + radius + 1)):
            for tx in range(max(0, x - radius), min(self.width, x + radius + 1)):
                if not include_self and tx == x and ty == y:
                    continue
                tile = self.get_tile(tx, ty)
                if tile is not None:
                    tiles.append(tile)
        return tiles

    def positions_for_body(self, body_type: BodyType = BodyType.LAND) -> list[tuple[int, int]]:
        """Return all `(x, y)` positions traversable by `body_type`."""
        valid_ids = [bid for bid, spec in BIOMES_BY_ID.items() if can_traverse(spec, body_type)]
        coords = np.argwhere(np.isin(self.biome_id, valid_ids))
        return [(int(x), int(y)) for y, x in coords]

    def place_village(self, n_houses: int = 10, n_farms: int = 10) -> list[Tile]:
        """Place `n_houses` houses and `n_farms` farms on walkable land near map center."""
        cx, cy = self.width // 2, self.height // 2
        walkable = self.positions_for_body(BodyType.LAND)
        pool = walkable if len(walkable) >= n_houses + n_farms else [
            (x, y) for y in range(self.height) for x in range(self.width)
        ]
        pool.sort(key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p[1], p[0]))
        placed: list[Tile] = []
        for idx, (x, y) in enumerate(pool[: n_houses + n_farms]):
            terrain = TerrainType.HOUSE if idx < n_houses else TerrainType.FARM
            placed.append(self.set_terrain(x, y, terrain))
        return placed

    def find_nearest(
        self, x: int, y: int, resource: ResourceType | str, min_amount: float = 0.01,
    ) -> Tile | None:
        """Return the closest tile with at least `min_amount` of `resource` using NumPy."""
        res_type = ResourceType(resource)
        arr = self.food if res_type is ResourceType.FOOD else self.wood
        coords = np.argwhere(arr >= min_amount)
        if len(coords) == 0:
            return None
        dists = np.abs(coords[:, 1] - x) + np.abs(coords[:, 0] - y)
        best_idx = int(np.argmin(dists))
        by, bx = int(coords[best_idx, 0]), int(coords[best_idx, 1])
        return self.get_tile(bx, by)

    def path(
        self, start: tuple[int, int], goal: tuple[int, int], body_type: BodyType = BodyType.LAND,
    ) -> list[tuple[int, int]]:
        """Find a shortest 4-directional path from `start` to `goal` for `body_type`."""
        if not self.can_enter(*start, body_type) or not self.can_enter(*goal, body_type):
            return []
        if start == goal:
            return [start]
        queue: deque[tuple[int, int]] = deque([start])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        while queue:
            cx, cy = queue.popleft()
            if (cx, cy) == goal:
                break
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in came_from and self.can_enter(nx, ny, body_type):
                    came_from[(nx, ny)] = (cx, cy)
                    queue.append((nx, ny))
        if goal not in came_from:
            return []
        route: list[tuple[int, int]] = []
        node: tuple[int, int] | None = goal
        while node is not None:
            route.append(node)
            node = came_from[node]
        route.reverse()
        return route

    def regrow(self, multiplier: float | None = None) -> None:
        """Vectorized NumPy regrowth across all tiles."""
        mult = self.environment.regrow_multiplier() if multiplier is None else multiplier
        if mult <= 0.0:
            return
        np.minimum(self.food_max, self.food + self.food_regen * mult, out=self.food)
        np.minimum(self.wood_max, self.wood + self.wood_regen * mult, out=self.wood)

    def advance_time(self, hours: int = 1) -> None:
        if hours < 0:
            raise ValueError("hours must be non-negative")
        for _ in range(hours):
            self.environment.advance_time(1)
            self.regrow()

    def to_compact_dict(self) -> dict[str, Any]:
        """Compact viewer payload: palette + flat row-major biome IDs (fast for 200x200)."""
        return {
            "width": self.width, "height": self.height,
            "palette": {str(bid): {"name": s.name, "color": s.color} for bid, s in BIOMES_BY_ID.items()},
            "biomes": self.biome_id.ravel().tolist(),
        }
