"""Hydrology: distance from ocean and flow-accumulation rivers, lakes, deltas, wetlands."""

from __future__ import annotations

from collections import deque

import numpy as np


def distance_from_ocean(ocean_mask: np.ndarray, max_dist: int = 24) -> np.ndarray:
    """Compute normalized [0, 1] distance of every tile from the nearest ocean cell."""
    h, w = ocean_mask.shape
    dist = np.full((h, w), max_dist, dtype=np.int16)
    q: deque[tuple[int, int]] = deque()

    ocean_coords = np.argwhere(ocean_mask)
    for y, x in ocean_coords:
        iy, ix = int(y), int(x)
        dist[iy, ix] = 0
        q.append((iy, ix))

    while q:
        cy, cx = q.popleft()
        nd = int(dist[cy, cx]) + 1
        if nd >= max_dist:
            continue
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = cy + dy, (cx + dx) % w
            if 0 <= ny < h and dist[ny, nx] > nd:
                dist[ny, nx] = nd
                q.append((ny, nx))

    return (dist.astype(np.float32) / float(max(1, max_dist))).astype(np.float32)


def compute_flow_accumulation(
    elevation: np.ndarray,
    sea_level: float,
    rainfall_mm: np.ndarray,
    river_threshold: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Route rainfall downhill from high to low cells to form rivers, lakes, deltas, wetlands."""
    h, w = elevation.shape
    ocean = elevation <= sea_level
    flow = np.where(ocean, 0.0, np.maximum(0.1, rainfall_mm / 1000.0)).astype(np.float32)
    lakes = np.zeros((h, w), dtype=bool)
    deltas = np.zeros((h, w), dtype=bool)

    # Process land cells strictly from highest to lowest elevation (8-neighbor D8 routing)
    scale = max(1.0, (h * w) / 2500.0)
    lake_min = min(6.0, 2.5 * scale)
    delta_min = min(8.0, 3.0 * scale)
    flat_order = np.argsort(-elevation.ravel())
    for idx in flat_order:
        y, x = divmod(int(idx), w)
        if ocean[y, x]:
            continue
        cur_e = float(elevation[y, x])
        best_e = cur_e
        nxt: tuple[int, int] | None = None
        for dy in (-1, 0, 1):
            ny = y + dy
            if not (0 <= ny < h):
                continue
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                nx = (x + dx) % w
                ne = float(elevation[ny, nx])
                if ne < best_e:
                    best_e, nxt = ne, (ny, nx)
        if nxt is None:
            if flow[y, x] >= lake_min:
                lakes[y, x] = True
        else:
            ny, nx = nxt
            if ocean[ny, nx]:
                if flow[y, x] >= delta_min:
                    deltas[y, x] = True
            else:
                flow[ny, nx] += flow[y, x]

    min_river = min(8.0, 2.5 * scale)
    pct = float(np.percentile(flow[~ocean], 93)) if np.any(~ocean) else min_river
    thresh = river_threshold if river_threshold is not None else max(min_river, pct)
    rivers = (~ocean) & (~lakes) & (flow >= thresh)

    # Floodplains & wetlands: low-lying moist tiles bordering rivers or deltas
    near_river = (
        np.roll(rivers, 1, 0) | np.roll(rivers, -1, 0)
        | np.roll(rivers, 1, 1) | np.roll(rivers, -1, 1)
    )
    wetlands = deltas | ((~ocean) & near_river & (elevation < sea_level + 0.08) & (rainfall_mm > 900.0))
    return flow, rivers, lakes, wetlands
