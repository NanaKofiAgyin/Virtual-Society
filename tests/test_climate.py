"""Unit tests for `world/climate.py` and `world/hydrology.py`."""

from __future__ import annotations

import numpy as np
import pytest

from world.climate import (
    ClimateModel,
    compute_rainfall,
    compute_temperature,
    glacial_cycle,
    plant_growth_rate,
    whittaker_biome,
)
from world.environment import load_events
from world.tectonics import TectonicWorld


def test_lapse_rate_cools_temperature_with_elevation() -> None:
    """Raising elevation by ~1,000m cools temperature by ~6.5°C."""
    sea = 0.40
    elev_low = np.full((20, 20), 0.45, dtype=np.float32)
    # +1000m in normalized elevation units = (1000 / 5500) * (1 - sea)
    elev_high = elev_low + np.float32((1000.0 / 5500.0) * (1.0 - sea))
    dist = np.full((20, 20), 0.5, dtype=np.float32)

    t_low = compute_temperature(elev_low, sea, dist)
    t_high = compute_temperature(elev_high, sea, dist)
    assert float((t_low - t_high).mean()) == pytest.approx(6.5, abs=0.2)


def test_westerlies_create_rain_shadow_behind_mountain_range() -> None:
    """In mid-latitude westerlies (West->East), rain is heavy west of mountains and dry east."""
    h, w = 40, 40
    elev = np.full((h, w), 0.52, dtype=np.float32)
    elev[:, :8] = 0.20  # western ocean supplying moist air
    # North-south mountain barrier at x=18..20
    elev[:, 18:21] = 0.90
    dist = np.full((h, w), 0.4, dtype=np.float32)

    rain = compute_rainfall(elev, sea_level=0.45, ocean_dist=dist)
    # Mid-latitude rows (around 45° latitude -> y ~ 8..12) have westerlies blowing West -> East
    windward = float(rain[8:13, 17:19].mean())
    leeward = float(rain[8:13, 22:28].mean())
    assert windward > leeward * 2.0, f"Expected rain shadow: windward={windward:.0f}mm vs leeward={leeward:.0f}mm"


def test_whittaker_biome_diagram_classifications() -> None:
    """Whittaker diagram maps temperature and rainfall to expected biomes."""
    assert whittaker_biome(temp_c=28.0, rain_mm=100.0, elev=0.55, sea_level=0.45) == "desert"
    assert whittaker_biome(temp_c=26.0, rain_mm=2400.0, elev=0.55, sea_level=0.45) == "jungle"
    assert whittaker_biome(temp_c=24.0, rain_mm=700.0, elev=0.55, sea_level=0.45) == "savanna"
    assert whittaker_biome(temp_c=12.0, rain_mm=1200.0, elev=0.55, sea_level=0.45) == "temperate_forest"
    assert whittaker_biome(temp_c=12.0, rain_mm=500.0, elev=0.55, sea_level=0.45) == "grassland"
    assert whittaker_biome(temp_c=-1.0, rain_mm=500.0, elev=0.55, sea_level=0.45) == "taiga"
    assert whittaker_biome(temp_c=-8.0, rain_mm=200.0, elev=0.55, sea_level=0.45) == "tundra"
    assert whittaker_biome(temp_c=-10.0, rain_mm=900.0, elev=0.55, sea_level=0.45) == "glacier"


def test_glacial_cycles_rivers_and_plant_growth() -> None:
    """Slow glacial cycles shift temperature/sea level; flow accumulation creates rivers; plants respond."""
    t_warm, s_warm = glacial_cycle(10_250)  # peak interglacial
    t_cold, s_cold = glacial_cycle(30_750)  # peak glacial
    assert t_warm > t_cold + 5.0
    assert s_warm > s_cold + 0.04

    tec = TectonicWorld(width=48, height=48, seed=42)
    tec.step(5)
    model = ClimateModel()
    state = model.compute(tec.elevation, base_sea_level=tec.sea_level, years_elapsed=10_250)
    assert np.any(state.river_mask)
    assert state.biome_id.shape == (48, 48)

    # Plants grow faster in warm+rainy+fertile conditions than cold+dry
    g_rich = plant_growth_rate(np.array([[22.0]]), np.array([[1500.0]]), np.array([[1.2]]), np.array([[False]]))
    g_poor = plant_growth_rate(np.array([[-4.0]]), np.array([[100.0]]), np.array([[0.3]]), np.array([[False]]))
    assert float(g_rich[0, 0]) > float(g_poor[0, 0]) * 5.0

    # Random sudden ice_age removed from events.json; fire & drought are rare
    events = load_events()
    assert "ice_age" not in events
    assert events["fire"].chance < 0.002
    assert events["drought"].chance < 0.002
