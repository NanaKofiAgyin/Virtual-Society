"""Physical climate model: lapse rate, wind belts, rain shadows, currents, Whittaker biomes."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from world.biomes import BIOMES_BY_NAME
from world.hydrology import compute_flow_accumulation, distance_from_ocean

MAX_ELEVATION_METERS = 5500.0
LAPSE_RATE_C_PER_1000M = 6.5
GLACIAL_CYCLE_YEARS = 41_000.0


def glacial_cycle(years_elapsed: int) -> tuple[float, float]:
    """Slow glacial/interglacial Milankovitch cycle returning `(temp_shift_c, sea_level_shift)`.

    Oscillates over tens of thousands of years instead of sudden random ice ages.
    """
    phase = math.sin((2.0 * math.pi * years_elapsed) / GLACIAL_CYCLE_YEARS)
    # Interglacial: +2°C / +0.02 sea level; Glacial max: -5°C / -0.04 sea level
    temp_shift = -1.5 + 3.5 * phase
    sea_shift = -0.01 + 0.03 * phase
    return round(temp_shift, 3), round(sea_shift, 4)


def compute_temperature(
    elevation: np.ndarray,
    sea_level: float,
    ocean_dist: np.ndarray,
    season_phase: float = 0.0,
    glacial_temp_c: float = 0.0,
) -> np.ndarray:
    """Compute surface temperature (°C) from latitude, 6.5°C/1000m lapse rate, currents & distance."""
    h, w = elevation.shape
    lat_deg = np.linspace(-90.0, 90.0, h, dtype=np.float32)[:, None]
    lat_rad = np.deg2rad(lat_deg)

    # Base insolation: ~29°C at equator, ~-18°C at poles
    base_temp = -18.0 + 47.0 * np.cos(lat_rad)

    # Elevation lapse rate: 6.5°C per 1000m above sea level
    rel_alt = np.clip((elevation - sea_level) / max(0.05, 1.0 - sea_level), 0.0, 1.0)
    alt_meters = rel_alt * MAX_ELEVATION_METERS
    lapse_cooling = (alt_meters / 1000.0) * LAPSE_RATE_C_PER_1000M

    # Continental seasonal swing (ocean moderates coastal temperatures)
    hemisphere = np.sin(lat_rad)  # north vs south opposite seasons
    seasonal_swing = season_phase * hemisphere * (6.0 + 14.0 * ocean_dist)

    # Ocean currents: warm western-boundary (east coasts) & cool eastern-boundary (west coasts)
    ocean = elevation <= sea_level
    east_coast = (~ocean) & np.roll(ocean, -1, axis=1)
    west_coast = (~ocean) & np.roll(ocean, 1, axis=1)
    subtropical = (np.abs(lat_deg) >= 15.0) & (np.abs(lat_deg) <= 50.0)
    currents = np.where(east_coast & subtropical, 3.0, 0.0) - np.where(west_coast & subtropical, 3.0, 0.0)

    temp_c = base_temp - lapse_cooling + seasonal_swing + currents + glacial_temp_c
    return temp_c.astype(np.float32)


def compute_rainfall(
    elevation: np.ndarray,
    sea_level: float,
    ocean_dist: np.ndarray,
    season_phase: float = 0.0,
) -> np.ndarray:
    """Compute annual rainfall (mm) from wind belts, orographic lift, rain shadows & monsoons."""
    h, w = elevation.shape
    ocean = elevation <= sea_level
    lat_deg = np.linspace(-90.0, 90.0, h, dtype=np.float32)
    rain = np.zeros((h, w), dtype=np.float32)

    for y in range(h):
        alat = abs(float(lat_deg[y]))
        # Trade winds (<30°) & Polar easterlies (>=60°): East->West (-1); Westerlies (30-60°): West->East (+1)
        wind_dir = 1 if (30.0 <= alat < 60.0) else -1
        xs = range(w) if wind_dir == 1 else range(w - 1, -1, -1)

        # Base atmospheric moisture higher in tropics (ITCZ) and mid-latitudes
        itcz = 1.0 if alat < 20.0 else (0.75 if alat < 55.0 else 0.45)
        moisture = 0.85 * itcz

        # Two wrapping passes so moisture carries across the east-west seam
        for pass_idx in range(2):
            prev_e = max(sea_level, float(elevation[y, 0 if wind_dir == 1 else w - 1]))
            for x in xs:
                e = float(elevation[y, x])
                if ocean[y, x]:
                    moisture = min(1.0, moisture + 0.18 * itcz)
                    if pass_idx == 1:
                        rain[y, x] = moisture * 1400.0
                    prev_e = sea_level
                else:
                    climb = max(0.0, e - prev_e)
                    # Orographic lift dumps heavy rain on windward slope & dries air for rain shadow
                    orographic = climb * 6.5
                    precip = moisture * (0.065 + orographic)
                    moisture = max(0.02, moisture - precip * 0.9 - climb * 1.6)
                    if pass_idx == 1:
                        rain[y, x] = precip * 3600.0
                    prev_e = e

    # Monsoon boost in warm coastal tropics/subtropics during summer hemisphere season
    lat_col = lat_deg[:, None]
    monsoon_zone = (np.abs(lat_col) >= 8.0) & (np.abs(lat_col) <= 32.0) & (~ocean)
    monsoon_boost = np.where(monsoon_zone, max(0.0, season_phase) * (1.0 - ocean_dist) * 900.0, 0.0)
    return np.clip(rain + monsoon_boost, 0.0, 4200.0).astype(np.float32)


def whittaker_biome(
    temp_c: float,
    rain_mm: float,
    elev: float,
    sea_level: float,
    is_river: bool = False,
    is_lake: bool = False,
    is_wetland: bool = False,
) -> str:
    """Classify a tile into a biome using a Whittaker temperature-vs-rainfall diagram."""
    if elev <= sea_level:
        depth = (sea_level - elev) / max(0.05, sea_level)
        if depth > 0.42:
            return "deep_ocean"
        if temp_c > 21.0 and depth < 0.25:
            return "coral_reef"
        return "shallow_sea"
    if is_lake:
        return "lake"
    if is_river:
        return "river"
    if is_wetland:
        return "wetland"
    if elev > 0.82:
        return "glacier" if temp_c < -2.0 else "mountain"
    if elev < sea_level + 0.025 and rain_mm < 1500.0:
        return "beach"

    # Whittaker diagram: Temperature (°C) × Annual Precipitation (mm)
    if temp_c < -5.0:
        return "glacier" if rain_mm > 600.0 else "tundra"
    if temp_c < 4.0:
        return "taiga" if rain_mm >= 350.0 else "tundra"
    if temp_c < 18.0:
        if rain_mm < 260.0:
            return "desert"
        if rain_mm < 780.0:
            return "grassland"
        return "temperate_forest"
    # Warm / tropical (>= 18°C)
    if rain_mm < 320.0:
        return "desert"
    if rain_mm < 1100.0:
        return "savanna"
    return "jungle"


def plant_growth_rate(
    temp_c: np.ndarray,
    rainfall_mm: np.ndarray,
    soil_nutrients: np.ndarray,
    ocean_mask: np.ndarray,
) -> np.ndarray:
    """Compute producer growth factor [0, 1.5] from temperature, rainfall, and soil nutrients."""
    # Gaussian-like temperature curve peaking at ~20°C, falling toward 0 below -5°C or above 45°C
    temp_factor = np.clip(1.0 - ((temp_c - 20.0) / 26.0) ** 2, 0.0, 1.0)
    rain_factor = np.clip(rainfall_mm / 1600.0, 0.0, 1.2)
    nut_factor = np.clip(soil_nutrients, 0.1, 1.5)
    land_growth = temp_factor * rain_factor * nut_factor
    return np.where(ocean_mask, 0.4 * nut_factor, land_growth).astype(np.float32)


@dataclass
class ClimateState:
    """Complete physical climate, hydrology, and Whittaker biome outputs."""

    temp_c: np.ndarray
    rainfall_mm: np.ndarray
    ocean_dist: np.ndarray
    flow_acc: np.ndarray
    river_mask: np.ndarray
    lake_mask: np.ndarray
    wetland_mask: np.ndarray
    biome_id: np.ndarray
    plant_growth: np.ndarray
    effective_sea_level: float
    glacial_temp_c: float


class ClimateModel:
    """Computes full physical climate, rivers, biomes, and plant growth from elevation."""

    def compute(
        self,
        elevation: np.ndarray,
        base_sea_level: float = 0.48,
        years_elapsed: int = 0,
        season_phase: float = 0.0,
        soil_nutrients: np.ndarray | None = None,
    ) -> ClimateState:
        """Run climate, hydrology, Whittaker classification, and producer growth."""
        g_temp, g_sea = glacial_cycle(years_elapsed)
        sea_level = float(np.clip(base_sea_level + g_sea, 0.20, 0.75))
        ocean = elevation <= sea_level
        ocean_dist = distance_from_ocean(ocean)

        temp_c = compute_temperature(elevation, sea_level, ocean_dist, season_phase, g_temp)
        rain_mm = compute_rainfall(elevation, sea_level, ocean_dist, season_phase)
        flow, rivers, lakes, wetlands = compute_flow_accumulation(elevation, sea_level, rain_mm)

        h, w = elevation.shape
        biome_id = np.zeros((h, w), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                name = whittaker_biome(
                    float(temp_c[y, x]), float(rain_mm[y, x]),
                    float(elevation[y, x]), sea_level,
                    is_river=bool(rivers[y, x]), is_lake=bool(lakes[y, x]), is_wetland=bool(wetlands[y, x]),
                )
                biome_id[y, x] = BIOMES_BY_NAME[name].id

        nutrients = np.ones_like(elevation) if soil_nutrients is None else soil_nutrients
        growth = plant_growth_rate(temp_c, rain_mm, nutrients, ocean)
        return ClimateState(
            temp_c, rain_mm, ocean_dist, flow, rivers, lakes, wetlands,
            biome_id, growth, sea_level, g_temp,
        )
