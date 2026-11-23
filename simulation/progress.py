"""Realistic long-timescale human progress: slow tech, Tasmania effect, domestication, migration."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agents.culture import BASE_WORDS, TechSpec, mutate_word

if TYPE_CHECKING:
    from world.map import WorldMap

GENERATION_YEARS = 25


def culture_era_name(known_techs: set[str]) -> str:
    """Derive a culture's era name strictly from the technologies that culture currently holds."""
    if "iron" in known_techs:
        return "Iron-Age Metal-Users"
    if "bronze" in known_techs:
        return "Bronze-Age Metal-Users"
    if "farming" in known_techs:
        return "Neolithic Farmers"
    if "fire" in known_techs or "stone_tools" in known_techs:
        return "Stone-Age Hunter-Gatherers"
    return "Early Foragers"


def classify_social_structure(pop: int, surplus: float, known_techs: set[str]) -> dict[str, Any]:
    """Derive emergent social structure (band/tribe/village/city) from pop, surplus, and tech."""
    if pop >= 250 and ("writing" in known_techs or "bronze" in known_techs or "iron" in known_techs):
        return {
            "tier": "city", "jobs": ["farmer", "artisan", "scribe", "trader", "guard", "priest"],
            "has_laws": True, "religion": "organized_pantheon", "trade_routes": True,
        }
    if pop >= 80 and ("farming" in known_techs or surplus >= 40.0):
        return {
            "tier": "village", "jobs": ["farmer", "builder", "potter", "trader", "healer"],
            "has_laws": True, "religion": "ancestor_shrines", "trade_routes": True,
        }
    if pop >= 25:
        return {
            "tier": "tribe", "jobs": ["hunter", "gatherer", "crafter", "shaman"],
            "has_laws": False, "religion": "animist_rituals", "trade_routes": False,
        }
    return {
        "tier": "band", "jobs": ["forager", "hunter"],
        "has_laws": False, "religion": "oral_myths", "trade_routes": False,
    }


@dataclass
class DomesticatedLineage:
    """Wild plant or animal population undergoing gradual artificial selection by humans."""

    species: str
    kind: str  # "plant" or "animal"
    docility: float = 0.20
    yield_size: float = 0.25
    fertility: float = 0.30
    generations_bred: int = 0

    @property
    def is_domesticated(self) -> bool:
        return self.docility >= 0.65 and self.yield_size >= 0.60

    def breed_generation(self, rng: random.Random, selection_intensity: float = 0.04) -> None:
        """Select the tamest, highest-yielding individuals each generation (artificial selection)."""
        self.docility = min(1.0, max(0.0, self.docility + selection_intensity + rng.gauss(0.0, 0.01)))
        self.yield_size = min(1.0, max(0.0, self.yield_size + selection_intensity * 0.9 + rng.gauss(0.0, 0.01)))
        self.fertility = min(1.0, max(0.0, self.fertility + selection_intensity * 0.6 + rng.gauss(0.0, 0.01)))
        self.generations_bred += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "species": self.species, "kind": self.kind, "docility": round(self.docility, 2),
            "yield_size": round(self.yield_size, 2), "domesticated": self.is_domesticated,
            "generations": self.generations_bred,
        }


@dataclass
class TechOrigin:
    """Date (year), place, and originating culture where a technology first appeared."""

    tech: str
    culture_id: str
    year: int
    place: str

    def to_dict(self) -> dict[str, Any]:
        return {"tech": self.tech, "culture_id": self.culture_id, "year": self.year, "place": self.place}


@dataclass
class CultureGroupState:
    """Autonomous human cultural group with its own population, tech, dialect, genes, and location."""

    id: str
    x: int
    y: int
    place: str
    population: int = 18
    food_store: float = 35.0
    known_techs: set[str] = field(default_factory=set)
    lost_techs: set[str] = field(default_factory=set)
    practice_gens: dict[str, int] = field(default_factory=dict)
    language: dict[str, str] = field(default_factory=lambda: dict(BASE_WORDS))
    mean_genes: dict[str, float] = field(default_factory=lambda: {"intelligence": 0.55, "cold_tolerance": 0.5, "heat_tolerance": 0.5})
    domestication: list[DomesticatedLineage] = field(default_factory=list)
    conflicts: int = 0

    @property
    def is_settled(self) -> bool:
        return self.population >= 40 or "farming" in self.known_techs

    @property
    def has_domesticable(self) -> bool:
        return any(d.is_domesticated for d in self.domestication)

    def to_dict(self) -> dict[str, Any]:
        soc = classify_social_structure(self.population, max(0.0, self.food_store - self.population), self.known_techs)
        return {
            "id": self.id, "position": [self.x, self.y], "place": self.place,
            "population": self.population, "era": culture_era_name(self.known_techs),
            "social_structure": soc, "known_techs": sorted(self.known_techs),
            "lost_techs": sorted(self.lost_techs), "language": dict(self.language),
            "domestication": [d.to_dict() for d in self.domestication], "conflicts": self.conflicts,
        }


