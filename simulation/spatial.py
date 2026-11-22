"""Spatial hash grid for O(1) amortized neighborhood and viewport queries."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base import Agent


class SpatialHashGrid:
    """Partitions 2D world coordinates into fixed-size buckets for fast proximity lookups."""

    def __init__(self, cell_size: int = 8) -> None:
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = cell_size
        self._buckets: dict[tuple[int, int], list[Agent]] = defaultdict(list)

    def clear(self) -> None:
        """Remove all agents from the grid."""
        self._buckets.clear()

    def _cell(self, x: int, y: int) -> tuple[int, int]:
        return (x // self.cell_size, y // self.cell_size)

    def insert(self, agent: Agent) -> None:
        """Insert a single alive agent into its spatial bucket."""
        if agent.alive:
            self._buckets[self._cell(agent.x, agent.y)].append(agent)

    def rebuild(self, agents: list[Agent]) -> None:
        """Clear and bulk-insert all alive agents."""
        self._buckets.clear()
        cs = self.cell_size
        buckets = self._buckets
        for agent in agents:
            if agent.alive:
                buckets[(agent.x // cs, agent.y // cs)].append(agent)

    def query_radius(self, x: int, y: int, radius: int) -> list[Agent]:
        """Return all alive agents within Manhattan/Chebyshev `radius` of `(x, y)`."""
        cs = self.cell_size
        min_cx, max_cx = (x - radius) // cs, (x + radius) // cs
        min_cy, max_cy = (y - radius) // cs, (y + radius) // cs
        found: list[Agent] = []
        for cy in range(min_cy, max_cy + 1):
            for cx in range(min_cx, max_cx + 1):
                bucket = self._buckets.get((cx, cy))
                if not bucket:
                    continue
                for a in bucket:
                    if abs(a.x - x) <= radius and abs(a.y - y) <= radius:
                        found.append(a)
        return found

    def query_rect(self, min_x: int, min_y: int, max_x: int, max_y: int) -> list[Agent]:
        """Return all alive agents inside the axis-aligned rectangle (e.g., camera view)."""
        cs = self.cell_size
        found: list[Agent] = []
        for cy in range(min_y // cs, max_y // cs + 1):
            for cx in range(min_x // cs, max_x // cs + 1):
                for a in self._buckets.get((cx, cy), ()):
                    if min_x <= a.x <= max_x and min_y <= a.y <= max_y:
                        found.append(a)
        return found
