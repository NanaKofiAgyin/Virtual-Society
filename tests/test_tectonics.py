"""Unit tests for `world/tectonics.py` and `world/erosion.py`."""

from __future__ import annotations

import numpy as np

from world.erosion import hydraulic_erosion, thermal_erosion
from world.tectonics import YEARS_PER_GEOLOGICAL_TICK, TectonicWorld


def test_same_seed_gives_identical_tectonic_world() -> None:
    """Two TectonicWorlds with the same seed produce identical plates, elevation, and timeline."""
    w1 = TectonicWorld(width=64, height=64, seed=42)
    w2 = TectonicWorld(width=64, height=64, seed=42)
    w1.step(10)
    w2.step(10)

    assert np.array_equal(w1.elevation, w2.elevation)
    assert np.array_equal(w1.plate_id, w2.plate_id)
    assert w1.sea_level == w2.sea_level
    assert w1.timeline == w2.timeline


def test_land_area_stays_within_plausible_25_to_40_percent() -> None:
    """Global land fraction stays within 25%–40% initially and over geological time."""
    for seed in (1, 42, 99):
        w = TectonicWorld(width=64, height=64, seed=seed)
        assert 8 <= len(w.plates) <= 15
        assert 0.25 <= w.land_fraction() <= 0.40
        w.step(20)
        assert 0.25 <= w.land_fraction() <= 0.40


def test_mountains_form_only_near_plate_boundaries_or_hotspots() -> None:
    """Tall mountain peaks (> 0.76) form at plate boundaries or volcanic hotspots, not interiors."""
    w = TectonicWorld(width=64, height=64, seed=7)
    # Track cumulative active boundary + hotspot zones across steps
    active_zones = np.zeros((64, 64), dtype=bool)
    for _ in range(12):
        w.step(1)
        # Expand boundary mask by 2 cells to cover folded mountain belt width
        b = w.boundary_mask | w.volcano_mask
        for _ in range(2):
            b = b | np.roll(b, 1, 0) | np.roll(b, -1, 0) | np.roll(b, 1, 1) | np.roll(b, -1, 1)
        active_zones |= b

    mountains = w.elevation > 0.76
    assert np.any(mountains), "Expected plate collisions to raise mountain belts"
    # Every raised mountain tile must lie in an active boundary/hotspot zone
    assert np.all(active_zones[mountains])


def test_erosion_never_creates_nan_or_negative_heights() -> None:
    """Thermal and hydraulic erosion never produce NaNs, infs, or negative heights."""
    rng = np.random.default_rng(123)
    h = rng.random((48, 48), dtype=np.float32)
    h[0, 0] = 0.0
    h[24, 24] = 1.0

    h = thermal_erosion(h, iterations=10)
    h = hydraulic_erosion(h, iterations=10)
    assert not np.isnan(h).any()
    assert not np.isinf(h).any()
    assert float(h.min()) >= 0.0
    assert float(h.max()) <= 1.0

    w = TectonicWorld(width=48, height=48, seed=5)
    w.fast_forward(50_000)  # 50 geological ticks = 50,000 years
    assert w.years_elapsed == 50 * YEARS_PER_GEOLOGICAL_TICK
    assert not np.isnan(w.elevation).any()
    assert float(w.elevation.min()) >= 0.0
    assert float(w.elevation.max()) <= 1.0
