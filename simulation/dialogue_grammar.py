"""Rule-based multi-turn dialogue grammar, speech styles, vocabulary, and gossip distortion."""

from __future__ import annotations

import random
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.human import HumanAgent
    from world.environment import Environment


class ConversationPurpose(str, Enum):
    """Twelve distinct purposes driving multi-turn human conversations."""

    GREETING = "greeting"
    GOSSIP = "gossip"
    TRADE_NEGOTIATION = "trade_negotiation"
    TEACHING_SKILL = "teaching_skill"
    ASKING_FOR_HELP = "asking_for_help"
    COMFORTING = "comforting"
    ARGUING = "arguing"
    COURTING = "courting"
    PLANNING_HUNT_MIGRATION = "planning_hunt_migration"
    TELLING_STORY = "telling_story"
    SETTLING_DISPUTE = "settling_dispute"
    MOURNING = "mourning"


IMPORTANT_PURPOSES = frozenset({
    ConversationPurpose.TRADE_NEGOTIATION,
    ConversationPurpose.SETTLING_DISPUTE,
    ConversationPurpose.COURTING,
    ConversationPurpose.PLANNING_HUNT_MIGRATION,
})

VALID_DIALOGUE_ACTIONS: tuple[str, ...] = (
    "agree", "trade", "teach", "befriend", "rival",
    "court", "ally", "migrate", "comfort", "resolve", "part_ways",
)

STYLE_PREFIXES: dict[str, tuple[str, ...]] = {
    "warm":   ("My friend,", "Listen kindly,", "Glad to see you,", "Walk with me,"),
    "terse":  ("Quickly:", "Look,", "Hear me:", "Plainly,"),
    "poetic": ("Under this sky,", "As the seasons turn,", "By hearth and wind,", "Mark these words,"),
    "formal": ("By our custom,", "In all fairness,", "Let it be known,", "Speaking plainly,"),
    "blunt":  ("Enough talk,", "Face facts,", "Don't fool yourself,", "Honestly,"),
}

DISTORTION_SWAPS: tuple[tuple[str, str], ...] = (
    ("abundant", "scarce"), ("scarce", "abundant"),
    ("north", "east"), ("south", "west"),
    ("safe", "dangerous"), ("friendly", "suspicious"),
    ("rich", "barren"), ("calm", "restless"),
)


def speech_style_of(human: HumanAgent) -> str:
    """Derive a consistent speech style from personality traits and cultural norms."""
    traits = {t.lower() for t in (human.persona.traits if human.persona else ())}
    peace = human.culture.norms.get("peacefulness", 0.5)
    law = human.culture.norms.get("lawfulness", 0.5)
    if "bold" in traits or peace < 0.38:
        return "blunt"
    if "curious" in traits or (human.persona and human.persona.job == "storyteller"):
        return "poetic"
    if law > 0.68:
        return "formal"
    if "resilient" in traits and human.genome.get("sociability", 0.5) < 0.45:
        return "terse"
    return "warm"


def distort_claim(claim: str, rng: random.Random) -> tuple[str, bool]:
    """Slightly distort a rumored claim during gossip retelling; returns `(new_claim, flipped)`."""
    if rng.random() > 0.45:
        return claim, False
    for old, new in DISTORTION_SWAPS:
        if old in claim:
            return claim.replace(old, new, 1), True
    return f"they say {claim}", False


def _dialect_word(human: HumanAgent, concept: str) -> str:
    return human.culture.language.get(concept, concept)


def _recent_observation(human: HumanAgent) -> str:
    mems = human.memory.recent(4)
    for m in reversed(mems):
        if m.text and not m.text.startswith("Talked with"):
            return m.text[:58]
    return f"working as a {human.persona.job if human.persona else 'villager'}"


def _favorite_other(human: HumanAgent, names_by_id: dict[str, str]) -> str:
    if not human.relationships:
        return "the elders"
    best_id = max(human.relationships, key=lambda k: human.relationships[k])
    return names_by_id.get(best_id, "our kin")


