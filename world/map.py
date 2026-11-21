"""2D world map: smoothed quantile noise generation, village placement, and BFS pathfinding."""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from world.environment import Environment
from world.tile import ResourceType, TerrainType, Tile

# Target terrain quantiles: 12% water, 43% grass, 33% forest, 12% mountain
QUANTILE_WATER = 0.12
QUANTILE_GRASS = 0.55
QUANTILE_FOREST = 0.88


class WorldMap:
    """Seeded, reproducible 2D tile grid with pathfinding, queries, and regrowth."""

    def __init__(
        self,
        width: int = 50,
        height: int = 50,
        seed: int | None = None,
        smooth_passes: int = 4,
    ) -> None:
        """Generate a `width x height` map using smoothed seeded noise and quantiles."""
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive integers")

        self.width = width
        self.height = height
        self.seed = seed
        self.rng = random.Random(seed)
        self.environment = Environment(rng=self.rng)
        self.tiles: list[list[Tile]] = []

        self._generate_grid(smooth_passes=smooth_passes)

    def _generate_grid(self, smooth_passes: int) -> None:
        """Generate terrain via smoothed random noise partitioned by quantiles."""
        noise = [
            [self.rng.random() for _ in range(self.width)]
            for _ in range(self.height)
        ]

        for _ in range(smooth_passes):
            smoothed: list[list[float]] = []
            for y in range(self.height):
                row: list[float] = []
                for x in range(self.width):
                    total = 0.0
                    count = 0
                    for ny in range(max(0, y - 1), min(self.height, y + 2)):
                        for nx in range(max(0, x - 1), min(self.width, x + 2)):
                            total += noise[ny][nx]
                            count += 1
                    row.append(total / count)
                smoothed.append(row)
            noise = smoothed

        # Rank every cell so terrain proportions match exact quantiles regardless of seed
        ranked = sorted(
            (noise[y][x], y, x)
            for y in range(self.height)
            for x in range(self.width)
        )
        total_cells = len(ranked)
        water_cut = int(total_cells * QUANTILE_WATER)
        grass_cut = int(total_cells * QUANTILE_GRASS)
        forest_cut = int(total_cells * QUANTILE_FOREST)

        terrain_grid: list[list[TerrainType]] = [
            [TerrainType.GRASS for _ in range(self.width)]
            for _ in range(self.height)
        ]
        for idx, (_, y, x) in enumerate(ranked):
            if idx < water_cut:
                terrain_grid[y][x] = TerrainType.WATER
            elif idx < grass_cut:
                terrain_grid[y][x] = TerrainType.GRASS
            elif idx < forest_cut:
                terrain_grid[y][x] = TerrainType.FOREST
            else:
                terrain_grid[y][x] = TerrainType.MOUNTAIN

        self.tiles = [
            [
                Tile.from_terrain(x=x, y=y, terrain=terrain_grid[y][x])
                for x in range(self.width)
            ]
            for y in range(self.height)
        ]

    def place_village(self, n_houses: int = 5, n_farms: int = 6) -> list[Tile]:
        """Place `n_houses` houses and `n_farms` farms near the map center."""
        cx, cy = self.width // 2, self.height // 2
        candidates = sorted(
            ((x, y) for y in range(self.height) for x in range(self.width)),
            key=lambda pos: ((pos[0] - cx) ** 2 + (pos[1] - cy) ** 2, pos[1], pos[0]),
        )
        # Prefer walkable tiles near center; fall back to any tile if map is tiny
        ordered = [p for p in candidates if self.tiles[p[1]][p[0]].walkable]
        if len(ordered) < n_houses + n_farms:
            ordered = candidates

        placed: list[Tile] = []
        for idx, (x, y) in enumerate(ordered[: n_houses + n_farms]):
            terrain = TerrainType.HOUSE if idx < n_houses else TerrainType.FARM
            tile = Tile.from_terrain(x=x, y=y, terrain=terrain)
            self.tiles[y][x] = tile
            placed.append(tile)
        return placed

    def in_bounds(self, x: int, y: int) -> bool:
        """Return True if (x, y) lies inside the grid boundaries."""
        return 0 <= x < self.width and 0 <= y < self.height

    def get_tile(self, x: int, y: int) -> Tile | None:
        """Return the Tile at (x, y), or None if out of bounds."""
        if not self.in_bounds(x, y):
            return None
        return self.tiles[y][x]

    def get_nearby(
        self,
        x: int,
        y: int,
        radius: int,
        include_self: bool = False,
    ) -> list[Tile]:
        """Return all in-bounds tiles within Chebyshev `radius` of (x, y)."""
        if radius < 0:
            raise ValueError("radius must be non-negative")

        nearby: list[Tile] = []
        for ty in range(max(0, y - radius), min(self.height, y + radius + 1)):
            for tx in range(max(0, x - radius), min(self.width, x + radius + 1)):
                if not include_self and tx == x and ty == y:
                    continue
                nearby.append(self.tiles[ty][tx])
        return nearby

    def find_nearest(
        self,
        x: int,
        y: int,
        resource: ResourceType | str,
        min_amount: float = 0.01,
    ) -> Tile | None:
        """Return the closest tile containing at least `min_amount` of `resource`."""
        res_type = ResourceType(resource)
        best_tile: Tile | None = None
        best_key: tuple[int, int, int] | None = None

        for row in self.tiles:
            for tile in row:
                if tile.get_resource(res_type) < min_amount:
                    continue
                dist = abs(tile.x - x) + abs(tile.y - y)
                key = (dist, tile.y, tile.x)
                if best_key is None or key < best_key:
                    best_key = key
                    best_tile = tile
        return best_tile

    def path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> list[tuple[int, int]]:
        """Find a shortest 4-directional walkable path from `start` to `goal` via BFS.

        Returns a list of (x, y) coordinates from start to goal inclusive,
        or an empty list if no walkable path exists.
        """
        start_tile = self.get_tile(*start)
        goal_tile = self.get_tile(*goal)
        if start_tile is None or goal_tile is None:
            return []
        if not start_tile.walkable or not goal_tile.walkable:
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
                if (nx, ny) in came_from:
                    continue
                neighbor = self.get_tile(nx, ny)
                if neighbor is not None and neighbor.walkable:
                    came_from[(nx, ny)] = (cx, cy)
                    queue.append((nx, ny))

        if goal not in came_from:
            return []

        result: list[tuple[int, int]] = []
        node: tuple[int, int] | None = goal
        while node is not None:
            result.append(node)
            node = came_from[node]
        result.reverse()
        return result

    def regrow(self, multiplier: float | None = None) -> None:
        """Regrow resources on every tile using `multiplier` (or current environment)."""
        mult = self.environment.regrow_multiplier() if multiplier is None else multiplier
        for row in self.tiles:
            for tile in row:
                tile.regrow(multiplier=mult)

    def advance_time(self, hours: int = 1) -> None:
        """Advance clock by `hours` (1 tick = 1 hour) and regrow resources each hour."""
        if hours < 0:
            raise ValueError("hours must be non-negative")
        for _ in range(hours):
            self.environment.advance_time(1)
            self.regrow()

    def to_dict(self) -> dict[str, Any]:
        """Serialize world map and environment state to a JSON-friendly dictionary."""
        return {
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
            "environment": self.environment.to_dict(),
            "tiles": [[tile.to_dict() for tile in row] for row in self.tiles],
        }
