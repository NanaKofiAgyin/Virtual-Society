"""Prompt builders and free templates for human talk, daily plans, and reflections."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from world.environment import Weather

if TYPE_CHECKING:
    from agents.human import HumanAgent
    from agents.memory import Memory
    from world.environment import Environment

_JOB_LINES: dict[str, tuple[str, ...]] = {
    "farmer": (
        "The crops need tending before dusk.",
        "Looks like a decent harvest this season.",
    ),
    "woodcutter": (
        "I'm heading back to the forest for timber.",
        "Good firewood will keep us warm come winter.",
    ),
    "hunter": (
        "I only take what we need so the herds stay strong.",
        "I spotted fresh tracks near the treeline.",
    ),
    "builder": (
        "We'll need plenty of timber before raising another house.",
        "A sturdy roof makes all the difference in a storm.",
    ),
    "healer": (
        "Let me know if anyone is feeling worn down.",
        "Rest and warm food cure most troubles.",
    ),
    "teacher": (
        "There is always something new to learn from the village.",
        "Let's pass down what we've learned this season.",
    ),
    "trader": (
        "If you have spare wood or food, let's make a fair swap.",
        "Keeping supplies moving helps the whole village.",
    ),
    "storyteller": (
        "Gather round later—I have a tale about the old forest.",
        "Every season brings a story worth remembering.",
    ),
}


def persona_system_prompt(human: HumanAgent, json_format: str) -> str:
    """Build a concise persona system prompt asking for a short JSON answer."""
    p = human.persona
    assert p is not None
    return (
        f"You are {p.name}, a {p.age}-year-old {p.job} "
        f"(traits: {', '.join(p.traits)}). Goal: {p.goal}. "
        f"Reply with valid JSON only, keeping the answer to 1 short sentence: {json_format}."
    )


def build_speech_prompt(
    speaker: HumanAgent,
    listener: HumanAgent,
    env: Environment,
    memories: list[Memory],
) -> tuple[str, str]:
    """Build (system, user) prompts for a short JSON conversation line."""
    system = persona_system_prompt(speaker, '{"speech": "..."}')
    mem_text = "; ".join(m.text for m in memories) if memories else "none"
    user = (
        f"Talking to {listener.name} ({listener.persona.job}). "
        f"Season: {env.season.value}, weather: {env.weather.value}, hour: {env.hour:02d}:00. "
        f"Hunger: {speaker.needs.hunger:.1f}/10, energy: {speaker.needs.energy:.1f}/10. "
        f"Memories: {mem_text}."
    )
    return system, user


def build_plan_prompt(
    human: HumanAgent,
    env: Environment,
    memories: list[Memory],
) -> tuple[str, str]:
    """Build (system, user) prompts for a one-sentence 06:00 daily plan in JSON."""
    system = persona_system_prompt(human, '{"plan": "..."}')
    mem_text = "; ".join(m.text for m in memories) if memories else "none"
    user = (
        f"It is 06:00 on Day {env.day} of {env.season.value} ({env.weather.value}). "
        f"Hunger: {human.needs.hunger:.1f}/10, food in bag: {human.inventory.get('food', 0.0):.1f}. "
        f"Recent memories: {mem_text}. What is your one-sentence plan for today?"
    )
    return system, user


def build_reflect_prompt(
    human: HumanAgent,
    env: Environment,
    day_memories: list[Memory],
) -> tuple[str, str]:
    """Build (system, user) prompts for a 23:00 nightly reflection in JSON."""
    system = persona_system_prompt(human, '{"reflection": "..."}')
    mem_text = "; ".join(m.text for m in day_memories) if day_memories else "a quiet day"
    user = (
        f"It is 23:00 on Day {env.day} of {env.season.value}. "
        f"Today's memories: {mem_text}. "
        "Write a short one-sentence reflection on your day."
    )
    return system, user


def template_speech(
    speaker: HumanAgent,
    listener: HumanAgent,
    env: Environment,
    rng: random.Random,
) -> str:
    """Return a free template dialogue line shaped by hunger, weather, and job."""
    if speaker.needs.hunger < 4.5:
        return f"Hey {listener.name}, my stomach is growling—have you seen any food?"
    if env.weather == Weather.STORM:
        return f"Stay safe, {listener.name}! This storm is fierce—head for shelter."
    if env.weather == Weather.RAIN:
        return f"Wet weather today, {listener.name}, though the rain helps the farms."

    job = speaker.persona.job.lower() if speaker.persona else "villager"
    lines = _JOB_LINES.get(job, ("Quiet day around the village, isn't it?",))
    return f"{listener.name}, {rng.choice(lines)}"


def template_plan(human: HumanAgent, env: Environment) -> str:
    """Return a free one-sentence daily plan based on hunger, weather, and job."""
    job = human.persona.job.lower() if human.persona else "villager"
    if human.needs.hunger < 4.5:
        return f"Today I will find food first, then return to my work as a {job}."
    if env.weather == Weather.STORM:
        return f"Today I will shelter from the storm and prepare for {job} work once it clears."
    return f"Today in {env.season.value} I will focus on my {job} duties and check on neighbors."


def template_reflection(human: HumanAgent, env: Environment, day_memories: list[Memory]) -> str:
    """Return a free one-sentence nightly reflection from the day's memories."""
    if not day_memories:
        return f"Day {env.day} of {env.season.value} was quiet and restful."
    highlight = max(day_memories, key=lambda m: (m.importance, m.tick))
    return f"Day {env.day} stood out because: {highlight.text}."
