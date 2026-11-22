"""Unit tests for the layered 200x200 NumPy `world` package, biomes, body types, and events."""

from __future__ import annotations

import numpy as np
import pytest

from world import (
    BIOMES_BY_ID,
    BIOMES_BY_NAME,
    BodyType,
    Environment,
    ResourceType,
    Season,
    TerrainType,
    Tile,
    TimeOfDay,
    Weather,
    WorldMap,
    can_traverse,
    load_events,
)


def test_default_200x200_layered_map_and_reproducibility() -> None:
    """Default WorldMap is 200x200 with NumPy climate/elevation layers and deterministic seed."""
    world = WorldMap(seed=42)
    assert (world.width, world.height) == (200, 200)
    assert world.elevation.shape == (200, 200)
    assert world.temperature.shape == (200, 200)
    assert world.moisture.shape == (200, 200)
    assert world.ocean_depth.shape == (200, 200)
    assert world.biome_id.dtype == np.uint8

    # Equator (middle rows) should be warmer than poles (top/bottom rows)
    equator_temp = float(world.temperature[90:110, :].mean())
    pole_temp = float(world.temperature[:15, :].mean())
    assert equator_temp > pole_temp + 0.15

    # Same seed produces identical biome grid
    w1 = WorldMap(width=40, height=40, seed=123)
    w2 = WorldMap(width=40, height=40, seed=123)
    assert np.array_equal(w1.biome_id, w2.biome_id)
    assert np.array_equal(w1.elevation, w2.elevation)


def test_diverse_biomes_and_rivers_generated() -> None:
    """A 200x200 world generates ocean, land biomes, mountains, and rivers."""
    world = WorldMap(width=200, height=200, seed=7)
    present = {BIOMES_BY_ID[int(bid)].name for bid in np.unique(world.biome_id)}
    assert len(present) >= 8
    assert "deep_ocean" in present or "shallow_sea" in present
    assert "river" in present


def test_body_type_movement_rules_and_pathfinding() -> None:
    """Movement & BFS pathfinding respect land, aquatic, amphibian, flying, and burrower rules."""
    assert can_traverse(BIOMES_BY_NAME["grassland"], BodyType.LAND) is True
    assert can_traverse(BIOMES_BY_NAME["deep_ocean"], BodyType.LAND) is False
    assert can_traverse(BIOMES_BY_NAME["deep_ocean"], BodyType.AQUATIC) is True
    assert can_traverse(BIOMES_BY_NAME["river"], BodyType.AQUATIC) is True
    assert can_traverse(BIOMES_BY_NAME["grassland"], BodyType.AQUATIC) is False
    assert can_traverse(BIOMES_BY_NAME["deep_ocean"], BodyType.AMPHIBIAN) is True
    assert can_traverse(BIOMES_BY_NAME["grassland"], BodyType.AMPHIBIAN) is True
    assert can_traverse(BIOMES_BY_NAME["mountain"], BodyType.FLYING) is True
    assert can_traverse(BIOMES_BY_NAME["grassland"], BodyType.BURROWER) is True
    assert can_traverse(BIOMES_BY_NAME["mountain"], BodyType.BURROWER) is False

    world = WorldMap(width=5, height=5, seed=1)
    for y in range(5):
        for x in range(5):
            world.set_terrain(x, y, TerrainType.GRASSLAND)
    for y in range(4):
        world.set_terrain(2, y, TerrainType.MOUNTAIN)

    route = world.path((0, 0), (4, 0), body_type=BodyType.LAND)
    assert route[0] == (0, 0) and route[-1] == (4, 0)
    assert all(world.can_enter(x, y, BodyType.LAND) for x, y in route)

    # Seal gap with river -> land blocked, amphibian & flying pass
    world.set_terrain(2, 4, TerrainType.RIVER)
    assert world.path((0, 0), (4, 0), body_type=BodyType.LAND) == []
    assert len(world.path((0, 0), (4, 0), body_type=BodyType.AMPHIBIAN)) > 0
    assert len(world.path((0, 0), (4, 0), body_type=BodyType.FLYING)) > 0


def test_place_village_find_nearest_and_vectorized_regrow() -> None:
    """place_village, find_nearest, depletion, and NumPy regrow work cleanly."""
    world = WorldMap(width=30, height=30, seed=5)
    placed = world.place_village(n_houses=4, n_farms=5)
    assert len(placed) == 9

    farm = next(t for t in placed if t.terrain is TerrainType.FARM)
    farm.deplete(ResourceType.FOOD, 4.0)
    after_deplete = world.get_tile(farm.x, farm.y).get_resource(ResourceType.FOOD)  # type: ignore[union-attr]
    assert after_deplete == pytest.approx(2.0)

    world.regrow(multiplier=1.5)
    assert world.get_tile(farm.x, farm.y).get_resource(ResourceType.FOOD) > after_deplete  # type: ignore[union-attr]

    nearest = world.find_nearest(15, 15, ResourceType.FOOD)
    assert nearest is not None and nearest.get_resource(ResourceType.FOOD) > 0.0


def test_seasons_climate_shifts_tides_and_data_events() -> None:
    """Seasons shift temperature/rainfall, tides oscillate, and events load from data/events.json."""
    events = load_events()
    assert {"drought", "flood", "fire", "ice_age", "volcano", "disease_outbreak"}.issubset(events.keys())

    env = Environment(seed=11)
    assert env.season is Season.SPRING and env.time_of_day is TimeOfDay.DAWN
    tides = [env.tide_level()]

    env.advance_time(24 * 7)
    assert env.season is Season.SUMMER
    summer_temp, summer_regrow = env.temp_offset(), env.regrow_multiplier()

    env.advance_time(24 * 14)
    assert env.season is Season.WINTER
    assert summer_temp > env.temp_offset()
    assert summer_regrow > env.regrow_multiplier()

    env.advance_time(3)
    tides.append(env.tide_level())
    assert tides[0] != tides[1]
    assert env.weather in set(Weather)
