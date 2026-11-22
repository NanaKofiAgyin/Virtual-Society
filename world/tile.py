"""Terrain tile view and resource container backed by data-driven biomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from world.biomes import BIOMES_BY_NAME, BiomeSpec

if TYPE_CHECKING:
    from world.map import WorldMap


class TerrainType(str, Enum):
    """All supported biomes and built structures (with legacy aliases)."""

    DEEP_OCEAN = "deep_ocean"
    SHALLOW_SEA = "shallow_sea"
    CORAL_REEF = "coral_reef"
    RIVER = "river"
    LAKE = "lake"
    WETLAND = "wetland"
    BEACH = "beach"
    DESERT = "desert"
    SAVANNA = "savanna"
    GRASSLAND = "grassland"
    TEMPERATE_FOREST = "temperate_forest"
    JUNGLE = "jungle"
    TAIGA = "taiga"
    TUNDRA = "tundra"
    MOUNTAIN = "mountain"
    GLACIER = "glacier"
    CAVE = "cave"
    FARM = "farm"
    HOUSE = "house"

    # Backwards-compatible aliases
    WATER = "shallow_sea"
    GRASS = "grassland"
    FOREST = "temperate_forest"


class ResourceType(str, Enum):
    """Harvestable resources stored on tiles."""

    FOOD = "food"
    WOOD = "wood"


@dataclass
class Tile:
    """Lightweight tile object exposing terrain, climate layers, and resources.

    When backed by a `WorldMap`, `deplete()` and `regrow()` sync directly to the
    map's NumPy arrays so 200x200 worlds remain fast and memory-efficient.
    """

    x: int
    y: int
    terrain: TerrainType
    walkable: bool
    resources: dict[ResourceType, float] = field(default_factory=dict)
    max_resources: dict[ResourceType, float] = field(default_factory=dict)
    regen_rates: dict[ResourceType, float] = field(default_factory=dict)
    elevation: float = 0.5
    temperature: float = 0.5
    moisture: float = 0.5
    ocean_depth: float = 0.0
    plants: tuple[str, ...] = ()
    _map: WorldMap | None = field(default=None, repr=False)

    @property
    def biome(self) -> BiomeSpec:
        """Return the BiomeSpec for this tile's terrain."""
        return BIOMES_BY_NAME[self.terrain.value]

    @classmethod
    def from_terrain(cls, x: int, y: int, terrain: TerrainType | str) -> Tile:
        """Create a standalone tile initialized from `data/biomes.json`."""
        t = TerrainType(terrain)
        spec = BIOMES_BY_NAME[t.value]
        return cls(
            x=x, y=y, terrain=t, walkable=spec.walkable,
            resources={ResourceType.FOOD: spec.food_max, ResourceType.WOOD: spec.wood_max},
            max_resources={ResourceType.FOOD: spec.food_max, ResourceType.WOOD: spec.wood_max},
            regen_rates={ResourceType.FOOD: spec.food_regen, ResourceType.WOOD: spec.wood_regen},
            plants=spec.plants,
        )

    def get_resource(self, resource: ResourceType | str) -> float:
        res_type = ResourceType(resource)
        return self.resources.get(res_type, 0.0)

    def deplete(self, resource: ResourceType | str, amount: float) -> float:
        """Deplete up to `amount` of a resource and sync back to the map array if attached."""
        if amount <= 0.0:
            return 0.0
        res_type = ResourceType(resource)
        available = self.resources.get(res_type, 0.0)
        taken = min(available, amount)
        new_val = available - taken
        self.resources[res_type] = new_val
        if self._map is not None:
            arr = self._map.food if res_type is ResourceType.FOOD else self._map.wood
            arr[self.y, self.x] = new_val
        return taken

    def regrow(self, multiplier: float = 1.0) -> None:
        """Regrow tile resources scaled by `multiplier`, capped at max capacity."""
        if multiplier <= 0.0:
            return
        for res_type, rate in self.regen_rates.items():
            if rate <= 0.0:
                continue
            current = self.resources.get(res_type, 0.0)
            maximum = self.max_resources.get(res_type, 0.0)
            if current < maximum:
                new_val = min(maximum, current + rate * multiplier)
                self.resources[res_type] = new_val
                if self._map is not None:
                    arr = self._map.food if res_type is ResourceType.FOOD else self._map.wood
                    arr[self.y, self.x] = new_val

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x, "y": self.y, "terrain": self.terrain.value,
            "walkable": self.walkable,
            "elevation": round(self.elevation, 2),
            "temperature": round(self.temperature, 2),
            "moisture": round(self.moisture, 2),
            "plants": list(self.plants),
            "resources": {res.value: round(val, 2) for res, val in self.resources.items()},
        }
