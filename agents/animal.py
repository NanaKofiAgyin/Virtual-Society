"""Rule-based animal agents with trophic food web, genomes, carcasses, and migration."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agents.base import Action, ActionType, Agent, Needs
from agents.ecosystem import (
    Carcass, SpeciesConfig, load_species, migration_target,
    predator_prey_capture_prob, trophic_energy_gain,
)
from agents.genome import Genome, crossover, express_phenotype, mutate, random_genome
from agents.lifecycle import (
    DeathCause, LifeStage, apply_environmental_hazards,
    can_mate_animals, compute_life_stage, stage_strength_multiplier,
)
from world.biomes import BodyType
from world.tile import ResourceType

if TYPE_CHECKING:
    from world.map import WorldMap


def _agent_kind(agent: Agent) -> str:
    return agent.species if isinstance(agent, AnimalAgent) else "human"


@dataclass
class AnimalAgent(Agent):
    """Rule-based animal with trophic diet, genome, lineage, life stages, and migration."""

    species: str = "deer"
    config: SpeciesConfig | None = None
    genome: Genome = field(default_factory=lambda: random_genome(rng=random.Random(0)))
    lineage_id: str = ""
    parent_id: str | None = None
    age: int = 0
    breed_timer: int = 0
    vision_radius: int = 5
    death_cause: DeathCause | None = None
    available_actions: list[ActionType] = field(
        default_factory=lambda: [ActionType.MOVE, ActionType.EAT, ActionType.SLEEP, ActionType.GATHER]
    )

    def __post_init__(self) -> None:
        if not self.lineage_id:
            self.lineage_id = self.id
        if self.config is not None:
            self.species = self.config.name
            self.speed = max(1, self.config.speed) if self.config.speed > 0 else 0
            self.body_type = BodyType(self.config.body_type)
            self.flies = self.body_type is BodyType.FLYING
            self.hunger_decay = self.config.hunger_rate

    @property
    def effective_max_age(self) -> int:
        base = self.config.max_age if self.config else 1500
        return max(120, int(base * express_phenotype(self.genome).effective_lifespan_factor))

    @property
    def stage(self) -> LifeStage:
        return compute_life_stage(self.age, self.effective_max_age)

    def decide(self, world: WorldMap, nearby_agents: list[Agent]) -> Action:
        if self.config and self._find_threat(nearby_agents) is not None:
            return Action(type=ActionType.MOVE, params={"intent": "flee"})
        return Action(type=ActionType.EAT if self.needs.hunger < 6.0 else ActionType.MOVE)

    def _find_threat(self, agents: list[Agent]) -> Agent | None:
        if not self.config or not self.config.fears:
            return None
        threats = [
            (abs(o.x - self.x) + abs(o.y - self.y), o) for o in agents
            if o is not self and o.alive and _agent_kind(o) in self.config.fears
        ]
        in_range = [p for p in threats if p[0] <= self.vision_radius]
        return min(in_range, key=lambda p: p[0])[1] if in_range else None

    def _find_prey(self, agents: list[Agent]) -> AnimalAgent | None:
        if not self.config or not self.config.prey:
            return None
        cands = [
            (abs(o.x - self.x) + abs(o.y - self.y), o) for o in agents
            if o is not self and o.alive and isinstance(o, AnimalAgent) and o.species in self.config.prey
        ]
        return min(cands, key=lambda p: p[0])[1] if cands else None

    def _forage(self, world: WorldMap, rng: random.Random) -> None:
        tile = world.get_tile(self.x, self.y)
        if tile is not None and tile.get_resource(ResourceType.FOOD) >= 0.2:
            self.needs.adjust(hunger=tile.deplete(ResourceType.FOOD, 1.5) * 4.5)
            return
        nearby = [
            t for t in world.get_nearby(self.x, self.y, radius=self.vision_radius)
            if world.can_enter(t.x, t.y, self.effective_body_type) and t.get_resource(ResourceType.FOOD) >= 0.2
        ]
        if nearby:
            target = min(nearby, key=lambda t: (abs(t.x - self.x) + abs(t.y - self.y), t.y, t.x))
            if not self.goto(world, (target.x, target.y)):
                self.wander(world, rng)
        else:
            self.wander(world, rng)

    def _scavenge(self, world: WorldMap, carcasses: list[Carcass], rng: random.Random) -> None:
        if not carcasses:
            self._forage(world, rng)
            return
        nearest = min(carcasses, key=lambda c: abs(c.x - self.x) + abs(c.y - self.y))
        dist = abs(nearest.x - self.x) + abs(nearest.y - self.y)
        if dist <= max(1, self.speed):
            bite = min(nearest.energy, 15.0)
            nearest.energy -= bite
            self.needs.adjust(hunger=trophic_energy_gain(bite) * 3.0)
        elif dist <= 12 and self.speed > 0 and self.goto(world, (nearest.x, nearest.y)):
            return
        elif self.speed > 0:
            self.wander(world, rng)

    def _hunt(self, world: WorldMap, agents: list[Agent], rng: random.Random) -> None:
        prey = self._find_prey(agents)
        if prey is None:
            if self.config and self.config.diet == "omnivore":
                self._forage(world, rng)
            else:
                self.wander(world, rng)
            return
        dist = abs(prey.x - self.x) + abs(prey.y - self.y)
        if dist <= max(1, self.speed):
            self.position = prey.position
            prob = predator_prey_capture_prob(self, prey) * stage_strength_multiplier(self.stage)
            if rng.random() < prob:
                prey.alive, prey.death_cause = False, DeathCause.PREDATION
                energy_val = prey.config.energy_value if prey.config else 30.0
                self.needs.adjust(hunger=trophic_energy_gain(energy_val))
            else:
                prey.flee_from(world, self.position, rng)
        elif dist <= 10 and self.goto(world, prey.position):
            return
        else:
            self.wander(world, rng)

    def step(
        self, world: WorldMap, agents: list[Agent], rng: random.Random,
        can_reproduce: bool = True, next_id_fn: Any = None,
        carcasses: list[Carcass] | None = None,
    ) -> AnimalAgent | None:
        """Run one hourly tick; returns a newborn AnimalAgent if mating succeeds."""
        if not self.alive or self.config is None:
            return None
        self.age += 1
        self.breed_timer = max(0, self.breed_timer - 1)
        pheno = express_phenotype(self.genome)
        self.needs.adjust(hunger=-self.config.hunger_rate * (0.7 + 0.3 * pheno.food_need))

        if self.age >= self.effective_max_age:
            self.alive, self.death_cause = False, DeathCause.OLD_AGE
            return None
        if self.needs.hunger <= 0.0:
            self.alive, self.starving, self.death_cause = False, True, DeathCause.STARVATION
            return None
        hazard = apply_environmental_hazards(self, world.environment, self.genome, rng)
        if hazard is not None:
            self.death_cause = hazard
            return None

        threat = self._find_threat(agents)
        if threat is not None and self.speed > 0:
            self.flee_from(world, threat.position, rng)
        elif self.config.diet in ("scavenger", "decomposer") and self.needs.hunger < 7.0:
            self._scavenge(world, carcasses or [], rng)
        elif self.config.diet in ("carnivore", "omnivore") and self.needs.hunger < 6.5:
            self._hunt(world, agents, rng)
        elif self.needs.hunger < 7.0:
            self._forage(world, rng)
        elif self.speed > 0:
            mig = migration_target(self, world)
            if mig is not None:
                self.position = mig
            else:
                self.wander(world, rng)

        if can_reproduce and self.alive and self.stage is LifeStage.ADULT and self.breed_timer <= 0:
            mates = [o for o in agents if isinstance(o, AnimalAgent) and can_mate_animals(self, o)]
            if mates and rng.random() < self.config.breed_chance:
                mate = rng.choice(mates)
                cd = int(self.config.breed_cooldown * pheno.breed_cooldown_factor)
                self.breed_timer, mate.breed_timer = cd, cd
                self.needs.adjust(hunger=-2.0)
                mate.needs.adjust(hunger=-1.5)
                child_genome = mutate(crossover(self.genome, mate.genome, rng=rng), rate=0.15, rng=rng)
                cid = next_id_fn() if next_id_fn else f"{self.species}_{rng.randrange(10**9)}"
                return AnimalAgent(
                    id=cid, name=f"{self.species.capitalize()}-{cid.split('_')[-1]}",
                    position=self.position, needs=Needs(hunger=6.5, energy=8.0, social=8.0),
                    species=self.species, config=self.config, genome=child_genome,
                    lineage_id=self.lineage_id, parent_id=self.id, age=0, breed_timer=cd,
                )
        return None


def spawn_animals(
    world: WorldMap, species_map: dict[str, SpeciesConfig], rng: random.Random,
) -> list[AnimalAgent]:
    """Spawn founding populations for motile species in their matching body-type habitats."""
    pools = {bt: world.positions_for_body(bt) for bt in BodyType}
    animals: list[AnimalAgent] = []
    counter = 0
    for name, cfg in species_map.items():
        if cfg.founding_max <= 0:
            continue
        pool = pools.get(BodyType(cfg.body_type)) or pools[BodyType.FLYING]
        if not pool:
            continue
        for _ in range(rng.randint(cfg.founding_min, cfg.founding_max)):
            counter += 1
            pos, aid = rng.choice(pool), f"{name}_{counter}"
            animals.append(AnimalAgent(
                id=aid, name=f"{name.capitalize()}-{counter}", position=pos,
                needs=Needs(hunger=rng.uniform(6.5, 9.5), energy=8.0, social=8.0),
                species=name, config=cfg, genome=random_genome(cfg.genome_template, rng=rng),
                lineage_id=aid, age=rng.randrange(int(cfg.max_age * 0.22), int(cfg.max_age * 0.55)),
                breed_timer=rng.randrange(0, max(1, cfg.breed_cooldown // 2)),
            ))
    return animals
