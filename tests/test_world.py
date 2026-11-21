"""Unit tests for the `world` package (tiles, map, pathfinding, environment)."""

from __future__ import annotations

from collections import Counter

import pytest

from world import (
    Environment,
    ResourceType,
    Season,
    TerrainType,
    Tile,
    TimeOfDay,
    Weather,
    WorldMap,
)


def test_same_seed_gives_same_map_and_weather() -> None:
    """Identical seeds must produce identical terrain grids and environment history."""
    world_a = WorldMap(width=30, height=30, seed=12345)
    world_b = WorldMap(width=30, height=30, seed=12345)

    for y in range(30):
        for x in range(30):
            tile_a = world_a.get_tile(x, y)
            tile_b = world_b.get_tile(x, y)
            assert tile_a is not None and tile_b is not None
            assert tile_a.terrain == tile_b.terrain
            assert tile_a.resources == tile_b.resources

    world_a.advance_time(hours=48)
    world_b.advance_time(hours=48)
    assert world_a.environment.to_dict() == world_b.environment.to_dict()


def test_quantile_terrain_proportions_are_stable() -> None:
    """Generated map should match ~12% water, ~43% grass, ~33% forest, ~12% mountain."""
    world = WorldMap(width=50, height=50, seed=42)
    total = world.width * world.height
    counts = Counter(tile.terrain for row in world.tiles for tile in row)

    assert counts[TerrainType.WATER] / total == pytest.approx(0.12, abs=0.01)
    assert counts[TerrainType.GRASS] / total == pytest.approx(0.43, abs=0.01)
    assert counts[TerrainType.FOREST] / total == pytest.approx(0.33, abs=0.01)
    assert counts[TerrainType.MOUNTAIN] / total == pytest.approx(0.12, abs=0.01)


def test_walkability_and_tile_resource_amounts() -> None:
    """Only grass, forest, farm, and house are walkable; initial resources match spec."""
    walkable_types = {TerrainType.GRASS, TerrainType.FOREST, TerrainType.FARM, TerrainType.HOUSE}
    for terrain in TerrainType:
        tile = Tile.from_terrain(0, 0, terrain)
        assert tile.walkable is (terrain in walkable_types)

    assert Tile.from_terrain(0, 0, TerrainType.GRASS).get_resource(ResourceType.FOOD) == 1.0
    assert Tile.from_terrain(0, 0, TerrainType.GRASS).get_resource(ResourceType.WOOD) == 0.0
    assert Tile.from_terrain(0, 0, TerrainType.FOREST).get_resource(ResourceType.FOOD) == 3.0
    assert Tile.from_terrain(0, 0, TerrainType.FOREST).get_resource(ResourceType.WOOD) == 5.0
    assert Tile.from_terrain(0, 0, TerrainType.FARM).get_resource(ResourceType.FOOD) == 6.0


def test_place_village_near_center() -> None:
    """place_village places the requested number of houses and farms near the map center."""
    world = WorldMap(width=20, height=20, seed=7)
    placed = world.place_village(n_houses=4, n_farms=5)

    assert len(placed) == 9
    houses = [t for row in world.tiles for t in row if t.terrain == TerrainType.HOUSE]
    farms = [t for row in world.tiles for t in row if t.terrain == TerrainType.FARM]
    assert len(houses) == 4
    assert len(farms) == 5
    # Verify placed tiles are close to center (10, 10)
    assert all(abs(t.x - 10) + abs(t.y - 10) <= 6 for t in placed)


def test_get_nearby_and_find_nearest_resource() -> None:
    """get_nearby returns radius neighbors and find_nearest locates closest resource."""
    world = WorldMap(width=10, height=10, seed=3)
    assert len(world.get_nearby(5, 5, radius=1)) == 8
    assert len(world.get_nearby(0, 0, radius=1)) == 3

    nearest_wood = world.find_nearest(5, 5, ResourceType.WOOD)
    assert nearest_wood is not None
    assert nearest_wood.get_resource(ResourceType.WOOD) > 0.0

    # Depleting that tile causes find_nearest to skip it
    nearest_wood.deplete(ResourceType.WOOD, 999.0)
    next_wood = world.find_nearest(5, 5, ResourceType.WOOD)
    assert next_wood is None or (next_wood.x, next_wood.y) != (nearest_wood.x, nearest_wood.y)


def test_bfs_pathfinding_avoids_obstacles_and_handles_blocked() -> None:
    """BFS path() routes around non-walkable tiles and returns [] when blocked."""
    world = WorldMap(width=5, height=5, seed=1)
    # Build a clean grass grid with a vertical mountain wall leaving a gap at y=4
    for y in range(5):
        for x in range(5):
            world.tiles[y][x] = Tile.from_terrain(x, y, TerrainType.GRASS)
    for y in range(4):
        world.tiles[y][2] = Tile.from_terrain(2, y, TerrainType.MOUNTAIN)

    route = world.path((0, 0), (4, 0))
    assert route[0] == (0, 0)
    assert route[-1] == (4, 0)
    assert all(world.get_tile(x, y).walkable for x, y in route)  # type: ignore[union-attr]
    # Adjacent steps are 4-directional (Manhattan distance 1)
    for (x1, y1), (x2, y2) in zip(route, route[1:]):
        assert abs(x1 - x2) + abs(y1 - y2) == 1

    # Seal the gap -> path should become unreachable
    world.tiles[4][2] = Tile.from_terrain(2, 4, TerrainType.WATER)
    assert world.path((0, 0), (4, 0)) == []


def test_seasons_advance_every_7_days_and_summer_regrows_faster_than_winter() -> None:
    """Environment advances 7-day seasons, 6-tick weather, and winter regrows slower than summer."""
    env = Environment(seed=11)
    assert env.season == Season.SPRING
    assert env.time_of_day == TimeOfDay.DAWN

    # 7 days * 24 hours = 168 ticks -> Summer (starts at hour 6, so 168 ticks = Day 1 of Summer)
    env.advance_time(24 * 7)
    assert env.season == Season.SUMMER
    summer_mult = env.regrow_multiplier()

    env.advance_time(24 * 7)
    assert env.season == Season.AUTUMN

    env.advance_time(24 * 7)
    assert env.season == Season.WINTER
    winter_mult = env.regrow_multiplier()
    assert summer_mult > winter_mult

    # One more season rolls into Year 2 Spring
    env.advance_time(24 * 7)
    assert env.season == Season.SPRING
    assert env.year == 2
    assert env.weather in set(Weather)


def test_world_regrow_restores_depleted_tiles() -> None:
    """WorldMap.regrow() restores depleted resources according to multiplier."""
    world = WorldMap(width=10, height=10, seed=5)
    world.place_village(n_houses=1, n_farms=1)
    farm = next(t for row in world.tiles for t in row if t.terrain == TerrainType.FARM)

    farm.deplete(ResourceType.FOOD, 5.0)
    before = farm.get_resource(ResourceType.FOOD)
    world.regrow(multiplier=1.5)
    assert farm.get_resource(ResourceType.FOOD) > before
