"""Speciation engine, phylogenetic tree tracking, extinctions, and niche shifts."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from agents.ecosystem import SpeciesConfig
from agents.genome import genetic_distance
from world.biomes import BodyType

if TYPE_CHECKING:
    from agents.animal import AnimalAgent
    from simulation.storage import Storage
    from world.map import WorldMap

KEY_GENES = ("size", "speed", "vision", "cold_tolerance", "heat_tolerance", "habitat_preference")
PHYSICAL_MASS_EXTINCTION_CAUSES = frozenset({"climate_shift", "volcanic_winter", "ocean_anoxia"})


@dataclass
class SpeciesNode:
    """Single node in the phylogenetic tree."""

    species_id: str
    parent_species: str | None
    born_tick: int
    habitat: str
    extinct_tick: int | None = None
    peak_population: int = 0
    key_gene_averages: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "species_id": self.species_id, "parent_species": self.parent_species,
            "born_tick": self.born_tick, "extinct_tick": self.extinct_tick,
            "peak_population": self.peak_population,
            "key_gene_averages": dict(self.key_gene_averages), "habitat": self.habitat,
        }


def _mean_genome(animals: list[AnimalAgent]) -> dict[str, float]:
    if not animals:
        return {}
    n = len(animals)
    return {k: round(sum(a.genome.get(k, 0.5) for a in animals) / n, 4) for k in animals[0].genome}


def _key_genes(mean_g: dict[str, float]) -> dict[str, float]:
    return {k: mean_g.get(k, 0.5) for k in KEY_GENES}


def _centroid(animals: list[AnimalAgent]) -> tuple[float, float]:
    return (sum(a.x for a in animals) / len(animals), sum(a.y for a in animals) / len(animals))


def _has_barrier_between(
    p1: tuple[float, float], p2: tuple[float, float], world: WorldMap, body_type: BodyType,
) -> bool:
    """Sample straight line between two centroids to detect impassable water/mountain barriers."""
    steps = max(2, int(math.hypot(p2[0] - p1[0], p2[1] - p1[1])))
    for i in range(1, steps):
        t = i / steps
        x = int(round(p1[0] + (p2[0] - p1[0]) * t))
        y = int(round(p1[1] + (p2[1] - p1[1]) * t))
        if not world.can_enter(x, y, body_type):
            return True
    return False


def _generate_species_name(parent_name: str, genes: dict[str, float], existing: set[str]) -> str:
    """Create a descriptive new species name from dominant drifted traits."""
    rules = (
        (genes.get("habitat_preference", 0.5) >= 0.85, "marine"),
        (genes.get("habitat_preference", 0.5) >= 0.70, "coastal"),
        (genes.get("cold_tolerance", 0.5) >= 0.72, "arctic"),
        (genes.get("heat_tolerance", 0.5) >= 0.72, "desert"),
        (genes.get("size", 0.5) >= 0.72, "giant"),
        (genes.get("speed", 0.5) >= 0.75, "swift"),
    )
    prefix = next((label for cond, label in rules if cond), "divergent")
    base = f"{prefix}_{parent_name}"
    if base not in existing:
        return base
    idx = 2
    while f"{base}_{idx}" in existing:
        idx += 1
    return f"{base}_{idx}"


class SpeciationEngine:
    """Tracks yearly clustering, allopatric speciation, niche shifts, and extinctions."""

    def __init__(
        self, species_map: dict[str, SpeciesConfig], tick: int = 0,
        storage: Storage | None = None, isolation_distance: float = 20.0,
        genetic_threshold: float = 0.16, divergence_generations: int = 3,
        mass_extinction_fraction: float = 0.40,
    ) -> None:
        self.isolation_distance, self.genetic_threshold = isolation_distance, genetic_threshold
        self.divergence_generations = divergence_generations
        self.mass_extinction_fraction = mass_extinction_fraction
        self.tree: dict[str, SpeciesNode] = {}
        self.divergence_streaks: dict[str, int] = {}
        self.history: list[dict[str, Any]] = []
        for name, cfg in species_map.items():
            if cfg.founding_max <= 0:
                continue
            node = SpeciesNode(name, None, tick, cfg.habitat, key_gene_averages=_key_genes(cfg.genome_template))
            self.tree[name] = node
            if storage is not None:
                storage.upsert_species(node)

    def _split_two_clusters(
        self, members: list[AnimalAgent],
    ) -> tuple[list[AnimalAgent], list[AnimalAgent]]:
        """Partition `members` into two geographic clusters around the farthest pair."""
        best_d, s1, s2 = -1.0, members[0], members[1]
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                d = math.hypot(a.x - b.x, a.y - b.y)
                if d > best_d:
                    best_d, s1, s2 = d, a, b
        c1, c2 = [], []
        for m in members:
            if math.hypot(m.x - s1.x, m.y - s1.y) <= math.hypot(m.x - s2.x, m.y - s2.y):
                c1.append(m)
            else:
                c2.append(m)
        return c1, c2

    def _check_niche_shift(
        self, name: str, members: list[AnimalAgent], mean_g: dict[str, float],
        species_map: dict[str, SpeciesConfig], tick: int,
    ) -> dict[str, Any] | None:
        """Allow gradual shoreline/aquatic niche shifts when `habitat_preference` drifts."""
        cfg = species_map.get(name)
        if cfg is None:
            return None
        pref = mean_g.get("habitat_preference", 0.5)
        new_bt, new_hab = None, None
        if cfg.body_type == "land" and pref >= 0.72:
            new_bt, new_hab = "amphibian", "fresh_water"
        elif cfg.body_type == "amphibian" and pref >= 0.88:
            new_bt, new_hab = "aquatic", "sea"
        if new_bt is None or new_hab is None:
            return None

        updated = replace(cfg, body_type=new_bt, habitat=new_hab)
        species_map[name] = updated
        for m in members:
            m.config = updated
            m.body_type = BodyType(new_bt)
        if name in self.tree:
            self.tree[name].habitat = new_hab
        return {"tick": tick, "kind": "niche_shift", "message": f"{name} shifted niche to {new_bt} ({new_hab})"}

    def step_year(
        self, tick: int, animals: list[AnimalAgent], species_map: dict[str, SpeciesConfig],
        world: WorldMap, storage: Storage | None = None,
        physical_cause: str | None = None, density_totals: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Run yearly clustering, speciation, niche shifts, and physical-cause extinction tracking."""
        events: list[dict[str, Any]] = []
        by_species: dict[str, list[AnimalAgent]] = {}
        for a in animals:
            if a.alive:
                by_species.setdefault(a.species, []).append(a)
        dens = density_totals or {}
        live_tracked = [n for n in self.tree.values() if n.extinct_tick is None]
        extinct_now = 0

        for node in live_tracked:
            members = by_species.get(node.species_id, [])
            if not members and dens.get(node.species_id, 0.0) >= 1.0:
                node.peak_population = max(node.peak_population, int(dens[node.species_id]))
                continue
            if not members:
                if node.peak_population > 0 or tick > node.born_tick:
                    node.extinct_tick = tick
                    extinct_now += 1
                    events.append({"tick": tick, "kind": "extinction", "message": f"Species {node.species_id} went extinct"})
                    if storage is not None:
                        storage.upsert_species(node)
                continue
            mean_g = _mean_genome(members)
            node.peak_population, node.key_gene_averages = max(node.peak_population, len(members)), _key_genes(mean_g)
            shift_ev = self._check_niche_shift(node.species_id, members, mean_g, species_map, tick)
            if shift_ev is not None:
                events.append(shift_ev)
            if storage is not None:
                storage.upsert_species(node)

        if physical_cause in PHYSICAL_MASS_EXTINCTION_CAUSES and len(live_tracked) >= 2 and extinct_now >= 2 and (extinct_now / len(live_tracked)) >= self.mass_extinction_fraction:
            events.append({"tick": tick, "kind": "mass_extinction", "cause": physical_cause, "message": f"Mass extinction ({physical_cause}): {extinct_now}/{len(live_tracked)} species died out"})

        # 2) Speciation clustering for each live species with >= 4 individuals
        for sp_name, members in list(by_species.items()):
            if len(members) < 4 or sp_name not in species_map:
                continue
            c1, c2 = self._split_two_clusters(members)
            if len(c1) < 2 or len(c2) < 2:
                self.divergence_streaks[sp_name] = 0
                continue
            p1, p2 = _centroid(c1), _centroid(c2)
            cfg = species_map[sp_name]
            isolated = (
                math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= self.isolation_distance
                or _has_barrier_between(p1, p2, world, BodyType(cfg.body_type))
            )
            g_dist = genetic_distance(_mean_genome(c1), _mean_genome(c2))
            if isolated and g_dist >= self.genetic_threshold:
                self.divergence_streaks[sp_name] = self.divergence_streaks.get(sp_name, 0) + 1
            else:
                self.divergence_streaks[sp_name] = 0

            if self.divergence_streaks[sp_name] >= self.divergence_generations:
                self.divergence_streaks[sp_name] = 0
                offshoot = c2 if len(c2) <= len(c1) else c1
                off_genes = _mean_genome(offshoot)
                new_name = _generate_species_name(sp_name, off_genes, set(species_map.keys()) | set(self.tree.keys()))
                new_cfg = replace(cfg, name=new_name)
                species_map[new_name] = new_cfg
                for m in offshoot:
                    m.species, m.config = new_name, new_cfg
                new_node = SpeciesNode(
                    species_id=new_name, parent_species=sp_name, born_tick=tick,
                    habitat=new_cfg.habitat, peak_population=len(offshoot),
                    key_gene_averages=_key_genes(off_genes),
                )
                self.tree[new_name] = new_node
                if storage is not None:
                    storage.upsert_species(new_node)
                events.append({
                    "tick": tick, "kind": "speciation",
                    "message": f"New species {new_name} evolved from {sp_name} (d={g_dist:.2f})",
                })

        self.history.extend(events)
        return events
