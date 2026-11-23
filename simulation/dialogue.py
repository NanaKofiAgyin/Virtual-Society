"""Multi-turn conversation engine: beliefs, opinions, gossip, Ollama mode, and consequences."""

from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, Any

from agents.culture import BASE_WORDS, mutate_word
from agents.lifecycle import can_pair_humans
from simulation.dialogue_grammar import (
    IMPORTANT_PURPOSES, VALID_DIALOGUE_ACTIONS, ConversationPurpose,
    compose_turn_line, distort_claim, speech_style_of,
)
from simulation.dialogue_models import Belief, ConversationRecord, ConversationTurn, PersonMind

if TYPE_CHECKING:
    from agents.human import HumanAgent
    from llm.client import LLMClient
    from world.map import WorldMap

DEFAULT_FEARS = ("winter famine", "wild predators", "sudden drought", "sickness", "losing kin")


class DialogueManager:
    """Drives multi-turn conversations, belief/gossip spread, Ollama calls, and language drift."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.minds: dict[str, PersonMind] = {}
        self.logs: deque[ConversationRecord] = deque(maxlen=120)
        self._spoken_day: int = -1
        self._spoken_today: set[str] = set()
        self._conv_seq: int = 0

    def ensure_mind(self, human: HumanAgent, world: WorldMap) -> PersonMind:
        if human.id in self.minds:
            m = self.minds[human.id]
            m.speech_style = speech_style_of(human)
            return m
        tile = world.get_tile(human.x, human.y)
        place = tile.terrain.value if tile else "grassland"
        fear = self.rng.choice(DEFAULT_FEARS)
        goal = human.persona.goal if human.persona else "Thrive with the settlement"
        traits = list(human.persona.traits) if human.persona else ["curious"]
        mind = PersonMind(
            beliefs=[
                Belief("local_food", f"food in the {place} is abundant", 0.85, "experience", 0, True),
                Belief("north_trail", "the north ridge is safe for foraging", 0.75, "experience", 0, True),
            ],
            opinions={k: float(v) for k, v in human.relationships.items()},
            goals=[goal], fears=[fear], traits=traits, speech_style=speech_style_of(human),
        )
        self.minds[human.id] = mind
        return mind

    def choose_purpose(self, a: HumanAgent, b: HumanAgent, world: WorldMap) -> ConversationPurpose:
        """Select a realistic conversation purpose from agents' state and relationship."""
        aff = a.relationships.get(b.id, 0.0)
        if b.id not in a.relationships:
            return ConversationPurpose.GREETING
        if any("died" in m.text.lower() for m in a.memory.recent(4)):
            return ConversationPurpose.MOURNING
        if aff <= -2.0:
            return self.rng.choice((ConversationPurpose.ARGUING, ConversationPurpose.SETTLING_DISPUTE))
        if can_pair_humans(a, b) and aff >= 2.5 and self.rng.random() < 0.45:
            return ConversationPurpose.COURTING
        if a.needs.hunger < 4.5 or b.needs.hunger < 4.5:
            return self.rng.choice((ConversationPurpose.ASKING_FOR_HELP, ConversationPurpose.TRADE_NEGOTIATION))
        if a.culture.known_techs - b.culture.known_techs:
            return ConversationPurpose.TEACHING_SKILL
        if a.needs.social < 4.0:
            return ConversationPurpose.COMFORTING
        return self.rng.choice((
            ConversationPurpose.GOSSIP, ConversationPurpose.TRADE_NEGOTIATION,
            ConversationPurpose.PLANNING_HUNT_MIGRATION, ConversationPurpose.TELLING_STORY,
            ConversationPurpose.GREETING,
        ))

    def _ask_ollama_turn(
        self, speaker: HumanAgent, listener: HumanAgent, purpose: ConversationPurpose,
        place: str, env_season: str, llm_client: LLMClient,
    ) -> tuple[str, str] | None:
        """Call local Ollama only for important exchanges with a short facts list and strict JSON."""
        facts = (
            f"Speaker: {speaker.name} ({speaker.persona.job if speaker.persona else 'villager'}, style={speech_style_of(speaker)}). "
            f"Listener: {listener.name}. Purpose: {purpose.value}. Place: {place}. Season: {env_season}. "
            f"Affinity: {speaker.relationships.get(listener.id, 0.0):.1f}. "
            f"Valid actions: {', '.join(VALID_DIALOGUE_ACTIONS)}."
        )
        system = 'Reply ONLY with JSON: {"line": "<1 short natural sentence>", "action": "<one valid action>"}'
        res = llm_client.ask(system, facts, json=True, model_tier="cheap", required=("line", "action"))
        if not isinstance(res, dict) or res.get("_fallback"):
            return None
        action = str(res.get("action", "")).strip().lower()
        line = str(res.get("line", "")).strip()
        if action not in VALID_DIALOGUE_ACTIONS or not line:
            return None
        return line, action

    def _apply_consequences(
        self, a: HumanAgent, b: HumanAgent, purpose: ConversationPurpose,
        final_action: str, world: WorldMap,
    ) -> list[str]:
        """Apply concrete simulation consequences: opinions, rumors, skills, trade, marriage, conflict."""
        ma, mb = self.ensure_mind(a, world), self.ensure_mind(b, world)
        consequences: list[str] = []
        delta = 0.8
        if purpose is ConversationPurpose.ARGUING or final_action == "rival":
            delta = -1.6
            consequences.append(f"Rivalry grew between {a.name} and {b.name}")
        elif purpose is ConversationPurpose.SETTLING_DISPUTE or final_action == "resolve":
            delta = 1.4
            consequences.append(f"{a.name} and {b.name} settled their dispute")
        elif purpose is ConversationPurpose.GOSSIP and ma.beliefs:
            src = self.rng.choice(ma.beliefs)
            new_claim, flipped = distort_claim(src.claim, self.rng)
            rumor = Belief(
                topic=src.topic, claim=new_claim, confidence=max(0.25, src.confidence * 0.85),
                source_id=a.id, distortions=src.distortions + (1 if flipped else 0),
                is_accurate=(src.is_accurate and not flipped),
            )
            mb.add_belief(rumor)
            consequences.append(f"Rumor spread to {b.name}: {new_claim}")
        elif purpose is ConversationPurpose.TEACHING_SKILL or final_action == "teach":
            diff = a.culture.known_techs - b.culture.known_techs
            if diff:
                t = sorted(diff)[0]
                b.culture.known_techs.add(t)
                consequences.append(f"{a.name} taught {t} to {b.name}")
            elif a.skills:
                sk = max(a.skills, key=lambda k: a.skills[k])
                b.skills[sk] = round(b.skills.get(sk, 0.0) + 0.5, 2)
                consequences.append(f"{a.name} coached {b.name} in {sk}")
        elif purpose is ConversationPurpose.TRADE_NEGOTIATION or final_action == "trade":
            if a.inventory.get("food", 0.0) >= 1.0 and b.inventory.get("wood", 0.0) >= 1.0:
                a.remove_item("food", 1.0); b.add_item("food", 1.0)
                b.remove_item("wood", 1.0); a.add_item("wood", 1.0)
                consequences.append(f"{a.name} traded food for wood with {b.name}")
            elif b.inventory.get("food", 0.0) >= 1.0:
                b.remove_item("food", 1.0); a.add_item("food", 1.0)
                consequences.append(f"{b.name} shared food with {a.name}")
        elif purpose is ConversationPurpose.COURTING or final_action == "court":
            delta = 1.8
            if can_pair_humans(a, b) and a.relationships.get(b.id, 0.0) + delta >= 4.0:
                a.family.partner, b.family.partner = b.id, a.id
                consequences.append(f"{a.name} and {b.name} formed a marriage/partnership")
        elif purpose is ConversationPurpose.PLANNING_HUNT_MIGRATION or final_action == "migrate":
            consequences.append(f"{a.name} & {b.name} planned a seasonal expedition")
        elif purpose is ConversationPurpose.COMFORTING or purpose is ConversationPurpose.MOURNING:
            delta = 1.2
            b.needs.adjust(social=2.5)
            consequences.append(f"{a.name} comforted {b.name}")

        a.adjust_affinity(b.id, delta); b.adjust_affinity(a.id, delta)
        ma.opinions[b.id] = a.relationships.get(b.id, 0.0)
        mb.opinions[a.id] = b.relationships.get(a.id, 0.0)
        a.needs.adjust(social=2.5); b.needs.adjust(social=2.0)
        if not consequences:
            consequences.append(f"Friendship deepened ({a.name} & {b.name})")
        return consequences

    def run_conversation(
        self, a: HumanAgent, b: HumanAgent, world: WorldMap,
        llm_client: LLMClient | None = None, purpose: ConversationPurpose | None = None,
        all_humans: list[HumanAgent] | None = None,
    ) -> ConversationRecord:
        """Run a 3–10 turn conversation with real state vocabulary, optional Ollama, and consequences."""
        env = world.environment
        if env.day != self._spoken_day:
            self._spoken_day, self._spoken_today = env.day, set()
        ma, mb = self.ensure_mind(a, world), self.ensure_mind(b, world)
        first_meeting = b.id not in a.relationships
        chosen_purpose = purpose or self.choose_purpose(a, b, world)
        tile = world.get_tile(a.x, a.y)
        place = tile.terrain.value if tile else "grassland"
        names_by_id = {h.id: h.name for h in (all_humans or [a, b])}
        n_turns = self.rng.randint(3, 10)
        is_important = first_meeting or (chosen_purpose in IMPORTANT_PURPOSES)
        use_llm = bool(llm_client is not None and llm_client.is_live() and is_important)

        turns: list[ConversationTurn] = []
        used_llm = False
        final_action = "agree"
        for i in range(n_turns):
            spk, lst = (a, b) if i % 2 == 0 else (b, a)
            mind = ma if spk is a else mb
            ctx = {
                "belief_claim": mind.beliefs[-1].claim if mind.beliefs else f"the {place} is calm",
                "fear": mind.fears[0] if mind.fears else "winter famine",
                "tech": next(iter(spk.culture.known_techs), "stone_tools"),
                "names_by_id": names_by_id,
            }
            line, act = "", "agree"
            if use_llm and i in (0, n_turns - 1):
                llm_res = self._ask_ollama_turn(spk, lst, chosen_purpose, place, env.season.value, llm_client)  # type: ignore[arg-type]
                if llm_res is not None:
                    line, act, used_llm = llm_res[0], llm_res[1], True
            if not line:
                line = compose_turn_line(spk, lst, chosen_purpose, i, env, place, ctx, self._spoken_today, self.rng)
                act = "rival" if chosen_purpose is ConversationPurpose.ARGUING else ("trade" if chosen_purpose is ConversationPurpose.TRADE_NEGOTIATION else "agree")
            final_action = act
            spk.last_speech = line
            turns.append(ConversationTurn(spk.id, spk.name, line, act))

        consequences = self._apply_consequences(a, b, chosen_purpose, final_action, world)
        a.memory.add(f"Conversation ({chosen_purpose.value}) with {b.name}: {turns[0].line[:60]}", env.tick)
        b.memory.add(f"Conversation ({chosen_purpose.value}) with {a.name}: {turns[0].line[:60]}", env.tick)
        self._conv_seq += 1
        rec = ConversationRecord(
            id=f"c_{self._conv_seq}", tick=env.tick, day=env.day, place=place,
            purpose=chosen_purpose.value, participants=(a.id, b.id),
            participant_names=(a.name, b.name), turns=turns,
            outcome=final_action, consequences=consequences, used_llm=used_llm,
        )
        self.logs.append(rec)
        return rec

    def drift_isolated_languages(self, humans: list[HumanAgent]) -> None:
        """Slowly drift vocabulary of isolated cultural groups so dialects diverge over time."""
        groups: dict[str, list[HumanAgent]] = {}
        for h in humans:
            if h.alive:
                groups.setdefault(h.culture.group_id, []).append(h)
        for members in groups.values():
            if len(members) >= 2 and self.rng.random() < 0.25:
                concept = self.rng.choice(tuple(BASE_WORDS.keys()))
                new_word = mutate_word(members[0].culture.language.get(concept, BASE_WORDS[concept]), self.rng)
                for m in members:
                    m.culture.language[concept] = new_word

    def build_glossaries(self, humans: list[HumanAgent]) -> dict[str, dict[str, str]]:
        """Build a per-culture glossary `{group_id: {meaning: dialect_word}}` for the viewer."""
        gloss: dict[str, dict[str, str]] = {}
        for h in humans:
            if h.alive and h.culture.group_id not in gloss:
                gloss[h.culture.group_id] = dict(h.culture.language)
        return gloss
