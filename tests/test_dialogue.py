"""Tests for multi-turn dialogue, beliefs/gossip, Ollama validation, consequences, and glossaries."""

from __future__ import annotations

import pathlib
import random
from typing import Any

from agents.base import Needs
from agents.culture import CulturalProfile
from agents.human import HumanAgent, Persona
from agents.lifecycle import FamilyTree
from llm.client import LLMClient
from simulation.dialogue import Belief, ConversationPurpose, DialogueManager
from world.map import WorldMap

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _make_human(hid: str, name: str, job: str, group: str = "group_1", traits: tuple[str, ...] = ("curious",)) -> HumanAgent:
    return HumanAgent(
        id=hid, name=name, position=(10, 10), home=(10, 10),
        persona=Persona(name, 24, job, traits, "Help the village thrive"),
        needs=Needs(7.0, 8.0, 5.0), inventory={"food": 4.0, "wood": 4.0},
        family=FamilyTree(surname=name.split()[-1], lineage_id=hid),
        culture=CulturalProfile(group_id=group), skills={job: 3.0},
    )


def test_multi_turn_conversations_all_purposes_and_no_daily_repetition() -> None:
    """Every conversation has 3-10 turns, supports all 12 purposes, and never repeats a line in a day."""
    world = WorldMap(width=20, height=20, seed=5)
    mgr = DialogueManager(random.Random(5))
    a = _make_human("h1", "Ada Ash", "farmer", traits=("curious",))
    b = _make_human("h2", "Bram Stone", "hunter", traits=("bold",))

    assert len(ConversationPurpose) == 12
    seen_lines: set[str] = set()
    for purpose in ConversationPurpose:
        rec = mgr.run_conversation(a, b, world, purpose=purpose, all_humans=[a, b])
        assert 3 <= len(rec.turns) <= 10
        assert rec.purpose == purpose.value
        for t in rec.turns:
            assert t.line not in seen_lines, f"Repeated line within same day: {t.line}"
            seen_lines.add(t.line)


def test_gossip_spreads_and_distorts_beliefs_with_real_consequences() -> None:
    """Gossip copies and distorts beliefs; trade, teaching, arguing, and courting have real effects."""
    world = WorldMap(width=20, height=20, seed=9)
    mgr = DialogueManager(random.Random(9))
    a = _make_human("h1", "Ada Ash", "farmer")
    b = _make_human("h2", "Bram Stone", "woodcutter")
    a.culture.known_techs.add("fire")

    # Seed an accurate belief on A and gossip repeatedly so B picks up a distorted rumor
    ma = mgr.ensure_mind(a, world)
    ma.beliefs = [Belief("trail", "the north ridge is safe and abundant", 0.9, "experience", 0, True)]
    for _ in range(6):
        mgr.run_conversation(a, b, world, purpose=ConversationPurpose.GOSSIP, all_humans=[a, b])
    mb = mgr.ensure_mind(b, world)
    assert any(bl.topic == "trail" for bl in mb.beliefs)
    assert any(bl.distortions > 0 or not bl.is_accurate for bl in mb.beliefs)

    # Teaching transfers tech
    mgr.run_conversation(a, b, world, purpose=ConversationPurpose.TEACHING_SKILL, all_humans=[a, b])
    assert "fire" in b.culture.known_techs

    # Trade swaps food & wood
    a_food_before, b_wood_before = a.inventory["food"], b.inventory["wood"]
    mgr.run_conversation(a, b, world, purpose=ConversationPurpose.TRADE_NEGOTIATION, all_humans=[a, b])
    assert a.inventory["food"] < a_food_before and b.inventory["wood"] < b_wood_before

    # Arguing lowers opinion
    before_op = a.relationships.get(b.id, 0.0)
    mgr.run_conversation(a, b, world, purpose=ConversationPurpose.ARGUING, all_humans=[a, b])
    assert a.relationships[b.id] < before_op

    # Courting with high affinity creates marriage/partnership
    a.relationships[b.id] = 4.5
    b.relationships[a.id] = 4.5
    mgr.run_conversation(a, b, world, purpose=ConversationPurpose.COURTING, all_humans=[a, b])
    assert a.family.partner == b.id and b.family.partner == a.id


class _FakeLiveLLM(LLMClient):
    """Stub live Ollama client to test important-only gating and strict action validation."""

    def __init__(self, reply: dict[str, Any]) -> None:
        super().__init__(mode="mock")
        self.calls = 0
        self._reply = reply

    def is_live(self) -> bool:
        return True

    def ask(self, system: str, user: str, json: bool = False, model_tier: str = "cheap", required: tuple[str, ...] = ()) -> Any:
        self.calls += 1
        return dict(self._reply)


def test_ollama_used_only_for_important_conversations_and_validates_actions() -> None:
    """Ollama is skipped for routine gossip, used for trade negotiations, and rejects invalid actions."""
    world = WorldMap(width=20, height=20, seed=12)
    mgr = DialogueManager(random.Random(12))
    a = _make_human("h1", "Ada Ash", "farmer")
    b = _make_human("h2", "Bram Stone", "hunter")
    a.relationships[b.id] = 1.0  # not a first meeting

    llm = _FakeLiveLLM({"line": "Let us trade grain for timber.", "action": "trade"})
    routine = mgr.run_conversation(a, b, world, llm_client=llm, purpose=ConversationPurpose.GOSSIP)
    assert llm.calls == 0 and not routine.used_llm

    important = mgr.run_conversation(a, b, world, llm_client=llm, purpose=ConversationPurpose.TRADE_NEGOTIATION)
    assert llm.calls >= 1 and important.used_llm and important.outcome == "trade"

    # Invalid action from LLM is rejected and falls back cleanly to rule-based grammar
    bad_llm = _FakeLiveLLM({"line": "Summon meteors!", "action": "destroy_world"})
    safe = mgr.run_conversation(a, b, world, llm_client=bad_llm, purpose=ConversationPurpose.SETTLING_DISPUTE)
    assert not safe.used_llm and safe.outcome != "destroy_world"


def test_language_drift_glossaries_and_viewer_dialogue_panel() -> None:
    """Isolated cultural groups diverge vocabulary and viewer includes filterable dialogue UI."""
    mgr = DialogueManager(random.Random(3))
    g1 = [_make_human("h1", "Ada Ash", "farmer", "group_1"), _make_human("h2", "Bram Ash", "hunter", "group_1")]
    g2 = [_make_human("h3", "Clara Oak", "farmer", "group_2"), _make_human("h4", "Dorian Oak", "hunter", "group_2")]
    humans = g1 + g2
    for _ in range(30):
        mgr.drift_isolated_languages(humans)
    gloss = mgr.build_glossaries(humans)
    assert "group_1" in gloss and "group_2" in gloss
    assert gloss["group_1"] != gloss["group_2"]

    html = (ROOT / "server" / "static" / "index.html").read_text(encoding="utf-8")
    assert "dlg-filter-person" in html and "dlg-filter-topic" in html and "dlg-filter-place" in html
    assert "culture-glossaries" in html
