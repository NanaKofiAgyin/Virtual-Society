"""Life cycle stages, death causes, family trees, mating, and child learning."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from agents.genome import crossover, express_phenotype, genetic_distance, mutate
from world.environment import Season, Weather

if TYPE_CHECKING:
    from agents.animal import AnimalAgent
    from agents.base import Agent
    from agents.human import HumanAgent
    from world.environment import Environment
    from world.map import WorldMap

TICKS_PER_YEAR = 24 * 7 * 4  # 672 ticks = 1 simulated year (4 seasons * 7 days * 24h)
CHILD_GIVEN_NAMES: tuple[str, ...] = (
    "Lina", "Owen", "Nora", "Milo", "Tessa", "Eli", "Faye", "Jude",
    "Wren", "Soren", "Vera", "Caleb", "Maya", "Rowan", "Freya", "Theo",
)


class LifeStage(str, Enum):
    """Developmental life stages for humans and animals."""

    CHILD = "child"
    ADULT = "adult"
    ELDER = "elder"


class DeathCause(str, Enum):
    """Natural and environmental causes of death."""

    STARVATION = "starvation"
    OLD_AGE = "old_age"
    PREDATION = "predation"
    DISEASE = "disease"
    INJURY = "injury"
    COLD = "cold"
    ACCIDENT = "accident"


@dataclass
class FamilyTree:
    """Tracks lineage and immediate family links for a human or animal."""

    surname: str = ""
    lineage_id: str = ""
    parents: tuple[str, ...] = ()
    partner: str | None = None
    children: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize family links to a JSON-friendly dictionary."""
        return {
            "surname": self.surname,
            "lineage_id": self.lineage_id,
            "parents": list(self.parents),
            "partner": self.partner,
            "children": list(self.children),
        }


def compute_life_stage(age_ticks: int, max_age_ticks: int) -> LifeStage:
    """Map an organism's age to CHILD (<20%), ADULT (20%–78%), or ELDER (>=78%)."""
    if max_age_ticks <= 0:
        return LifeStage.ADULT
    ratio = age_ticks / max_age_ticks
    if ratio < 0.20:
        return LifeStage.CHILD
    if ratio < 0.78:
        return LifeStage.ADULT
    return LifeStage.ELDER


def stage_strength_multiplier(stage: LifeStage) -> float:
    """Return physical strength multiplier: children are weaker, elders slightly weaker."""
    if stage is LifeStage.CHILD:
        return 0.45
    if stage is LifeStage.ELDER:
        return 0.70
    return 1.0


def apply_environmental_hazards(
    agent: Agent,
    env: Environment,
    genome: dict[str, float],
    rng: random.Random,
    in_house: bool = False,
) -> DeathCause | None:
    """Apply cold, disease, and rare accident checks; return DeathCause if fatal."""
    if not agent.alive:
        return None
    pheno = express_phenotype(genome)

    # Cold hazard during winter nights/storms when unsheltered
    if env.season is Season.WINTER and not in_house and (env.is_night or env.weather is Weather.STORM):
        cold_dmg = max(0.0, (pheno.cold_drain_factor - 0.85) * 0.45)
        if cold_dmg > 0.0:
            agent.health = max(0.0, agent.health - cold_dmg)
            if agent.health <= 0.0:
                agent.alive = False
                return DeathCause.COLD

    # Disease hazard (rare, higher when weak/starving, mitigated by disease_resistance)
    disease_res = genome.get("disease_resistance", 0.5)
    base_prob = 0.0008 if agent.needs.hunger >= 3.0 else 0.004
    if rng.random() < base_prob * (1.2 - 0.9 * disease_res):
        agent.health = max(0.0, agent.health - 2.5)
        if agent.health <= 0.0:
            agent.alive = False
            return DeathCause.DISEASE

    # Rare accident hazard (slightly higher during storms outside)
    acc_prob = 0.0005 if (env.weather is Weather.STORM and not in_house) else 0.0001
    if rng.random() < acc_prob:
        agent.health = max(0.0, agent.health - 2.0)
        if agent.health <= 0.0:
            agent.alive = False
            return DeathCause.ACCIDENT

    return None


def can_mate_animals(a: AnimalAgent, b: AnimalAgent, max_dist: int = 3) -> bool:
    """Return True if two animals are mature, well fed, nearby, and genetically compatible."""
    if a is b or not a.alive or not b.alive or a.species != b.species:
        return False
    if a.stage is not LifeStage.ADULT or b.stage is not LifeStage.ADULT:
        return False
    if a.breed_timer > 0 or b.breed_timer > 0:
        return False
    if a.needs.hunger < 6.0 or b.needs.hunger < 6.0:
        return False
    if abs(a.x - b.x) + abs(a.y - b.y) > max_dist:
        return False
    return genetic_distance(a.genome, b.genome) <= 0.55


