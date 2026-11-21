"""Terrain tile definitions and per-tile resource containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TerrainType(str, Enum):
    """Supported terrain types for world tiles."""

    WATER = "water"
    GRASS = "grass"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    FARM = "farm"
    HOUSE = "house"


class ResourceType(str, Enum):
    """Harvestable resources stored on tiles."""

    FOOD = "food"
    WOOD = "wood"


@dataclass(frozen=True)
class ResourceSpec:
    """Initial/maximum amount and base per-tick regrowth rate."""

    maximum: float
    regen_rate: float


@dataclass(frozen=True)
class TerrainSpec:
    """Default walkability and resource capacities for a terrain type."""

    walkable: bool
    resources: dict[ResourceType, ResourceSpec]


TERRAIN_SPECS: dict[TerrainType, TerrainSpec] = {
    TerrainType.WATER: TerrainSpec(
        walkable=False,
        resources={
            ResourceType.FOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
            ResourceType.WOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
        },
    ),
    TerrainType.GRASS: TerrainSpec(
        walkable=True,
        resources={
            ResourceType.FOOD: ResourceSpec(maximum=1.0, regen_rate=0.10),
            ResourceType.WOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
        },
    ),
    TerrainType.FOREST: TerrainSpec(
        walkable=True,
        resources={
            ResourceType.FOOD: ResourceSpec(maximum=3.0, regen_rate=0.20),
            ResourceType.WOOD: ResourceSpec(maximum=5.0, regen_rate=0.25),
        },
    ),
    TerrainType.MOUNTAIN: TerrainSpec(
        walkable=False,
        resources={
            ResourceType.FOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
            ResourceType.WOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
        },
    ),
    TerrainType.FARM: TerrainSpec(
        walkable=True,
        resources={
            ResourceType.FOOD: ResourceSpec(maximum=6.0, regen_rate=0.40),
            ResourceType.WOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
        },
    ),
    TerrainType.HOUSE: TerrainSpec(
        walkable=True,
        resources={
            ResourceType.FOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
            ResourceType.WOOD: ResourceSpec(maximum=0.0, regen_rate=0.0),
        },
    ),
}


@dataclass
class Tile:
    """A single cell in the 2D world grid."""

    x: int
    y: int
    terrain: TerrainType
    walkable: bool
    resources: dict[ResourceType, float] = field(default_factory=dict)
    max_resources: dict[ResourceType, float] = field(default_factory=dict)
    regen_rates: dict[ResourceType, float] = field(default_factory=dict)

    @classmethod
    def from_terrain(cls, x: int, y: int, terrain: TerrainType) -> Tile:
        """Create a tile initialized with default walkability and resources."""
        spec = TERRAIN_SPECS[terrain]
        return cls(
            x=x,
            y=y,
            terrain=terrain,
            walkable=spec.walkable,
            resources={res: rspec.maximum for res, rspec in spec.resources.items()},
            max_resources={res: rspec.maximum for res, rspec in spec.resources.items()},
            regen_rates={res: rspec.regen_rate for res, rspec in spec.resources.items()},
        )

    def get_resource(self, resource: ResourceType | str) -> float:
        """Return the current amount of a given resource on this tile."""
        res_type = ResourceType(resource)
        return self.resources.get(res_type, 0.0)

    def deplete(self, resource: ResourceType | str, amount: float) -> float:
        """Deplete up to `amount` of a resource and return what was actually taken."""
        if amount <= 0.0:
            return 0.0
        res_type = ResourceType(resource)
        available = self.resources.get(res_type, 0.0)
        taken = min(available, amount)
        self.resources[res_type] = available - taken
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
                self.resources[res_type] = min(maximum, current + rate * multiplier)

    def to_dict(self) -> dict[str, Any]:
        """Serialize tile state to a JSON-friendly dictionary."""
        return {
            "x": self.x,
            "y": self.y,
            "terrain": self.terrain.value,
            "walkable": self.walkable,
            "resources": {res.value: round(val, 2) for res, val in self.resources.items()},
        }
