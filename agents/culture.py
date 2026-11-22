"""Cultural evolution: data-driven tech tree, teaching, knowledge loss, drift, and settlements."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents.genome import express_phenotype

if TYPE_CHECKING:
    from agents.human import HumanAgent

DEFAULT_TECH_PATH = Path(__file__).resolve().parent.parent / "data" / "tech.json"
BASE_WORDS: dict[str, str] = {"food": "noma", "water": "sula", "home": "kora", "friend": "vela", "fire": "tara"}
VOWELS = "aeiou"
CONSONANTS = "klmnprstv"
ERA_ORDER = ("paleolithic", "neolithic", "bronze_age", "iron_age")
ERA_LABELS = {
    "paleolithic": "Stone Age", "neolithic": "Neolithic Era",
    "bronze_age": "Bronze Age", "iron_age": "Iron Age",
}


@dataclass(frozen=True)
class TechSpec:
    """Single technology node loaded from `data/tech.json`."""

    name: str
    era: str
    prereqs: tuple[str, ...]
    materials: dict[str, float]
    min_experience: float
    base_chance: float
    effect: str


def load_techs(path: Path | str = DEFAULT_TECH_PATH) -> dict[str, TechSpec]:
    """Load technology definitions from JSON."""
    raw: dict[str, dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: TechSpec(
            name=name, era=str(c["era"]), prereqs=tuple(c.get("prereqs", ())),
            materials={k: float(v) for k, v in c.get("materials", {}).items()},
            min_experience=float(c.get("min_experience", 0.5)),
            base_chance=float(c.get("base_chance", 0.05)), effect=str(c.get("effect", "")),
        )
        for name, c in raw.items()
    }


@dataclass
class CulturalProfile:
    """Individual human's learned technologies, language, norms, beliefs, and group identity."""

    known_techs: set[str] = field(default_factory=set)
    language: dict[str, str] = field(default_factory=lambda: dict(BASE_WORDS))
    norms: dict[str, float] = field(default_factory=lambda: {"sharing": 0.6, "lawfulness": 0.5, "peacefulness": 0.6})
    beliefs: list[str] = field(default_factory=lambda: ["nature_spirits"])
    group_id: str = "group_1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id, "known_techs": sorted(self.known_techs),
            "language": dict(self.language),
            "norms": {k: round(v, 2) for k, v in self.norms.items()},
            "beliefs": list(self.beliefs),
        }


def mutate_word(word: str, rng: random.Random) -> str:
    """Apply a small phonetic shift to a word so isolated languages drift over generations."""
    if not word:
        return word
    chars = list(word)
    idx = rng.randrange(len(chars))
    chars[idx] = rng.choice(VOWELS if chars[idx] in VOWELS else CONSONANTS)
    return "".join(chars)


def inherit_culture(parent_a: HumanAgent, parent_b: HumanAgent, rng: random.Random) -> CulturalProfile:
    """Pass parental techs, slightly mutated language, norms, and group identity to a child."""
    ca, cb = parent_a.culture, parent_b.culture
    shared_techs = {t for t in ca.known_techs | cb.known_techs if rng.random() < 0.70}
    lang = {
        k: (mutate_word(w, rng) if rng.random() < 0.25 else w)
        for k in BASE_WORDS
        for w in [ca.language.get(k, BASE_WORDS[k]) if rng.random() < 0.5 else cb.language.get(k, BASE_WORDS[k])]
    }
    norms = {
        k: max(0.0, min(1.0, (ca.norms.get(k, 0.5) + cb.norms.get(k, 0.5)) / 2.0 + rng.gauss(0.0, 0.05)))
        for k in ("sharing", "lawfulness", "peacefulness")
    }
    beliefs = list(dict.fromkeys([*ca.beliefs[:2], *cb.beliefs[:1]]))
    return CulturalProfile(shared_techs, lang, norms, beliefs, ca.group_id)


def cultural_distance(a: CulturalProfile, b: CulturalProfile) -> float:
    """Measure linguistic + norm divergence in [0.0, 1.0] between two cultural profiles."""
    word_diffs = sum(1.0 for k in BASE_WORDS if a.language.get(k) != b.language.get(k)) / len(BASE_WORDS)
    norm_keys = ("sharing", "lawfulness", "peacefulness")
    norm_diffs = sum(abs(a.norms.get(k, 0.5) - b.norms.get(k, 0.5)) for k in norm_keys) / len(norm_keys)
    return round(0.6 * word_diffs + 0.4 * norm_diffs, 4)


def attempt_discovery(
    human: HumanAgent,
    nearby_humans: list[HumanAgent],
    group_size: int,
    techs: dict[str, TechSpec],
    rng: random.Random,
) -> str | None:
    """Attempt an emergent tech discovery based on curiosity, materials, skills, and contact."""
    if not human.alive:
        return None
    max_exp = max(human.skills.values(), default=0.0)
    learn = express_phenotype(human.genome).learning_rate
    curious_mult = 1.4 if (human.persona and "curious" in human.persona.traits) else 1.0
    pop_mult = 1.0 + 0.35 * math.log1p(max(1, group_size))
    inter_group = any(o.culture.group_id != human.culture.group_id for o in nearby_humans if o.alive)
    contact_mult = 1.5 if inter_group else (1.15 if nearby_humans else 0.85)

    for tech in techs.values():
        if tech.name in human.culture.known_techs:
            continue
        if not all(p in human.culture.known_techs for p in tech.prereqs):
            continue
        if max_exp < tech.min_experience:
            continue
        if any(human.inventory.get(m, 0.0) < amt for m, amt in tech.materials.items()):
            continue
        prob = min(0.85, tech.base_chance * learn * curious_mult * pop_mult * contact_mult)
        if rng.random() < prob:
            human.culture.known_techs.add(tech.name)
            return tech.name
    return None


