"""Base Agent abstraction shared by humans and rule-based animals."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from world.map import WorldMap

CARDINALS = ((0, -1), (1, 0), (0, 1), (-1, 0))


class ActionType(str, Enum):
    """Actions an agent can perform in the world."""

    MOVE = "move"
    EAT = "eat"
    SLEEP = "sleep"
    TALK = "talk"
    WORK = "work"
    GATHER = "gather"


ALL_ACTIONS: tuple[ActionType, ...] = tuple(ActionType)


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    """Clamp a numeric value to the inclusive range [low, high]."""
    return max(low, min(high, value))


@dataclass
class Needs:
    """Agent needs on a 0–10 scale where 10 is fully satisfied and 0 is critical."""

    hunger: float = 8.0
    energy: float = 8.0
    social: float = 8.0

    def __post_init__(self) -> None:
        self.clamp()

    def clamp(self) -> None:
        """Keep all need values strictly within [0.0, 10.0]."""
        self.hunger = _clamp(self.hunger)
        self.energy = _clamp(self.energy)
        self.social = _clamp(self.social)

    def adjust(self, hunger: float = 0.0, energy: float = 0.0, social: float = 0.0) -> None:
        """Apply deltas to each need and clamp results to [0.0, 10.0]."""
        self.hunger += hunger
        self.energy += energy
        self.social += social
        self.clamp()

    def to_dict(self) -> dict[str, float]:
        """Serialize needs to a JSON-friendly dictionary."""
        return {
            "hunger": round(self.hunger, 2),
            "energy": round(self.energy, 2),
            "social": round(self.social, 2),
        }


@dataclass
class Action:
    """A concrete action chosen by an agent for a single tick."""

    type: ActionType
    target: Any = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Agent(ABC):
    """Base class for all autonomous entities (humans and animals)."""

    id: str
    name: str
    position: tuple[int, int]
    needs: Needs = field(default_factory=Needs)
    health: float = 10.0
    inventory: dict[str, float] = field(default_factory=dict)
    speed: int = 1
    flies: bool = False
    available_actions: list[ActionType] = field(default_factory=lambda: list(ALL_ACTIONS))
    alive: bool = True
    starving: bool = False
    exhausted: bool = False

    hunger_decay: float = 0.4
    energy_decay: float = 0.3
    social_decay: float = 0.2

    @property
    def x(self) -> int:
        """Return the agent's x coordinate."""
        return self.position[0]

    @property
    def y(self) -> int:
        """Return the agent's y coordinate."""
        return self.position[1]

    def _valid_neighbors(self, world: WorldMap) -> list[tuple[int, int]]:
        """Return adjacent tiles this agent is allowed to enter."""
        cx, cy = self.position
        result: list[tuple[int, int]] = []
        for dx, dy in CARDINALS:
            tile = world.get_tile(cx + dx, cy + dy)
            if tile is not None and (self.flies or tile.walkable):
                result.append((tile.x, tile.y))
        return result

    def goto(self, world: WorldMap, target: tuple[int, int]) -> bool:
        """Move up to `self.speed` tiles toward `target` using `world.path()`."""
        if not self.alive or self.position == target:
            return False
        if self.flies:
            moved = False
            for _ in range(max(1, self.speed)):
                cx, cy = self.position
                tx, ty = target
                if (cx, cy) == (tx, ty):
                    break
                dx = (1 if tx > cx else -1) if tx != cx else 0
                dy = (1 if ty > cy else -1) if ty != cy else 0
                nx, ny = (cx + dx, cy) if abs(tx - cx) >= abs(ty - cy) else (cx, cy + dy)
                if not world.in_bounds(nx, ny):
                    break
                self.position = (nx, ny)
                moved = True
            return moved

        route = world.path(self.position, target)
        if len(route) <= 1:
            return False
        self.position = route[min(max(1, self.speed), len(route) - 1)]
        return True

    def wander(self, world: WorldMap, rng: random.Random) -> bool:
        """Move up to `self.speed` random valid steps."""
        if not self.alive:
            return False
        moved = False
        for _ in range(max(1, self.speed)):
            neighbors = self._valid_neighbors(world)
            if not neighbors:
                break
            self.position = rng.choice(neighbors)
            moved = True
        return moved

    def flee_from(
        self,
        world: WorldMap,
        threat_pos: tuple[int, int],
        rng: random.Random | None = None,
    ) -> bool:
        """Move up to `self.speed` steps away from `threat_pos`."""
        if not self.alive:
            return False
        tx, ty = threat_pos
        moved = False
        for _ in range(max(1, self.speed)):
            neighbors = self._valid_neighbors(world)
            if not neighbors:
                break
            best_dist = max((nx - tx) ** 2 + (ny - ty) ** 2 for nx, ny in neighbors)
            best = [p for p in neighbors if (p[0] - tx) ** 2 + (p[1] - ty) ** 2 == best_dist]
            self.position = rng.choice(best) if rng is not None else best[0]
            moved = True
        return moved

    def update_needs(self) -> list[str]:
        """Decay needs for one tick and apply starvation/exhaustion consequences."""
        if not self.alive:
            return []
        events: list[str] = []
        self.needs.adjust(-self.hunger_decay, -self.energy_decay, -self.social_decay)
        if self.needs.hunger <= 0.0:
            self.starving = True
            self.health = _clamp(self.health - 1.5)
            events.append("starving")
        else:
            self.starving = False

        if self.needs.energy <= 0.0:
            self.exhausted = True
            self.health = _clamp(self.health - 0.5)
            events.append("exhausted")
        elif self.needs.energy >= 2.0:
            self.exhausted = False

        if self.health <= 0.0:
            self.alive = False
            events.append("died")
        return events

    def add_item(self, item: str, amount: float) -> None:
        """Add a positive quantity of an item to inventory."""
        if amount > 0.0:
            self.inventory[item] = self.inventory.get(item, 0.0) + amount

    def remove_item(self, item: str, amount: float) -> float:
        """Remove up to `amount` of an item from inventory and return what was taken."""
        if amount <= 0.0:
            return 0.0
        available = self.inventory.get(item, 0.0)
        taken = min(available, amount)
        remaining = available - taken
        if remaining <= 0.0:
            self.inventory.pop(item, None)
        else:
            self.inventory[item] = remaining
        return taken

    def can_perform(self, action_type: ActionType) -> bool:
        """Return True if this agent is allowed to perform `action_type` right now."""
        if not self.alive or action_type not in self.available_actions:
            return False
        if self.exhausted and action_type in (ActionType.MOVE, ActionType.WORK, ActionType.GATHER):
            return False
        return True

    @abstractmethod
    def decide(self, world: WorldMap, nearby_agents: list[Agent]) -> Action:
        """Choose the next action based on the world state and nearby agents."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize agent state to a JSON-friendly dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.__class__.__name__,
            "position": list(self.position),
            "inventory": {k: round(v, 2) for k, v in self.inventory.items()},
            "needs": self.needs.to_dict(),
            "health": round(self.health, 2),
            "speed": self.speed,
            "alive": self.alive,
            "starving": self.starving,
            "exhausted": self.exhausted,
        }
