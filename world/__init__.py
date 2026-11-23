"""World package: layered NumPy maps, 17 biomes, body-type movement, climate & events."""

from world.biomes import BIOMES_BY_ID, BIOMES_BY_NAME, BiomeSpec, BodyType, can_traverse, load_biomes
from world.climate import ClimateModel, ClimateState, glacial_cycle, whittaker_biome
from world.environment import Environment, Season, TimeOfDay, Weather, WorldEventSpec, load_events
from world.map import WorldMap
from world.tectonics import YEARS_PER_GEOLOGICAL_TICK, Plate, TectonicWorld
from world.tile import ResourceType, TerrainType, Tile

__all__ = [
    "BIOMES_BY_ID", "BIOMES_BY_NAME", "BiomeSpec", "BodyType", "ClimateModel",
    "ClimateState", "Environment", "Plate", "ResourceType", "Season",
    "TectonicWorld", "TerrainType", "Tile", "TimeOfDay", "Weather",
    "WorldEventSpec", "WorldMap", "YEARS_PER_GEOLOGICAL_TICK",
    "can_traverse", "glacial_cycle", "load_biomes", "load_events", "whittaker_biome",
]