def spread_knowledge(teacher: HumanAgent, student: HumanAgent, rng: random.Random) -> str | None:
    """Transfer one technology from `teacher` to `student` and slightly blend language/norms."""
    if not teacher.alive or not student.alive:
        return None
    teachable = [t for t in teacher.culture.known_techs if t not in student.culture.known_techs]
    if not teachable:
        return None
    prob = 0.35 + 0.45 * express_phenotype(student.genome).learning_rate
    if rng.random() < prob:
        tech = rng.choice(sorted(teachable))
        student.culture.known_techs.add(tech)
        # Slight linguistic convergence on contact
        key = rng.choice(list(BASE_WORDS.keys()))
        if rng.random() < 0.25:
            student.culture.language[key] = teacher.culture.language.get(key, BASE_WORDS[key])
        return tech
    return None


@dataclass
class Settlement:
    """Emergent human settlement formed by spatial clustering of villagers."""

    id: str
    center: tuple[int, int]
    member_ids: list[str]
    leader_id: str | None = None
    laws: list[str] = field(default_factory=list)
    surplus_food: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "center": list(self.center),
            "population": len(self.member_ids), "leader_id": self.leader_id,
            "laws": list(self.laws), "surplus_food": round(self.surplus_food, 1),
        }


def determine_era(known_techs: set[str], techs: dict[str, TechSpec]) -> str:
    """Return human-readable era name from currently living technologies."""
    best_idx = 0
    for name in known_techs:
        spec = techs.get(name)
        if spec and spec.era in ERA_ORDER:
            best_idx = max(best_idx, ERA_ORDER.index(spec.era))
    return ERA_LABELS[ERA_ORDER[best_idx]]


def step_society(
    humans: list[HumanAgent],
    techs: dict[str, TechSpec],
    ever_discovered: set[str],
    rng: random.Random,
    tick: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run cultural discovery, teaching, settlement leadership/laws, trade/conflict, and loss."""
    live = [h for h in humans if h.alive]
    events: list[dict[str, Any]] = []

    # 1) Emergent settlements via simple spatial clustering (radius <= 14)
    settlements: list[Settlement] = []
    unassigned = list(live)
    while unassigned:
        seed_h = unassigned.pop(0)
        cluster = [seed_h]
        rest = []
        for o in unassigned:
            if abs(o.x - seed_h.x) + abs(o.y - seed_h.y) <= 14:
                cluster.append(o)
            else:
                rest.append(o)
        unassigned = rest
        sid = f"settlement_{len(settlements) + 1}"
        cx = sum(h.x for h in cluster) // len(cluster)
        cy = sum(h.y for h in cluster) // len(cluster)
        surplus = sum(max(0.0, h.inventory.get("food", 0.0) - 2.0) for h in cluster)
        leader = max(cluster, key=lambda h: h.genome.get("sociability", 0.5) + h.genome.get("intelligence", 0.5))
        avg_law = sum(h.culture.norms.get("lawfulness", 0.5) for h in cluster) / len(cluster)
        laws = ["share_harvest", "protect_settlement"] if (len(cluster) >= 5 and avg_law >= 0.45) else []
        for h in cluster:
            h.culture.group_id = sid
        settlements.append(Settlement(sid, (cx, cy), [h.id for h in cluster], leader.id, laws, surplus))

    # 2) Discovery & teaching among nearby humans
    group_sizes = {s.id: len(s.member_ids) for s in settlements}
    for h in live:
        nearby = [o for o in live if o is not h and abs(o.x - h.x) + abs(o.y - h.y) <= 4]
        new_tech = attempt_discovery(h, nearby, group_sizes.get(h.culture.group_id, 1), techs, rng)
        if new_tech:
            ever_discovered.add(new_tech)
            events.append({"tick": tick, "kind": "discovery", "message": f"{h.name} discovered {new_tech}"})
        if nearby:
            taught = spread_knowledge(h, nearby[0], rng)
            if taught:
                events.append({"tick": tick, "kind": "teaching", "message": f"{h.name} taught {taught} to {nearby[0].name}"})

    # 3) Check for lost technologies (known previously, but 0 living humans know it now)
    active_techs: set[str] = set()
    for h in live:
        active_techs.update(h.culture.known_techs)
    lost_techs = sorted(ever_discovered - active_techs)

    summary = {
        "tech_count": len(active_techs), "known_techs": sorted(active_techs),
        "lost_techs": lost_techs, "era": determine_era(active_techs, techs),
        "settlements": [s.to_dict() for s in settlements],
        "population_per_settlement": {s.id: len(s.member_ids) for s in settlements},
    }
    return summary, events
