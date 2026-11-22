"""Unit tests for `llm/narrator.py` (rare high-value moments, batching, action validation)."""

from __future__ import annotations

import json
import random
from typing import Any

from llm import LLMClient, Narrator, VALID_LEADER_ACTIONS


class _FakeResp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._data = json.dumps({"message": {"content": json.dumps(payload)}}).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def test_mock_mode_uses_templates_with_zero_network_calls() -> None:
    """When LLM_MODE=mock, all 5 rare moments fall back cleanly without touching the network."""
    def forbid_net(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Network must never be called in mock mode")

    narrator = Narrator(LLMClient(mode="mock", urlopen_fn=forbid_net))
    rng = random.Random(7)

    assert narrator.name_new_species("deer", "tundra", {"cold_tolerance": 0.9}, {"deer"}, "arctic_deer") == "arctic_deer"
    st = narrator.name_settlement("s1", "grassland", 12, {"sharing": 0.7})
    assert "Grassland" in st["name"] and "12" in st["description"]

    era = narrator.summarize_era("Neolithic Era", [{"title": "First Farm"}, {"title": "First Boat"}])
    assert "First Farm" in era

    dec = narrator.leader_decision("Ada", "Oak Haven", {"surplus_food": 0.5, "tension": 0.1})
    assert dec["action"] == "ration_food"
    assert dec["action"] in VALID_LEADER_ACTIONS

    word = narrator.invent_word("fire", "Oak Clan", "tara", rng)
    assert word.isalpha() and len(word) == 4


def test_live_ollama_high_value_moments_and_strict_action_validation() -> None:
    """Live Ollama names species/settlements/eras/words, and illegal actions are rejected."""
    replies = iter([
        _FakeResp({"name": "Frost Stag"}),
        _FakeResp({"name": "Sunridge", "description": "A warm highland farming town."}),
        _FakeResp({"summary": "The Bronze Age united the river villages in trade."}),
        # Model hallucinates an illegal physics-breaking action -> must be rejected!
        _FakeResp({"action": "grant_immortality", "reason": "Make everyone invincible"}),
        # Valid action -> accepted!
        _FakeResp({"action": "explore", "reason": "Seek timber beyond the ridge."}),
        _FakeResp({"word": "sola"}),
    ])
    live = LLMClient(mode="ollama", enable_cache=False, urlopen_fn=lambda *a, **k: next(replies), sleep_fn=lambda _: None)
    narrator = Narrator(live, max_per_batch=2)
    rng = random.Random(1)

    sp = narrator.name_new_species("deer", "tundra", {"cold_tolerance": 0.9}, {"deer"}, "arctic_deer")
    assert sp == "frost_stag"

    st = narrator.name_settlement("s1", "savanna", 18, {"sharing": 0.6})
    assert st["name"] == "Sunridge" and "farming" in st["description"]

    summary = narrator.summarize_era("Bronze Age", [{"title": "First Writing"}])
    assert "Bronze Age" in summary

    # Illegal action rejected -> falls back to valid rule-based action
    bad_dec = narrator.leader_decision("Ada", "Sunridge", {"surplus_food": 0.2, "tension": 0.0})
    assert bad_dec["action"] == "ration_food"
    assert bad_dec["action"] in VALID_LEADER_ACTIONS

    good_dec = narrator.leader_decision("Ada", "Sunridge", {"surplus_food": 10.0, "tension": 0.1})
    assert good_dec["action"] == "explore"

    assert narrator.invent_word("sun", "Sunridge", "tara", rng) == "sola"


def test_batch_queue_respects_max_per_batch() -> None:
    """Narrator batch queue drains at most `max_per_batch` tasks per flush."""
    narrator = Narrator(LLMClient(mode="mock"), max_per_batch=2)
    for i in range(5):
        narrator.enqueue(lambda n=i: n)

    assert narrator.flush_batch() == [0, 1]
    assert narrator.flush_batch() == [2, 3]
    assert narrator.flush_batch() == [4]
    assert narrator.flush_batch() == []
