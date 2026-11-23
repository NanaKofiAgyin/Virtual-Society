"""Data models for beliefs, person minds, conversation turns, and conversation logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Belief:
    """Something a person believes to be true (learned from experience or gossip; can be wrong)."""

    topic: str
    claim: str
    confidence: float = 0.8
    source_id: str = "experience"
    distortions: int = 0
    is_accurate: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic, "claim": self.claim, "confidence": round(self.confidence, 2),
            "source_id": self.source_id, "distortions": self.distortions, "is_accurate": self.is_accurate,
        }


@dataclass
class PersonMind:
    """Per-person mental state: beliefs, opinions, goals, fears, traits, and speech style."""

    beliefs: list[Belief] = field(default_factory=list)
    opinions: dict[str, float] = field(default_factory=dict)
    goals: list[str] = field(default_factory=list)
    fears: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    speech_style: str = "warm"

    def add_belief(self, belief: Belief, max_beliefs: int = 8) -> None:
        self.beliefs = [b for b in self.beliefs if b.topic != belief.topic]
        self.beliefs.append(belief)
        if len(self.beliefs) > max_beliefs:
            self.beliefs = self.beliefs[-max_beliefs:]

    def to_dict(self, names_by_id: dict[str, str] | None = None) -> dict[str, Any]:
        names = names_by_id or {}
        ops = [
            {"id": oid, "name": names.get(oid, oid), "score": round(sc, 2)}
            for oid, sc in sorted(self.opinions.items(), key=lambda kv: -kv[1])[:8]
        ]
        return {
            "beliefs": [b.to_dict() for b in self.beliefs[-6:]],
            "opinions": ops, "goals": list(self.goals[:3]),
            "fears": list(self.fears[:3]), "traits": list(self.traits),
            "speech_style": self.speech_style,
        }


@dataclass
class ConversationTurn:
    """Single spoken turn inside a multi-turn conversation."""

    speaker_id: str
    speaker_name: str
    line: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id, "speaker_name": self.speaker_name,
            "line": self.line, "action": self.action,
        }


@dataclass
class ConversationRecord:
    """Complete multi-turn conversation (3–10 turns) with place, purpose, and consequences."""

    id: str
    tick: int
    day: int
    place: str
    purpose: str
    participants: tuple[str, str]
    participant_names: tuple[str, str]
    turns: list[ConversationTurn]
    outcome: str
    consequences: list[str]
    used_llm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "tick": self.tick, "day": self.day, "place": self.place,
            "purpose": self.purpose, "participants": list(self.participants),
            "participant_names": list(self.participant_names),
            "turns": [t.to_dict() for t in self.turns],
            "outcome": self.outcome, "consequences": list(self.consequences), "used_llm": self.used_llm,
        }