def _are_close_kin(a: HumanAgent, b: HumanAgent) -> bool:
    """Prevent parent-child and sibling pairing."""
    if b.id in a.family.parents or a.id in b.family.parents:
        return True
    return bool(set(a.family.parents) & set(b.family.parents))


def can_pair_humans(a: HumanAgent, b: HumanAgent) -> bool:
    """Return True if two adult humans can form a partnership by affinity & compatibility."""
    if a is b or not a.alive or not b.alive:
        return False
    if a.stage is not LifeStage.ADULT or b.stage is not LifeStage.ADULT:
        return False
    if a.family.partner is not None or b.family.partner is not None:
        return False
    if _are_close_kin(a, b):
        return False
    affinity = (a.relationships.get(b.id, 0.0) + b.relationships.get(a.id, 0.0)) / 2.0
    if affinity < 2.0:
        return False
    return genetic_distance(a.genome, b.genome) <= 0.55


def spawn_human_child(
    parent_a: HumanAgent,
    parent_b: HumanAgent,
    world: WorldMap,
    rng: random.Random,
    child_id: str,
) -> HumanAgent:
    """Create a human child inheriting crossed/mutated genes, surname, home, and knowledge."""
    from agents.base import Needs
    from agents.culture import inherit_culture
    from agents.human import HumanAgent, Persona

    child_genome = mutate(crossover(parent_a.genome, parent_b.genome, rng=rng), rate=0.15, rng=rng)
    # Skin tone adapts gradually toward local latitude UV/sunlight over many generations
    pos = parent_a.home or parent_a.position
    sunlight = max(0.05, min(0.95, 1.0 - abs(pos[1] - world.height / 2.0) / max(1.0, world.height / 2.0)))
    cur_skin = child_genome.get("skin_tone", 0.5)
    child_genome["skin_tone"] = round(max(0.05, min(0.95, cur_skin + (sunlight - cur_skin) * 0.08 + rng.gauss(0.0, 0.02))), 3)
    child_genome.setdefault("hair_tone", round(rng.uniform(0.1, 0.9), 3))
    child_culture = inherit_culture(parent_a, parent_b, rng=rng)
    surname = parent_a.family.surname or parent_b.family.surname or "Village"
    given = rng.choice(CHILD_GIVEN_NAMES)
    full_name = f"{given} {surname}"
    job = rng.choice([parent_a.persona.job, parent_b.persona.job])

    # Inherit a fraction of parents' learned skills
    inherited_skills: dict[str, float] = {}
    for skill in set(parent_a.skills) | set(parent_b.skills):
        avg = (parent_a.skills.get(skill, 0.0) + parent_b.skills.get(skill, 0.0)) / 2.0
        inherited_skills[skill] = round(avg * 0.35, 2)

    child = HumanAgent(
        id=child_id,
        name=full_name,
        position=parent_a.home or parent_a.position,
        home=parent_a.home or parent_a.position,
        persona=Persona(name=full_name, age=0, job=job, traits=("curious",), goal="Grow and learn"),
        needs=Needs(hunger=8.0, energy=8.5, social=8.5),
        genome=child_genome,
        culture=child_culture,
        family=FamilyTree(
            surname=surname,
            lineage_id=parent_a.family.lineage_id or parent_a.id,
            parents=(parent_a.id, parent_b.id),
        ),
        skills=inherited_skills,
        age_ticks=0,
        sex=rng.choice(("M", "F")),
    )
    parent_a.family.children.append(child.id)
    parent_b.family.children.append(child.id)
    child.adjust_affinity(parent_a.id, 6.0)
    child.adjust_affinity(parent_b.id, 6.0)
    parent_a.adjust_affinity(child.id, 7.0)
    parent_b.adjust_affinity(child.id, 7.0)
    parent_a.memory.add(f"Had a child named {full_name}", world.environment.tick, importance=8)
    parent_b.memory.add(f"Had a child named {full_name}", world.environment.tick, importance=8)
    return child


def child_learn_from_adults(
    child: HumanAgent,
    adults: list[HumanAgent],
    tick: int,
) -> str | None:
    """Allow a child to learn a job skill by watching a nearby adult."""
    nearby = [
        a for a in adults
        if a.alive and a.stage is LifeStage.ADULT
        and abs(a.x - child.x) + abs(a.y - child.y) <= 3
    ]
    if not nearby:
        return None
    mentor = nearby[0]
    skill = mentor.persona.job
    gain = round(0.15 * express_phenotype(child.genome).learning_rate, 3)
    child.skills[skill] = round(min(10.0, child.skills.get(skill, 0.0) + gain), 3)
    if tick % 24 == 0:
        child.memory.add(f"Learned {skill} by watching {mentor.name}", tick, importance=3)
    return skill
