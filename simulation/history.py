"""History chronicle, milestone logging, novelty metrics, and stagnation detector."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.animal import AnimalAgent
    from agents.human import HumanAgent

FIRST_TECH_MILESTONES: dict[str, tuple[str, str]] = {
    "fire": ("first_fire", "First Fire"),
    "farming": ("first_farm", "First Farm"),
    "boats": ("first_boat", "First Boat"),
    "writing": ("first_writing", "First Writing"),
    "iron": ("first_iron", "First Ironworking"),
}


@dataclass(frozen=True)
class Milestone:
    """A notable historical milestone recorded in the world chronicle."""

    tick: int
    year: int
    era: str
    kind: str
    title: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick, "year": self.year, "era": self.era,
            "kind": self.kind, "title": self.title, "detail": self.detail,
        }


def _genetic_diversity(genomes: list[dict[str, float]]) -> float:
    """Mean per-gene standard deviation across a species' genomes (0 = clones)."""
    if len(genomes) < 2:
        return 0.0
    keys = list(genomes[0].keys())
    stds = []
    for k in keys:
        vals = [g.get(k, 0.5) for g in genomes]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        stds.append(math.sqrt(var))
    return round(sum(stds) / len(stds), 4) if stds else 0.0


class HistoryTracker:
    """Tracks milestones by era, novelty metrics over time, and stagnation warnings."""

    def __init__(self, stagnation_years: int = 5) -> None:
        self.stagnation_years = stagnation_years
        self.milestones: list[Milestone] = []
        self._seen_unique: set[str] = set()
        self.last_novelty_year: int = 0
        self.warnings: list[dict[str, Any]] = []

        # Novelty metric series
        self.total_tech_discoveries: int = 0
        self.species_count_series: list[dict[str, Any]] = []
        self.avg_intelligence_series: list[dict[str, Any]] = []
        self.population_series: list[dict[str, Any]] = []
        self.gene_diversity_latest: dict[str, float] = {}
        self.gene_averages_series: list[dict[str, Any]] = []

    def record_milestone(
        self, kind: str, title: str, detail: str, tick: int, year: int, era: str,
        unique_key: str | None = None,
    ) -> Milestone | None:
        """Record a milestone (deduplicating one-time firsts via `unique_key`)."""
        if unique_key is not None:
            if unique_key in self._seen_unique:
                return None
            self._seen_unique.add(unique_key)
        m = Milestone(tick=tick, year=year, era=era, kind=kind, title=title, detail=detail)
        self.milestones.append(m)
        self.last_novelty_year = max(self.last_novelty_year, year)
        return m

    def observe_event(self, ev: dict[str, Any], year: int, era: str) -> None:
        """Promote major simulation events into historical milestones."""
        kind, msg, tick = ev.get("kind", ""), ev.get("message", ""), int(ev.get("tick", 0))
        if kind == "discovery":
            self.total_tech_discoveries += 1
            for tech_name, (key, title) in FIRST_TECH_MILESTONES.items():
                if msg.endswith(tech_name):
                    self.record_milestone("tech", title, msg, tick, year, era, unique_key=key)
        elif kind == "speciation":
            self.record_milestone("new_species", "New Species Evolved", msg, tick, year, era)
        elif kind == "extinction":
            self.record_milestone("extinction", "Species Extinction", msg, tick, year, era)
        elif kind == "mass_extinction":
            self.record_milestone("mass_extinction", "Mass Extinction", msg, tick, year, era)
        elif kind == "war":
            self.record_milestone("war", "Conflict Erupted", msg, tick, year, era)

    def observe_environment(self, active_event: str | None, tick: int, year: int, era: str) -> None:
        """Log plague and ice age milestones when those world events start."""
        if active_event == "disease_outbreak":
            self.record_milestone("plague", "Plague Outbreak", "A contagious blight spread.", tick, year, era,
                                  unique_key=f"plague_y{year}")
        elif active_event == "ice_age":
            self.record_milestone("ice_age", "Ice Age", "A sudden freeze gripped the world.", tick, year, era,
                                  unique_key=f"ice_age_y{year}")

    def record_year_metrics(
        self, year: int, humans: list[HumanAgent], animals: list[AnimalAgent],
        society: dict[str, Any], active_event: str | None = None,
    ) -> dict[str, Any] | None:
        """Compute yearly novelty metrics and run the stagnation detector."""
        live_h = [h for h in humans if h.alive]
        live_a = [a for a in animals if a.alive]
        if society.get("settlements"):
            self.record_milestone(
                "settlement", "First Settlement", "Villagers formed an organized settlement.",
                tick=year * 672, year=year, era=society.get("era", "Stone Age"),
                unique_key="first_settlement",
            )

        by_sp: dict[str, list[dict[str, float]]] = {}
        if live_h:
            by_sp["human"] = [h.genome for h in live_h]
        for a in live_a:
            by_sp.setdefault(a.species, []).append(a.genome)

        counts = {sp: len(gs) for sp, gs in by_sp.items()}
        self.population_series.append({"year": year, "counts": counts})
        self.species_count_series.append({"year": year, "species_count": len(by_sp)})
        self.gene_diversity_latest = {sp: _genetic_diversity(gs) for sp, gs in by_sp.items()}

        all_g = [g for gs in by_sp.values() for g in gs]
        h_intel = round(sum(g.get("intelligence", 0.5) for g in by_sp.get("human", ())) / max(1, len(live_h)), 4) if live_h else 0.0
        all_intel = round(sum(g.get("intelligence", 0.5) for g in all_g) / max(1, len(all_g)), 4) if all_g else 0.0
        self.avg_intelligence_series.append({"year": year, "human": h_intel, "overall": all_intel})

        avg_cold = round(sum(g.get("cold_tolerance", 0.5) for g in all_g) / max(1, len(all_g)), 4) if all_g else 0.0
        avg_spd = round(sum(g.get("speed", 0.5) for g in all_g) / max(1, len(all_g)), 4) if all_g else 0.0
        self.gene_averages_series.append({"year": year, "intelligence": all_intel, "cold_tolerance": avg_cold, "speed": avg_spd})

        return self.check_stagnation(year, live_h, live_a, active_event)

    def check_stagnation(
        self, year: int, live_humans: list[HumanAgent], live_animals: list[AnimalAgent],
        active_event: str | None = None,
    ) -> dict[str, Any] | None:
        """If nothing new happened for `stagnation_years`, warn with likely cause & fix."""
        quiet_years = year - self.last_novelty_year
        if quiet_years < self.stagnation_years:
            return None

        mean_div = (
            sum(self.gene_diversity_latest.values()) / len(self.gene_diversity_latest)
            if self.gene_diversity_latest else 0.0
        )
        if len(live_humans) < 8 or len(live_animals) < 20:
            cause = "Population is too small to sustain innovation or speciation."
            suggestion = "Increase FOUNDING_HUMANS or MAX_TOTAL_AGENTS in .env."
        elif mean_div < 0.03:
            cause = "Genetic diversity is very low (mutation rate may be too low)."
            suggestion = "Increase mutation rate in agents/genome.py."
        elif active_event is None:
            cause = "Environment is stable with no recent climate pressures."
            suggestion = "Increase event chances in data/events.json."
        else:
            cause = "No new techs, settlements, or species emerged recently."
            suggestion = "Raise tech base_chance in data/tech.json or lower speciation threshold."

        warning = {
            "year": year, "quiet_years": quiet_years,
            "cause": cause, "suggestion": suggestion,
        }
        self.warnings.append(warning)
        return warning

    def new_tech_per_century(self, current_year: int) -> float:
        """Estimated rate of tech discoveries per 100 simulated years."""
        years = max(1, current_year)
        return round((self.total_tech_discoveries / years) * 100.0, 2)

    def chronicle(self) -> dict[str, list[dict[str, Any]]]:
        """Group recorded milestones by era name."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for m in self.milestones:
            grouped.setdefault(m.era, []).append(m.to_dict())
        return grouped

    def to_dict(self, current_year: int) -> dict[str, Any]:
        """Return JSON-friendly history, chronicle, novelty metrics, and warnings."""
        return {
            "milestones": [m.to_dict() for m in self.milestones[-100:]],
            "chronicle": self.chronicle(),
            "metrics": {
                "new_tech_per_century": self.new_tech_per_century(current_year),
                "species_count_over_time": self.species_count_series[-50:],
                "genetic_diversity_per_species": dict(self.gene_diversity_latest),
                "avg_intelligence_over_time": self.avg_intelligence_series[-50:],
                "population_over_time": self.population_series[-50:],
                "gene_averages_over_time": self.gene_averages_series[-50:],
            },
            "warnings": self.warnings[-20:],
        }
