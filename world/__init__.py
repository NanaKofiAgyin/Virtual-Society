"""World package: layered NumPy maps, 17 biomes, body-type movement, climate & events."""

from world.biomes import BIOMES_BY_ID, BIOMES_BY_NAME, BiomeSpec, BodyType, can_traverse, load_biomes
from world.environment import Environment, Season, TimeOfDay, Weather, WorldEventSpec, load_events
from world.map import WorldMap
from world.tile import ResourceType, TerrainType, Tile

__all__ = [
    "BIOMES_BY_ID", "BIOMES_BY_NAME", "BiomeSpec", "BodyType", "Environment",
    "ResourceType", "Season", "TerrainType", "Tile", "TimeOfDay", "Weather",
    "WorldEventSpec", "WorldMap", "can_traverse", "load_biomes", "load_events",
]