def compose_turn_line(
    speaker: HumanAgent,
    listener: HumanAgent,
    purpose: ConversationPurpose,
    turn_idx: int,
    env: Environment,
    place: str,
    context: dict[str, Any],
    spoken_today: set[str],
    rng: random.Random,
) -> str:
    """Generate a non-repeating, state-grounded dialogue line using speaker's style & dialect."""
    style = speech_style_of(speaker)
    job = speaker.persona.job if speaker.persona else "villager"
    season, weather = env.season.value, env.weather.value
    obs = _recent_observation(speaker)
    food_w = _dialect_word(speaker, "food")
    home_w = _dialect_word(speaker, "home")
    friend_w = _dialect_word(speaker, "friend")
    fire_w = _dialect_word(speaker, "fire")
    belief_claim = context.get("belief_claim", f"the {place} trails are safe this {season}")
    fear = context.get("fear", "winter hunger")
    tech = context.get("tech", "stone_tools")
    fav = _favorite_other(speaker, context.get("names_by_id", {}))

    bank: dict[ConversationPurpose, tuple[str, ...]] = {
        ConversationPurpose.GREETING: (
            f"may your {home_w} stay warm through this {weather} {season}, {listener.name}.",
            f"I was just {obs} near the {place}—how fares your work?",
            f"good to cross paths in the {place}, {friend_w}; the {season} air feels crisp.",
        ),
        ConversationPurpose.GOSSIP: (
            f"word around {fav} is that {belief_claim}.",
            f"have you heard? Some swear {belief_claim}, though I wonder.",
            f"earlier in the {place} I noticed {obs}, and folks still whisper {belief_claim}.",
        ),
        ConversationPurpose.TRADE_NEGOTIATION: (
            f"as a {job}, I can spare extra {food_w} if you bring timber or stone.",
            f"with {weather} skies in {season}, fair trade keeps every {home_w} supplied.",
            f"let us strike an honest bargain before {fear} catches the {place} unprepared.",
        ),
        ConversationPurpose.TEACHING_SKILL: (
            f"watch closely—mastering {tech} takes patience and steady hands in {season}.",
            f"my elders taught me {job} craft by the {fire_w}; let me pass {tech} to you.",
            f"practice this step beside me, {listener.name}, and you will outgrow {fear}.",
        ),
        ConversationPurpose.ASKING_FOR_HELP: (
            f"my stores of {food_w} run thin after {obs}; could you lend a hand?",
            f"I fear {fear} this {season}, {listener.name}—would you stand with me?",
            f"a {job} alone cannot mend everything in the {place} during {weather} weather.",
        ),
        ConversationPurpose.COMFORTING: (
            f"rest by the {fire_w}, {friend_w}; even harsh {season} storms pass.",
            f"you are not alone against {fear}—{fav} and I still have your back.",
            f"take heart, {listener.name}; tomorrow in the {place} will be gentler.",
        ),
        ConversationPurpose.ARGUING: (
            f"your carelessness in the {place} puts our {food_w} at risk!",
            f"I saw {obs} with my own eyes—stop claiming {belief_claim}!",
            f"we cannot afford foolishness while {fear} hangs over this {season}.",
        ),
        ConversationPurpose.COURTING: (
            f"whenever I see you in the {place}, {listener.name}, the {season} feels brighter.",
            f"what if we shared a {home_w} and built a future together by the {fire_w}?",
            f"even {fav} notices how well our paths fit, {friend_w}.",
        ),
        ConversationPurpose.PLANNING_HUNT_MIGRATION: (
            f"tracks in the {place} point toward richer game; should we move camp this {season}?",
            f"if {fear} deepens under this {weather}, migrating together could save our {home_w}.",
            f"bring your sharpest {tech} tools—a coordinated trek beats wandering alone.",
        ),
        ConversationPurpose.TELLING_STORY: (
            f"gather by the {fire_w}: I still remember {obs} from earlier in {season}.",
            f"our people call hearth '{home_w}' because ancestors survived {fear} together.",
            f"long before this {weather} day, a {job} learned {tech} and changed our fate.",
        ),
        ConversationPurpose.SETTLING_DISPUTE: (
            f"let us weigh both sides calmly so the {place} stays united in {season}.",
            f"sharing {food_w} fairly beats letting old grudges split our {home_w}.",
            f"shake hands, {listener.name}, and leave this quarrel behind by the {fire_w}.",
        ),
        ConversationPurpose.MOURNING: (
            f"the {place} feels quieter today; we will remember the fallen by the {fire_w}.",
            f"even in grief this {season}, their lessons in {tech} live on in us.",
            f"stand close, {friend_w}; mourning together keeps our {home_w} strong.",
        ),
    }

    prefixes = STYLE_PREFIXES[style]
    cores = bank[purpose]
    # Try combinations to guarantee zero repetition within the same simulated day
    for attempt in range(12):
        pre = prefixes[(turn_idx + attempt + rng.randrange(len(prefixes))) % len(prefixes)]
        core = cores[(turn_idx + attempt) % len(cores)]
        suffix = "" if attempt < 4 else f" ({season}, turn {turn_idx + 1})"
        line = f"{pre} {core}{suffix}"
        if line not in spoken_today:
            spoken_today.add(line)
            return line
    fallback = f"{prefixes[0]} {cores[0]} [{speaker.name}->{listener.name} t{env.tick}]"
    spoken_today.add(fallback)
    return fallback
