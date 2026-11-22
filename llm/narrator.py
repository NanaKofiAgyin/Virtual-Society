"""Rare high-value LLM moments (batched, rate-limited, strictly action-validated).

Everyday survival and ecology stay 100% rule-based. When `LLM_MODE=ollama`,
this module handles only rare creative/strategic moments:
1. Naming new species
2. Naming and describing a new culture or settlement
3. Writing the chronicle summary of an era
4. Notable leader decisions (strictly restricted to `valid_actions`)
5. Inventing words for a group's language

Model output can NEVER alter world physics or biology; invalid or failed
responses always fall back to deterministic templates.
"""

from __future__ import annotations

import random
import re
from collections import deque
from typing import Any, Callable, Sequence

from agents.culture import mutate_word
from llm.client import LLMClient

VALID_LEADER_ACTIONS: tuple[str, ...] = ("migrate", "make_peace", "ration_food", "explore")
_IDENT_RE = re.compile(r"[^a-z0-9_]+")
_WORD_RE = re.compile(r"[^a-z]+")


def _slug(text: str, fallback: str) -> str:
    cleaned = _IDENT_RE.sub("_", text.strip().lower()).strip("_")
    return cleaned[:32] if cleaned else fallback


def _clean_word(text: str, fallback: str) -> str:
    cleaned = _WORD_RE.sub("", text.strip().lower())
    return cleaned[:10] if 2 <= len(cleaned) <= 10 else fallback


class Narrator:
    """Batched, safe wrapper for rare high-value Ollama calls with template fallbacks."""

    def __init__(self, client: LLMClient | None = None, max_per_batch: int = 3) -> None:
        self.client = client if client is not None else LLMClient(mode="mock")
        self.max_per_batch = max(1, max_per_batch)
        self._queue: deque[Callable[[], Any]] = deque()

    def enqueue(self, task: Callable[[], Any]) -> None:
        """Queue a rare high-value task to be executed in the next rate-limited batch."""
        self._queue.append(task)

    def flush_batch(self) -> list[Any]:
        """Run up to `max_per_batch` queued tasks and return their results."""
        results: list[Any] = []
        for _ in range(min(self.max_per_batch, len(self._queue))):
            fn = self._queue.popleft()
            results.append(fn())
        return results

    def name_new_species(
        self,
        parent_name: str,
        habitat: str,
        key_genes: dict[str, float],
        existing_names: set[str],
        fallback_name: str,
    ) -> str:
        """Name a newly speciated lineage, falling back to `fallback_name` when mock/failed."""
        if not self.client.is_live():
            return fallback_name
        system = 'Name a newly evolved animal species in 1-2 lowercase words. Reply JSON: {"name": "..."}.'
        user = f"Ancestor: {parent_name}. Habitat: {habitat}. Key genes: {key_genes}."
        res = self.client.ask(system, user, json=True, model_tier="cheap", required=("name",))
        if isinstance(res, dict) and not res.get("_fallback") and res.get("name"):
            candidate = _slug(str(res["name"]), fallback_name)
            if candidate not in existing_names:
                return candidate
        return fallback_name

    def name_settlement(
        self,
        settlement_id: str,
        biome: str,
        population: int,
        norms: dict[str, float],
    ) -> dict[str, str]:
        """Name and briefly describe a new culture/settlement."""
        fallback_name = f"{biome.replace('_', ' ').title()} Haven ({settlement_id})"
        fallback_desc = f"A {biome.replace('_', ' ')} community of {population} villagers."
        if not self.client.is_live():
            return {"name": fallback_name, "description": fallback_desc}

        system = 'Name and describe a new human settlement in 1 sentence. Reply JSON: {"name": "...", "description": "..."}.'
        user = f"Biome: {biome}. Population: {population}. Norms: {norms}."
        res = self.client.ask(
            system, user, json=True, model_tier="main", required=("name", "description")
        )
        if isinstance(res, dict) and not res.get("_fallback") and res.get("name") and res.get("description"):
            return {
                "name": str(res["name"]).strip()[:48],
                "description": str(res["description"]).strip()[:180],
            }
        return {"name": fallback_name, "description": fallback_desc}

    def summarize_era(self, era_name: str, milestones: list[dict[str, Any]]) -> str:
        """Write a short chronicle summary of an era from its milestones."""
        titles = [m.get("title", "") for m in milestones[-8:] if m.get("title")]
        fallback = (
            f"The {era_name} saw {', '.join(titles[:4])}."
            if titles else f"The {era_name} passed quietly."
        )
        if not self.client.is_live():
            return fallback

        system = 'Write a 1-2 sentence historical chronicle summary. Reply JSON: {"summary": "..."}.'
        user = f"Era: {era_name}. Key milestones: {', '.join(titles) or 'none'}."
        res = self.client.ask(system, user, json=True, model_tier="main", required=("summary",))
        if isinstance(res, dict) and not res.get("_fallback") and res.get("summary"):
            return str(res["summary"]).strip()[:240]
        return fallback

    def leader_decision(
        self,
        leader_name: str,
        settlement_name: str,
        context: dict[str, Any],
        valid_actions: Sequence[str] = VALID_LEADER_ACTIONS,
    ) -> dict[str, str]:
        """Ask a notable leader to choose strictly among `valid_actions`.

        Never allows illegal or physics-breaking actions; falls back to rules.
        """
        allowed = tuple(valid_actions) if valid_actions else VALID_LEADER_ACTIONS
        # Rule-based fallback choice
        surplus = float(context.get("surplus_food", 0.0))
        tension = float(context.get("tension", 0.0))
        if surplus < 2.0 and "ration_food" in allowed:
            fb_action, fb_reason = "ration_food", "Food stores are low; rationing protects everyone."
        elif tension > 0.6 and "make_peace" in allowed:
            fb_action, fb_reason = "make_peace", "Reducing tension avoids a costly conflict."
        elif "explore" in allowed:
            fb_action, fb_reason = "explore", "Scouting nearby lands finds new resources."
        else:
            fb_action, fb_reason = allowed[0], "Following standard village policy."

        if not self.client.is_live():
            return {"action": fb_action, "reason": fb_reason}

        system = (
            f"You are leader {leader_name} of {settlement_name}. "
            f"Choose ONLY one action from {list(allowed)}. "
            'Reply JSON: {"action": "...", "reason": "..."}.'
        )
        user = f"Settlement status: {context}."
        res = self.client.ask(
            system, user, json=True, model_tier="main", required=("action", "reason")
        )
        if isinstance(res, dict) and not res.get("_fallback"):
            chosen = str(res.get("action", "")).strip().lower()
            if chosen in allowed:
                return {"action": chosen, "reason": str(res.get("reason", "")).strip()[:160] or fb_reason}
        return {"action": fb_action, "reason": fb_reason}

    def invent_word(
        self,
        concept: str,
        group_name: str,
        existing_word: str,
        rng: random.Random,
    ) -> str:
        """Invent a short group language word, falling back to phonetic drift."""
        fallback = mutate_word(existing_word, rng)
        if not self.client.is_live():
            return fallback

        system = 'Invent one short pronounceable lowercase word (3-8 letters). Reply JSON: {"word": "..."}.'
        user = f"Group: {group_name}. Concept: {concept}. Old word: {existing_word}."
        res = self.client.ask(system, user, json=True, model_tier="cheap", required=("word",))
        if isinstance(res, dict) and not res.get("_fallback") and res.get("word"):
            return _clean_word(str(res["word"]), fallback)
        return fallback
