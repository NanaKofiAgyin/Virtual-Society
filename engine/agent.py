# engine/agent.py

"""
Defines the autonomous Agent class representing entities that observe, decide,
and act dynamically within the grid world using a utility-based system.
"""

import math
from typing import Optional, List, Tuple, Dict, Any
from config import (
    TILE_SPECS, AGENT_START_ENERGY, AGENT_MAX_ENERGY, AGENT_VISION_RADIUS,
    AGENT_REPRODUCE_THRESHOLD, AGENT_METABOLISM, AGENT_MOVE_COST,
    AGENT_REST_GAIN, AGENT_EAT_AMOUNT, AGENT_FOOD_TO_ENERGY_RATIO
)

class Agent:
    """
    An autonomous agent that navigates the world grid, consumes resources,
    reproduces under high energy, and rests to survive under environmental factors.
    """
    def __init__(self, x: int, y: int, energy: float = AGENT_START_ENERGY):
        """
        Initializes an agent at coordinates (x, y) with specified starting energy.
        
        Args:
            x (int): Starting column coordinate.
            y (int): Starting row coordinate.
            energy (float): Starting energy.
        """
        self.x: int = x
        self.y: int = y
        self.energy: float = float(energy)
        self.vision_radius: int = AGENT_VISION_RADIUS

    def decide_and_act(self, world) -> Optional['Agent']:
        """
        Observes the local tiles, calculates the utility scores for actions
        (EAT, REST, REPRODUCE, MOVE), chooses the highest scoring action, and executes it.
        
        Args:
            world (World): The current world grid simulation.
            
        Returns:
            Optional[Agent]: A newborn agent if reproduction was chosen and executed, else None.
        """
        if self.energy <= 0.0:
            return None
            
        current_tile = world.get_tile(self.x, self.y)
        if not current_tile:
            # Out of bounds safety fallback
            self.energy = 0.0
            return None

        # 1. Observe and score actions
        actions_list: List[Tuple[str, Any, float]] = [] # stores (action_name, payload, score)

        # - Action A: EAT
        eat_score = 0.0
        if "food" in current_tile.resources:
            food_avail = current_tile.resources.get("food", 0.0)
            spec = TILE_SPECS.get(current_tile.type, {})
            max_food = spec.get("resources", {}).get("food", {}).get("max", 0.0)
            
            if max_food > 0.0 and food_avail > 0.0:
                food_ratio = food_avail / max_food
                hunger = AGENT_MAX_ENERGY - self.energy
                eat_score = hunger * food_ratio
                
        actions_list.append(("eat", None, eat_score))

        # - Action B: REST
        # Rest is valuable if energy is moderate-to-low and there's no immediate food
        rest_score = (60.0 - self.energy) * 0.8
        if rest_score < 0.0:
            rest_score = 0.0
        actions_list.append(("rest", None, rest_score))

        # - Action C: REPRODUCE
        reproduce_score = 0.0
        if self.energy >= AGENT_REPRODUCE_THRESHOLD:
            reproduce_score = (self.energy - AGENT_REPRODUCE_THRESHOLD) * 2.5
        actions_list.append(("reproduce", None, reproduce_score))

        # - Action D: MOVE TO TILE (scan 5x5 vision neighborhood)
        for dy in range(-self.vision_radius, self.vision_radius + 1):
            for dx in range(-self.vision_radius, self.vision_radius + 1):
                if dx == 0 and dy == 0:
                    continue # current tile evaluated under EAT/REST
                    
                nx, ny = self.x + dx, self.y + dy
                neighbor = world.get_tile(nx, ny)
                
                # Verify move coordinates are walkable
                if neighbor and neighbor.walkable:
                    dist = abs(dx) + abs(dy) # Manhattan distance
                    
                    # Extract food attraction
                    n_spec = TILE_SPECS.get(neighbor.type, {})
                    n_max_food = n_spec.get("resources", {}).get("food", {}).get("max", 0.0)
                    n_food = neighbor.resources.get("food", 0.0)
                    
                    food_score = 0.0
                    if n_max_food > 0.0:
                        food_score = (n_food / n_max_food) * 25.0
                        
                    # Calculate move utility
                    move_score = food_score - (dist * 1.5)
                    actions_list.append(("move", (nx, ny), move_score))

        # 2. Select the action with the maximum utility
        # Filter for highest utility action
        best_action, best_payload, best_score = max(actions_list, key=lambda item: item[2])

        # 3. Execute selected action
        if best_action == "eat":
            food_avail = current_tile.resources.get("food", 0.0)
            amount_to_eat = min(AGENT_EAT_AMOUNT, food_avail)
            current_tile.resources["food"] = food_avail - amount_to_eat
            
            # Gain energy and deduct metabolic rate
            self.energy = min(AGENT_MAX_ENERGY, self.energy + amount_to_eat * AGENT_FOOD_TO_ENERGY_RATIO)
            self.energy -= AGENT_METABOLISM
            
        elif best_action == "rest":
            # Conserve energy, gain rest increment (metabolism is offset by resting state)
            self.energy = min(AGENT_MAX_ENERGY, self.energy + AGENT_REST_GAIN)
            
        elif best_action == "reproduce":
            # Splits parent energy in half and spawns a newborn
            child_energy = self.energy / 2.0
            self.energy = child_energy - AGENT_METABOLISM
            
            # Create a newborn agent at same tile
            newborn = Agent(self.x, self.y, energy=child_energy)
            return newborn
            
        elif best_action == "move":
            nx, ny = best_payload
            self.x = nx
            self.y = ny
            # Consume movement energy and baseline metabolism
            self.energy -= (AGENT_MOVE_COST + AGENT_METABOLISM)

        return None

    def __repr__(self) -> str:
        return f"<Agent pos=({self.x},{self.y}) energy={self.energy:.1f}>"
