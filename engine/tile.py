# engine/tile.py

"""
Defines the Tile class and its associated behaviors, including resource
regeneration, decay, and walkable parameters.
"""

from typing import Dict, Any
from config import TILE_SPECS

class Tile:
    """
    Represents an individual coordinate (cell) in the world grid.
    Contains tile properties (type, walkability, representation) and manages
    dynamic resources (wood, food) that change each tick.
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
        
        # Load structural parameters from configuration specs
        spec = TILE_SPECS.get(self.type)
        if not spec:
            raise ValueError(f"Unknown tile type: '{tile_type}' provided during initialization.")
            
        self.walkable: bool = spec.get("walkable", True)
        self.display_char: str = spec.get("display_char", "?")
        self.color_code: str = spec.get("color_code", "")
        
        # Load resource limits, rates, and initial amounts
        self.resources: Dict[str, float] = {}
        self._resource_specs: Dict[str, Dict[str, float]] = spec.get("resources", {})
        
        for res_name, res_spec in self._resource_specs.items():
            self.resources[res_name] = float(res_spec.get("base", 0.0))

    def tick(self) -> Dict[str, float]:
        """
        Executes one cycle of simulation on this tile.
        Regenerates or decays resources based on the tile type specification.
        
        Returns:
            Dict[str, float]: The change in each resource type during this tick.
        """
        changes = {}
        for res_name, res_spec in self._resource_specs.items():
            current = self.resources.get(res_name, 0.0)
            
            # Retrieve regeneration and decay rates (defaulting to 0.0 if not defined)
            regen = float(res_spec.get("regen_rate", 0.0))
            decay = float(res_spec.get("decay_rate", 0.0))
            max_limit = float(res_spec.get("max", 0.0))
            
            # Calculate the net resource change for this tick
            net_change = regen - decay
            updated = current + net_change
            
            # Apply strict boundaries: [0.0, max_limit]
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
