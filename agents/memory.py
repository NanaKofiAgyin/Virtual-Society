"""Free keyword-scored memory stream with recency + importance + overlap retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]+")

# Free keyword importance rules (highest match wins; default = 2)
IMPORTANCE_RULES: tuple[tuple[str, int], ...] = (
    ("died", 9),
    ("wolf", 7),
    ("gave", 6),
    ("shared", 6),
    ("talked", 3),
)
DEFAULT_IMPORTANCE = 2


def score_importance(text: str) -> int:
    """Score memory importance (1–10) using free keyword rules, never an LLM."""
    lowered = text.lower()
    best = DEFAULT_IMPORTANCE
    for keyword, score in IMPORTANCE_RULES:
        if keyword in lowered and score > best:
            best = score
    return best


def _tokens(text: str) -> set[str]:
    """Extract lowercase alphanumeric word tokens for keyword overlap scoring."""
    return set(_WORD_RE.findall(text.lower()))


@dataclass
class Memory:
    """A single episodic memory entry stored by a human agent."""

    text: str
    tick: int
    importance: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize memory to a JSON-friendly dictionary."""
        return {"text": self.text, "tick": self.tick, "importance": self.importance}


class MemoryStream:
    """Bounded memory store with free importance scoring and ranked retrieval."""

    def __init__(self, cap: int = 50) -> None:
        """Create a memory stream holding at most `cap` memories."""
        if cap <= 0:
            raise ValueError("cap must be positive")
        self.cap = cap
        self._memories: list[Memory] = []

    def __len__(self) -> int:
        return len(self._memories)

    def add(self, text: str, tick: int, importance: int | None = None) -> Memory:
        """Add a memory, auto-scoring importance and forgetting the least valuable if full."""
        score = score_importance(text) if importance is None else max(1, min(10, importance))
        mem = Memory(text=text, tick=tick, importance=score)
        self._memories.append(mem)
        if len(self._memories) > self.cap:
            self._forget_least_valuable(current_tick=tick)
        return mem

    def _forget_least_valuable(self, current_tick: int) -> None:
        """Drop the single oldest/least-important memory to stay within `self.cap`."""
        worst_idx = min(
            range(len(self._memories)),
            key=lambda i: self._retention_value(self._memories[i], current_tick),
        )
        self._memories.pop(worst_idx)

    @staticmethod
    def _retention_value(mem: Memory, current_tick: int) -> float:
        """Value score used for forgetting (higher = keep longer)."""
        age_days = max(0, current_tick - mem.tick) / 24.0
        recency = 1.0 / (1.0 + age_days)
        return (mem.importance / 10.0) * 0.7 + recency * 0.3

    def retrieve(self, query: str, current_tick: int, k: int = 5) -> list[Memory]:
        """Return the top `k` memories ranked by recency + importance + keyword overlap."""
        if k <= 0 or not self._memories:
            return []
        q_tokens = _tokens(query)

        def rank(mem: Memory) -> tuple[float, int]:
            age_days = max(0, current_tick - mem.tick) / 24.0
            recency = 1.0 / (1.0 + age_days)
            importance = mem.importance / 10.0
            overlap = 0.0
            if q_tokens:
                m_tokens = _tokens(mem.text)
                overlap = len(q_tokens & m_tokens) / len(q_tokens)
            return (recency + importance + overlap, mem.tick)

        ranked = sorted(self._memories, key=rank, reverse=True)
        return ranked[:k]

    def recent(self, n: int = 5) -> list[Memory]:
        """Return the `n` most recently added memories."""
        return self._memories[-n:] if n > 0 else []

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize all memories for viewer/storage export."""
        return [m.to_dict() for m in self._memories]
