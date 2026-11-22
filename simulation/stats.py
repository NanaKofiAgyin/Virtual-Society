"""Simulation statistics: births, deaths by cause, and yearly average genes per species."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from agents.genome import GENES

if TYPE_CHECKING:
    from agents.animal import AnimalAgent
    from agents.human import HumanAgent
    from agents.lifecycle import DeathCause


class SimulationStats:
    """Logs births, deaths by cause, and yearly per-species gene averages."""

    def __init__(self) -> None:
        self.births_total: int = 0
        self.births_by_species: dict[str, int] = {}
        self.deaths_by_cause: dict[str, int] = {}
        self.deaths_by_species: dict[str, dict[str, int]] = {}
        self.yearly_history: list[dict[str, Any]] = []
        self.society: dict[str, Any] = {
            "tech_count": 0, "known_techs": [], "lost_techs": [],
            "era": "Stone Age", "settlements": [], "population_per_settlement": {},
        }

    def update_society(self, society_summary: dict[str, Any]) -> None:
        """Update tracked technology count, settlements, populations, and era."""
        self.society = dict(society_summary)

    def record_birth(self, species: str) -> None:
        """Increment birth counters for `species`."""
        self.births_total += 1
        self.births_by_species[species] = self.births_by_species.get(species, 0) + 1

    def record_death(self, species: str, cause: DeathCause | str) -> None:
        """Increment death counters by cause and by species."""
        cause_key = cause.value if hasattr(cause, "value") else str(cause)
        self.deaths_by_cause[cause_key] = self.deaths_by_cause.get(cause_key, 0) + 1
        sp_map = self.deaths_by_species.setdefault(species, {})
        sp_map[cause_key] = sp_map.get(cause_key, 0) + 1

    @staticmethod
    def _average_genes(genomes: list[dict[str, float]]) -> dict[str, float]:
        if not genomes:
            return {}
        n = len(genomes)
        return {
            gene: round(sum(g.get(gene, 0.5) for g in genomes) / n, 4)
            for gene in GENES
        }

    def record_year(
        self,
        year: int,
        humans: list[HumanAgent],
        animals: list[AnimalAgent],
    ) -> dict[str, Any]:
        """Compute and archive a yearly summary of populations, events, and mean genes."""
        by_species: dict[str, list[dict[str, float]]] = defaultdict(list)
        for h in humans:
            if h.alive:
                by_species["human"].append(h.genome)
        for a in animals:
            if a.alive:
                by_species[a.species].append(a.genome)

        avg_genes = {sp: self._average_genes(gs) for sp, gs in by_species.items()}
        pop = {sp: len(gs) for sp, gs in by_species.items()}
        snapshot = {
            "year": year,
            "population": pop,
            "births_total": self.births_total,
            "births_by_species": dict(self.births_by_species),
            "deaths_by_cause": dict(self.deaths_by_cause),
            "avg_genes": avg_genes,
        }
        self.yearly_history.append(snapshot)
        return snapshot

    def summary(self) -> dict[str, Any]:
        """Return JSON-friendly statistics summary."""
        return {
            "births_total": self.births_total,
            "births_by_species": dict(self.births_by_species),
            "deaths_by_cause": dict(self.deaths_by_cause),
            "deaths_by_species": {sp: dict(c) for sp, c in self.deaths_by_species.items()},
            "society": dict(self.society),
            "yearly_history": list(self.yearly_history[-20:]),
        }
