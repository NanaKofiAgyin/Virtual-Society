"""Contact-based, density-dependent, slowly mutating disease dynamics."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.animal import AnimalAgent


@dataclass
class Pathogen:
    """Evolving pathogen strain with transmissibility, virulence, and slow mutation."""

    name: str
    host_species: str
    transmissibility: float = 0.22  # base contact transmission beta
    virulence: float = 0.08         # mortality risk per season while infected
    recovery_rate: float = 0.45     # fraction recovering with temporary immunity
    mutation_rate: float = 0.015    # slow drift per evolutionary step
    generation: int = 0

    def mutate(self, rng: random.Random) -> None:
        """Mutate pathogen traits slowly with a virulence-transmission trade-off."""
        if rng.random() > 0.35:
            return
        dv = rng.gauss(0.0, self.mutation_rate)
        db = rng.gauss(0.0, self.mutation_rate)
        # Higher virulence slightly impairs host mobility/transmission window
        self.virulence = max(0.01, min(0.45, self.virulence + dv))
        self.transmissibility = max(0.05, min(0.65, self.transmissibility + db - 0.15 * max(0.0, dv)))
        self.generation += 1


@dataclass
class DiseaseEngine:
    """Manages contact-based, density-dependent outbreaks across regions and agents."""

    rng: random.Random
    strains: dict[str, Pathogen] = field(default_factory=dict)
    infected_ids: set[str] = field(default_factory=set)

    def ensure_strain(self, species: str) -> Pathogen:
        if species not in self.strains:
            self.strains[species] = Pathogen(
                name=f"{species}_pathogen",
                host_species=species,
                transmissibility=self.rng.uniform(0.16, 0.28),
                virulence=self.rng.uniform(0.04, 0.12),
            )
        return self.strains[species]

    def step_regional_outbreak(
        self,
        species: str,
        pop: float,
        infected_frac: float,
        region_area: float,
        mean_resistance: float,
        social: bool = False,
    ) -> tuple[float, float]:
        """Advance contact-based density-dependent SIR step for one species in one region.

        Returns `(new_infected_frac, deaths_fraction)`.
        """
        if pop < 1.0:
            return 0.0, 0.0
        strain = self.ensure_strain(species)
        # Local contact density scales with pop / area (social species cluster more tightly)
        contact_density = (pop / max(10.0, region_area)) * (1.45 if social else 1.0)
        susceptibility = max(0.15, 1.0 - 0.70 * mean_resistance)

        # Spontaneous spillover only becomes likely at high host density
        if infected_frac <= 1e-4:
            spillover_prob = min(0.08, 0.0025 * (contact_density ** 1.6))
            if self.rng.random() < spillover_prob:
                infected_frac = min(0.12, max(0.02, 1.5 / pop))
            else:
                return 0.0, 0.0

        susceptible = max(0.0, 1.0 - infected_frac)
        new_cases = strain.transmissibility * contact_density * susceptibility * susceptible * infected_frac
        recovered = strain.recovery_rate * infected_frac
        deaths = strain.virulence * susceptibility * infected_frac

        next_inf = max(0.0, min(0.85, infected_frac + new_cases - recovered - deaths))
        if next_inf < 0.005:
            next_inf = 0.0
        else:
            strain.mutate(self.rng)
        return next_inf, min(0.35, deaths)

    def step_agents(self, animals: list[AnimalAgent], contact_radius: int = 2) -> int:
        """Spread contact-based disease among individual agents; returns count of disease deaths."""
        live = [a for a in animals if a.alive]
        if not live:
            return 0
        deaths = 0
        # Index infected agents by species for fast contact checks
        by_species: dict[str, list[AnimalAgent]] = {}
        for a in live:
            by_species.setdefault(a.species, []).append(a)

        new_infections: set[str] = set()
        recovered_ids: set[str] = set()
        for sp, members in by_species.items():
            strain = self.ensure_strain(sp)
            infected = [m for m in members if m.id in self.infected_ids]
            # Density-dependent spillover when many conspecifics crowd closely
            if not infected and len(members) >= 12 and self.rng.random() < 0.0004 * len(members):
                seed_host = self.rng.choice(members)
                new_infections.add(seed_host.id)
                infected = [seed_host]
            if not infected:
                continue
            strain.mutate(self.rng)
            for host in infected:
                res = host.genome.get("disease_resistance", 0.5)
                for other in members:
                    if other.id in self.infected_ids or other.id == host.id:
                        continue
                    if abs(other.x - host.x) + abs(other.y - host.y) <= contact_radius:
                        p_tx = strain.transmissibility * max(0.15, 1.0 - 0.7 * other.genome.get("disease_resistance", 0.5))
                        if self.rng.random() < p_tx * 0.25:
                            new_infections.add(other.id)
                if self.rng.random() < strain.virulence * max(0.15, 1.0 - 0.7 * res) * 0.15:
                    host.alive = False
                    deaths += 1
                    recovered_ids.add(host.id)
                elif self.rng.random() < strain.recovery_rate * 0.2:
                    recovered_ids.add(host.id)

        self.infected_ids = (self.infected_ids | new_infections) - recovered_ids
        return deaths