class ProgressTracker:
    """Simulates multi-millennium human tech, Tasmania loss, domestication, and migration."""

    def __init__(self, techs: dict[str, TechSpec], rng: random.Random) -> None:
        self.techs = techs
        self.rng = rng
        self.groups: dict[str, CultureGroupState] = {}
        self.tech_origins: dict[str, TechOrigin] = {}
        self.events: list[dict[str, Any]] = []
        self._group_seq = 0

    def add_group(self, x: int, y: int, place: str, pop: int = 18, has_wild_crops: bool = True) -> CultureGroupState:
        self._group_seq += 1
        gid = f"culture_{self._group_seq}"
        dom = [DomesticatedLineage("wild_grain", "plant"), DomesticatedLineage("wild_wolf", "animal")] if has_wild_crops else []
        g = CultureGroupState(id=gid, x=x, y=y, place=place, population=pop, food_store=pop * 2.2, domestication=dom)
        self.groups[gid] = g; return g

    def _connected_learners(self, group: CultureGroupState) -> tuple[int, int]:
        """Return `(connected_population, contact_group_count)` within travel/contact distance."""
        contact_range = 35 if "sailing" in group.known_techs else (22 if ("boats" in group.known_techs or "the_wheel" in group.known_techs) else 14)
        conn_pop, contacts = group.population, 0
        for other in self.groups.values():
            if other.id != group.id and other.population > 0 and math.hypot(other.x - group.x, other.y - group.y) <= contact_range:
                conn_pop += other.population; contacts += 1
        return conn_pop, contacts

    def step_generation(
        self, year: int, sea_level: float = 0.48, world: WorldMap | None = None,
    ) -> list[dict[str, Any]]:
        """Advance all cultural groups by 1 generation (~25 years): practice, discovery, Tasmania loss, migration."""
        gen_events: list[dict[str, Any]] = []
        for g in list(self.groups.values()):
            if g.population <= 0:
                continue
            conn_pop, contacts = self._connected_learners(g)

            # 1) Artificial selection / domestication of nearby wild flora & fauna
            for lin in g.domestication:
                if g.population >= 15:
                    lin.breed_generation(self.rng, selection_intensity=0.035)

            # 2) Practice accumulation & slow discovery (scales with pop + contact)
            for name, spec in self.techs.items():
                if name in g.known_techs:
                    continue
                if not all(p in g.known_techs for p in spec.prereqs):
                    continue
                if spec.requires_domesticable and not g.has_domesticable:
                    continue
                if spec.requires_settled and not g.is_settled:
                    continue
                if conn_pop < spec.min_learners:
                    continue
                g.practice_gens[name] = g.practice_gens.get(name, 0) + 1
                if g.practice_gens[name] < spec.practice_generations:
                    continue
                # Discovery probability rises with connected learners & inter-group contact
                pop_factor = 1.0 + 0.55 * math.log1p(conn_pop / max(1, spec.min_learners))
                contact_factor = 1.0 + 0.35 * contacts
                prob = min(0.25, spec.base_chance * 12.0 * pop_factor * contact_factor)
                if self.rng.random() < prob:
                    g.known_techs.add(name)
                    g.lost_techs.discard(name)
                    if name not in self.tech_origins:
                        self.tech_origins[name] = TechOrigin(name, g.id, year, g.place)
                    gen_events.append({"year": year, "kind": "discovery", "culture": g.id, "tech": name, "place": g.place})

            # 3) Tasmania effect: imperfect generational transmission loses complex techs in small isolated groups
            fidelity = 0.97 if "writing" in g.known_techs else 0.86
            for name in list(g.known_techs):
                spec = self.techs.get(name)
                if spec and conn_pop < spec.min_learners:
                    deficit = (spec.min_learners - conn_pop) / max(1, spec.min_learners)
                    loss_prob = (1.0 - fidelity) * (0.4 + 1.2 * deficit)
                    if self.rng.random() < loss_prob:
                        g.known_techs.remove(name)
                        g.lost_techs.add(name)
                        gen_events.append({"year": year, "kind": "tech_lost", "culture": g.id, "tech": name, "place": g.place})

            # 4) Isolated cultural & genetic drift
            if contacts == 0:
                key = self.rng.choice(tuple(BASE_WORDS.keys()))
                if self.rng.random() < 0.30:
                    g.language[key] = mutate_word(g.language.get(key, BASE_WORDS[key]), self.rng)
                for gk in g.mean_genes:
                    g.mean_genes[gk] = round(max(0.05, min(0.95, g.mean_genes[gk] + self.rng.gauss(0.0, 0.015))), 3)

            # 5) Food scarcity -> band split & migration (land bridges when sea_level low, boats/sailing later)
            food_per_cap = g.food_store / max(1, g.population)
            if food_per_cap < 1.5 and g.population >= 16 and len(self.groups) < 12:
                can_cross_water = (sea_level <= 0.45) or ("boats" in g.known_techs) or ("sailing" in g.known_techs)
                step_dist = 18 if can_cross_water else 10
                nx = (g.x + self.rng.choice((-step_dist, step_dist))) % (world.width if world else 100)
                ny = max(2, min((world.height if world else 100) - 3, g.y + self.rng.randint(-8, 8)))
                split_pop = g.population // 3
                g.population -= split_pop
                tile = world.get_tile(nx, ny) if world else None
                new_place = tile.terrain.value if tile else ("coastal_bridge" if sea_level <= 0.45 else "frontier")
                child = self.add_group(nx, ny, new_place, pop=split_pop, has_wild_crops=(self.rng.random() < 0.65))
                child.known_techs = {t for t in g.known_techs if self.rng.random() < 0.85}
                child.language = dict(g.language)
                gen_events.append({"year": year, "kind": "migration", "from": g.id, "to": child.id, "place": new_place, "via_bridge": sea_level <= 0.45})

        self.events.extend(gen_events)
        return gen_events

    def to_tech_tree_dict(self) -> dict[str, Any]:
        """Serialize per-culture tech tree, lost techs, eras, and first-appearance origins for viewer."""
        return {
            "cultures": [g.to_dict() for g in self.groups.values()],
            "origins": {k: v.to_dict() for k, v in self.tech_origins.items()},
            "tech_specs": {k: {"prereqs": list(v.prereqs), "min_learners": v.min_learners, "practice_generations": v.practice_generations} for k, v in self.techs.items()},
        }
