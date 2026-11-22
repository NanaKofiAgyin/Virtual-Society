"""Data-driven biome definitions, classification, and body-type movement rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_BIOMES_PATH = Path(__file__).resolve().parent.parent / "data" / "biomes.json"


class BodyType(str, Enum):
    """Locomotion body types determining which biomes an agent can enter."""

    LAND = "land"
    AQUATIC = "aquatic"
    AMPHIBIAN = "amphibian"
    FLYING = "flying"
    BURROWER = "burrower"


@dataclass(frozen=True)
class BiomeSpec:
    """Data-driven properties for a biome loaded from `data/biomes.json`."""

    name: str
    id: int
    color: str
    walkable: bool
    swimmable: bool
    burrowable: bool
    food_max: float
    food_regen: float
    wood_max: float
    wood_regen: float
    plants: tuple[str, ...]


def load_biomes(
    path: Path | str = DEFAULT_BIOMES_PATH,
) -> tuple[dict[str, BiomeSpec], dict[int, BiomeSpec]]:
    """Load biomes from JSON and return `(by_name, by_id)` lookup dicts."""
    raw: dict[str, dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    by_name: dict[str, BiomeSpec] = {}
    by_id: dict[int, BiomeSpec] = {}
    for name, c in raw.items():
        spec = BiomeSpec(
            name=name, id=int(c["id"]), color=str(c["color"]),
            walkable=bool(c["walkable"]), swimmable=bool(c["swimmable"]),
            burrowable=bool(c["burrowable"]),
            food_max=float(c["food_max"]), food_regen=float(c["food_regen"]),
            wood_max=float(c["wood_max"]), wood_regen=float(c["wood_regen"]),
            plants=tuple(c.get("plants", ())),
        )
        by_name[name] = spec
        by_id[spec.id] = spec
    return by_name, by_id


BIOMES_BY_NAME, BIOMES_BY_ID = load_biomes()


def can_traverse(biome: BiomeSpec, body_type: BodyType) -> bool:
    """Return True if an organism with `body_type` can enter `biome`."""
    if body_type is BodyType.FLYING:
        return True
    if body_type is BodyType.LAND:
        return biome.walkable
    if body_type is BodyType.AQUATIC:
        return biome.swimmable
    if body_type is BodyType.AMPHIBIAN:
        return biome.walkable or biome.swimmable
    if body_type is BodyType.BURROWER:
        return biome.burrowable
    return biome.walkable


def classify_biome(
    elevation: float,
    temperature: float,
    moisture: float,
    ocean_depth: float,
    is_river: bool = False,
    is_lake: bool = False,
    is_cave: bool = False,
) -> str:
    """Determine biome name from elevation, temperature, moisture, and hydrological flags."""
    if is_cave:
        return "cave"
    if ocean_depth > 0.0:
        if ocean_depth > 0.45:
            return "deep_ocean"
        if temperature > 0.62 and ocean_depth < 0.28:
            return "coral_reef"
        return "shallow_sea"
    if is_lake:
        return "lake"
    if is_river:
        return "river"
    if elevation > 0.84:
        return "glacier" if temperature < 0.32 else "mountain"
    if elevation < 0.34 and moisture > 0.68:
        return "wetland"
    if elevation < 0.33 and moisture <= 0.68:
        return "beach"
    if temperature < 0.22:
        return "glacier" if moisture > 0.65 else "tundra"
    if temperature < 0.40:
        return "taiga" if moisture > 0.38 else "tundra"
    if temperature < 0.68:
        if moisture < 0.24:
            return "desert"
        return "temperate_forest" if moisture > 0.52 else "grassland"
    # Warm / tropical band
    if moisture < 0.28:
        return "desert"
    if moisture < 0.52:
        return "savanna"
    return "jungle"
