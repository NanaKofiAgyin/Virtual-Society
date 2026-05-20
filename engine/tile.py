# engine/tile.py

"""
Defines the Tile class and its associated behaviors, including resource
regeneration, decay, and walkable parameters.
Upgraded in Phase 2 with environmental pressure multipliers (overcrowding/isolation)
and dynamic terrain state shift transitions.
"""

from typing import Dict, Any
from config import (
    TILE_SPECS, THRESHOLD_OVERCROWDED, THRESHOLD_ISOLATED, PENALTY_ISOLATED_DECAY
)

class Tile:
    """
    Represents an individual coordinate (cell) in the world grid.
    Contains tile properties (type, walkability, representation) and manages
    dynamic resources (wood, food) that change each tick based on neighbor interactions.
    """
    def __init__(self, x: int, y: int, tile_type: str):
        """
        Initializes a tile at coordinates (x, y) with a specified type.
        
        Args:
            x (int): X-coordinate in the grid.
            y (int): Y-coordinate in the grid.
            tile_type (str): Type of the tile ('grass', 'forest', 'water', 'mountain').
        """
        self.x: int = x
        self.y: int = y
        self.type: str = tile_type.lower()
        self.resources: Dict[str, float] = {}
        self._resource_specs: Dict[str, Dict[str, float]] = {}
        self.walkable: bool = True
        self.display_char: str = "?"
        self.color_code: str = ""
        
        # Load structural parameters and config resources
        self._load_specs()

    def _load_specs(self) -> None:
        """Loads structural parameters and initializes resources based on the current tile type."""
        spec = TILE_SPECS.get(self.type)
        if not spec:
            raise ValueError(f"Unknown tile type: '{self.type}' provided during initialization.")
            
        self.walkable = spec.get("walkable", True)
        self.display_char = spec.get("display_char", "?")
        self.color_code = spec.get("color_code", "")
        self._resource_specs = spec.get("resources", {})
        
        # Initialize resources to base configured amounts
        self.resources.clear()
        for res_name, res_spec in self._resource_specs.items():
            self.resources[res_name] = float(res_spec.get("base", 0.0))

    def transition_to(self, new_type: str) -> None:
        """
        Dynamically shifts the terrain state of this cell to another type.
        Re-initializes all specs and resources to their matching parameters.
        
        Args:
            new_type (str): The new terrain type name.
        """
        self.type = new_type.lower()
        self._load_specs()

    def tick(self, same_neighbor_count: int = 3) -> Dict[str, float]:
        """
        Executes one cycle of simulation on this tile under environmental pressures.
        Regenerates or decays resources.
        
        Args:
            same_neighbor_count (int): How many Moore adjacent cells are of the same type.
            
        Returns:
            Dict[str, float]: The change in each resource type during this tick.
        """
        changes = {}
        
        # Determine environmental pressure effects
        growth_multiplier = 1.0
        decay_penalty = 0.0
        
        if same_neighbor_count >= THRESHOLD_OVERCROWDED:
            # Overcrowded: Growth slows down by 50% due to resources competition
            growth_multiplier = 0.5
        elif same_neighbor_count <= THRESHOLD_ISOLATED:
            # Isolated: Growth is uninhibited but lack of community causes decay penalty
            decay_penalty = PENALTY_ISOLATED_DECAY

        for res_name, res_spec in self._resource_specs.items():
            current = self.resources.get(res_name, 0.0)
            
            # Retrieve rates, scaling regeneration and adding decay penalty if applicable
            regen = float(res_spec.get("regen_rate", 0.0)) * growth_multiplier
            decay = float(res_spec.get("decay_rate", 0.0)) + decay_penalty
            max_limit = float(res_spec.get("max", 0.0))
            
            # Calculate resource level transition
            net_change = regen - decay
            updated = current + net_change
            
            # Clamp limits strictly to [0.0, max_limit]
            if updated > max_limit:
                net_change = max_limit - current
                updated = max_limit
            elif updated < 0.0:
                net_change = -current
                updated = 0.0
                
            self.resources[res_name] = updated
            changes[res_name] = net_change
            
        return changes

    def get_status_str(self) -> str:
        """
        Returns a concise diagnostic string of the tile's coordinates,
        type, and current resource levels.
        
        Returns:
            str: Diagnostic status.
        """
        res_parts = [f"{k}: {v:.1f}" for k, v in self.resources.items() if v > 0]
        res_str = f" [{', '.join(res_parts)}]" if res_parts else ""
        walk_str = "Walkable" if self.walkable else "Impassable"
        return f"Tile({self.x},{self.y}) Type: {self.type.capitalize()} ({walk_str}){res_str}"

    def __repr__(self) -> str:
        return f"<Tile at ({self.x}, {self.y}) type={self.type}>"
