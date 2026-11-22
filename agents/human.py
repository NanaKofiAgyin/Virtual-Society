"""Human agent with persona, genome, family tree, life cycle, memory, and speech."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agents.base import Action, ActionType, Agent
from agents.culture import CulturalProfile
from agents.genome import Genome, express_phenotype, random_genome
from agents.lifecycle import (
    TICKS_PER_YEAR,
    DeathCause,
    FamilyTree,
    LifeStage,
    apply_environmental_hazards,
    compute_life_stage,
)
from agents.memory import MemoryStream
from agents.utility import run_human_tick
from llm.prompts import (
    build_plan_prompt,
    build_reflect_prompt,
    build_speech_prompt,
    template_plan,
    template_reflection,
    template_speech,
)
from world.tile import TerrainType

if TYPE_CHECKING:
    from llm.client import LLMClient
    from world.map import WorldMap

BASE_HUMAN_LIFESPAN_YEARS = 65


@dataclass(frozen=True)
class Persona:
    """Identity and role configuration for a human villager."""

    name: str
    age: int = 25
    job: str = "farmer"
    traits: tuple[str, ...] = ("kind", "curious")
    goal: str = "Help the village thrive"

    def to_dict(self) -> dict[str, Any]:
        """Serialize persona fields to a dictionary."""
        return {
            "name": self.name, "age": self.age, "job": self.job,
            "traits": list(self.traits), "goal": self.goal,
        }


@dataclass
class HumanAgent(Agent):
    """Human villager with genome, life cycle, family tree, memory, and optional LLM."""

    persona: Persona | None = None
    home: tuple[int, int] | None = None
    relationships: dict[str, float] = field(default_factory=dict)
    memory: MemoryStream = field(default_factory=MemoryStream)
    genome: Genome = field(default_factory=lambda: random_genome(rng=random.Random(0)))
    family: FamilyTree = field(default_factory=FamilyTree)
    culture: CulturalProfile = field(default_factory=CulturalProfile)
    skills: dict[str, float] = field(default_factory=dict)
    age_ticks: int = 20 * TICKS_PER_YEAR
    breed_timer: int = 0
    death_cause: DeathCause | None = None
    last_action: str = "idle"
    last_speech: str = ""
    daily_plan: str = ""
    last_reflection: str = ""
    hunger_decay: float = 0.20
    energy_decay: float = 0.20
    _last_plan_day: int = field(default=-1, repr=False)
    _last_reflect_day: int = field(default=-1, repr=False)

    def __post_init__(self) -> None:
        if self.persona is None:
            self.persona = Persona(name=self.name)
        else:
            self.name = self.persona.name
        if self.home is None:
            self.home = self.position
        if not self.family.lineage_id:
            self.family.lineage_id = self.id
        if not self.family.surname and " " in self.name:
            self.family.surname = self.name.split()[-1]

    @property
    def max_age_ticks(self) -> int:
        """Maximum natural lifespan in ticks modulated by genome."""
        factor = express_phenotype(self.genome).effective_lifespan_factor
        return max(10 * TICKS_PER_YEAR, int(BASE_HUMAN_LIFESPAN_YEARS * TICKS_PER_YEAR * factor))

    @property
    def age_years(self) -> float:
        """Current age expressed in simulated years."""
        return round(self.age_ticks / TICKS_PER_YEAR, 1)

    @property
    def stage(self) -> LifeStage:
        """Current developmental life stage (child, adult, elder)."""
        return compute_life_stage(self.age_ticks, self.max_age_ticks)

    def adjust_affinity(self, other_id: str, delta: float) -> float:
        """Adjust relationship affinity with `other_id`, clamped to [-10.0, 10.0]."""
        updated = max(-10.0, min(10.0, round(self.relationships.get(other_id, 0.0) + delta, 2)))
        self.relationships[other_id] = updated
        return updated

    def speak(
        self,
        listener: HumanAgent,
        world: WorldMap,
        llm_client: LLMClient | None,
        rng: random.Random,
    ) -> str:
        """Say a line to `listener` using live Ollama + memories if available, else templates."""
        tick, env = world.environment.tick, world.environment
        memories = self.memory.retrieve(f"{listener.name} {self.persona.job}", tick, k=3)
        line = ""
        if llm_client is not None and llm_client.is_live():
            system, user = build_speech_prompt(self, listener, env, memories)
            reply = llm_client.ask(system, user, json=True, model_tier="cheap", required=("speech",))
            if isinstance(reply, dict) and not reply.get("_fallback") and reply.get("speech"):
                line = str(reply["speech"]).strip()
        if not line:
            line = template_speech(self, listener, env, rng)

        self.last_speech = line
        self.needs.adjust(social=2.5)
        listener.needs.adjust(social=2.0)
        self.adjust_affinity(listener.id, 0.5)
        listener.adjust_affinity(self.id, 0.5)
        self.memory.add(f"Talked with {listener.name}: {line}", tick)
        listener.memory.add(f"Talked with {self.name}: {line}", tick)
        return line

    def make_daily_plan(self, world: WorldMap, llm_client: LLMClient | None = None) -> str:
        """Generate a one-sentence 06:00 daily plan and save it as a memory."""
        env = world.environment
        memories = self.memory.retrieve(f"{self.persona.job} {env.season.value}", env.tick, k=3)
        plan = ""
        if llm_client is not None and llm_client.is_live():
            system, user = build_plan_prompt(self, env, memories)
            reply = llm_client.ask(system, user, json=True, model_tier="main", required=("plan",))
            if isinstance(reply, dict) and not reply.get("_fallback") and reply.get("plan"):
                plan = str(reply["plan"]).strip()
        if not plan:
            plan = template_plan(self, env)
        self.daily_plan, self._last_plan_day = plan, env.day
        self.memory.add(f"Daily plan: {plan}", env.tick, importance=4)
        return plan

    def write_reflection(self, world: WorldMap, llm_client: LLMClient | None = None) -> str:
        """Write a 23:00 reflection from the day's memories and save it as a memory."""
        env = world.environment
        day_mems = [m for m in self.memory.recent(24) if env.tick - m.tick < 24]
        reflection = ""
        if llm_client is not None and llm_client.is_live():
            system, user = build_reflect_prompt(self, env, day_mems)
            reply = llm_client.ask(system, user, json=True, model_tier="main", required=("reflection",))
            if isinstance(reply, dict) and not reply.get("_fallback") and reply.get("reflection"):
                reflection = str(reply["reflection"]).strip()
        if not reflection:
            reflection = template_reflection(self, env, day_mems)
        self.last_reflection, self._last_reflect_day = reflection, env.day
        self.memory.add(f"Reflection: {reflection}", env.tick, importance=5)
        return reflection

    def decide(self, world: WorldMap, nearby_agents: list[Agent]) -> Action:
        if self.exhausted or world.environment.is_night:
            return Action(type=ActionType.SLEEP)
        if self.needs.hunger < 4.0:
            return Action(type=ActionType.EAT)
        return Action(type=ActionType.TALK if self.needs.social < 5.0 else ActionType.WORK)

    def step(
        self,
        world: WorldMap,
        agents: list[Agent],
        rng: random.Random,
        llm_client: LLMClient | None = None,
    ) -> str:
        """Age, update needs & hazards, run 06:00/23:00 hooks, and execute priority brain."""
        if not self.alive:
            self.last_action = "dead"
            return self.last_action

        self.age_ticks += 1
        self.breed_timer = max(0, self.breed_timer - 1)
        if self.age_ticks >= self.max_age_ticks:
            self.alive, self.death_cause, self.last_action = False, DeathCause.OLD_AGE, "dead"
            self.memory.add(f"{self.name} died of old age", world.environment.tick)
            return self.last_action

        events = self.update_needs()
        if not self.alive:
            self.death_cause = DeathCause.STARVATION if self.starving else DeathCause.INJURY
            self.memory.add(f"{self.name} died", world.environment.tick)
            self.last_action = "dead"
            return self.last_action

        cur_tile = world.get_tile(self.x, self.y)
        in_house = cur_tile is not None and cur_tile.terrain is TerrainType.HOUSE
        hazard = apply_environmental_hazards(self, world.environment, self.genome, rng, in_house=in_house)
        if hazard is not None:
            self.death_cause, self.last_action = hazard, "dead"
            self.memory.add(f"{self.name} died from {hazard.value}", world.environment.tick)
            return self.last_action

        if "starving" in events:
            self.memory.add("I am starving and need food", world.environment.tick, importance=6)

        env = world.environment
        if env.hour == 6 and self._last_plan_day != env.day:
            self.make_daily_plan(world, llm_client=llm_client)
        elif env.hour == 23 and self._last_reflect_day != env.day:
            self.write_reflection(world, llm_client=llm_client)

        self.last_action = run_human_tick(self, world, agents, rng, llm_client=llm_client)
        return self.last_action

    def detail(self) -> dict[str, Any]:
        """Return detailed human state for the HTML/JS viewer inspector panel."""
        return {
            **self.to_dict(),
            "persona": self.persona.to_dict() if self.persona else {},
            "stage": self.stage.value,
            "age_years": self.age_years,
            "home": list(self.home) if self.home else list(self.position),
            "family": self.family.to_dict(),
            "culture": self.culture.to_dict(),
            "skills": dict(self.skills),
            "death_cause": self.death_cause.value if self.death_cause else None,
            "relationships": dict(self.relationships),
            "last_action": self.last_action,
            "last_speech": self.last_speech,
            "daily_plan": self.daily_plan,
            "last_reflection": self.last_reflection,
            "memories": [m.to_dict() for m in self.memory.recent(10)],
        }
