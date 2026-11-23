"""Vectorized thermal & hydraulic erosion and wrapping continent counting."""

from __future__ import annotations

from collections import deque

import numpy as np


def thermal_erosion(
    height: np.ndarray,
    talus: float = 0.035,
    rate: float = 0.25,
    iterations: int = 2,
) -> np.ndarray:
    """Crumble slopes steeper than `talus` onto lower 4-neighbors (wrapping world)."""
    h = np.array(height, dtype=np.float32, copy=True)
    shifts = ((-1, 0), (1, 0), (0, -1), (0, 1))
    for _ in range(iterations):
        delta = np.zeros_like(h)
        for dy, dx in shifts:
            nb = np.roll(np.roll(h, -dy, axis=0), -dx, axis=1)
            diff = h - nb
            excess = np.where(diff > talus, (diff - talus) * rate * 0.25, 0.0)
            delta -= excess
            delta += np.roll(np.roll(excess, dy, axis=0), dx, axis=1)
        h = np.clip(np.nan_to_num(h + delta, nan=0.0), 0.0, 1.0)
    return h


def hydraulic_erosion(
    height: np.ndarray,
    sea_level: float = 0.48,
    rainfall: float = 0.02,
    deposit_rate: float = 0.35,
    iterations: int = 2,
) -> np.ndarray:
    """Carve valleys on steep land slopes and deposit sediment into flatter lowlands/deltas."""
    h = np.array(height, dtype=np.float32, copy=True)
    shifts = ((-1, 0), (1, 0), (0, -1), (0, 1))
    for _ in range(iterations):
        nbs = [np.roll(np.roll(h, -dy, axis=0), -dx, axis=1) for dy, dx in shifts]
        min_nb = np.minimum(np.minimum(nbs[0], nbs[1]), np.minimum(nbs[2], nbs[3]))
        slope = np.maximum(0.0, h - min_nb)
        above_sea = h > sea_level

        carved = np.where(above_sea & (slope > 0.015), slope * rainfall * 2.5, 0.0)
        h -= carved

        # Deposit carried sediment onto lower neighbors (valleys & coastal deltas)
        sediment = carved * deposit_rate
        for dy, dx in shifts:
            nb = np.roll(np.roll(h, -dy, axis=0), -dx, axis=1)
            receives = (nb <= min_nb + 1e-4)
            moved = np.where(receives, sediment * 0.25, 0.0)
            h += np.roll(np.roll(moved, dy, axis=0), dx, axis=1)

        h = np.clip(np.nan_to_num(h, nan=0.0), 0.0, 1.0)
    return h


def count_continents(land_mask: np.ndarray, min_tiles: int = 12) -> int:
    """Count distinct connected landmasses (>= `min_tiles`) with horizontal wrapping."""
    h, w = land_mask.shape
    visited = np.zeros((h, w), dtype=bool)
    continents = 0
    for y in range(h):
        for x in range(w):
            if not land_mask[y, x] or visited[y, x]:
                continue
            visited[y, x] = True
            q: deque[tuple[int, int]] = deque([(y, x)])
            size = 0
            while q:
                cy, cx = q.popleft()
                size += 1
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = cy + dy, (cx + dx) % w
                    if 0 <= ny < h and land_mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((ny, nx))
            if size >= min_tiles:
                continents += 1
    return continents
