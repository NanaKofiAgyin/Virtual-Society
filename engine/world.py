# engine/world.py

"""
Manages the grid coordinate system, randomly generates the world using
weighted probabilities, and handles broad phase tick updates.
"""

import random
from typing import List, Dict, Optional, Any
from config import TILE_PROBABILITIES, DEFAULT_WIDTH, DEFAULT_HEIGHT
from engine.tile import Tile

class World:
    """
    Represents the 2D grid world. Handles cell generation, state updates,
    and aggregate stats for resources and terrain types.
    """
    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT):
        """
        Initializes the world grid with the specified dimensions.
        
        Args:
            width (int): Grid width (number of columns).
            height (int): Grid height (number of rows).
        """
        if width <= 0 or height <= 0:
            raise ValueError("World dimensions must be positive, non-zero integers.")
            
        self.width: int = width
        self.height: int = height
        
        # Grid layout: self.grid[y][x] represents coordinate (x, y)
        self.grid: List[List[Tile]] = [[None for _ in range(width)] for _ in range(height)]
        
        # Generate the world terrain
        self.generate()

    def generate(self) -> None:
        """
        Populates the grid with Tile objects randomly selected using
        the weighted probabilities defined in the configuration.
        """
        tile_types = list(TILE_PROBABILITIES.keys())
        weights = list(TILE_PROBABILITIES.values())
        
        for y in range(self.height):
            for x in range(self.width):
                # Perform a weighted random choice to select the tile type
                chosen_type = random.choices(tile_types, weights=weights, k=1)[0]
                self.grid[y][x] = Tile(x, y, chosen_type)

    def tick(self) -> Dict[str, Dict[str, float]]:
        """
        Ticks every single tile in the world grid.
        Accumulates the change in resources across the entire world.
        
        Returns:
            Dict[str, Dict[str, float]]: A mapping of resource types to their global changes.
        """
        global_changes = {"wood": 0.0, "food": 0.0}
        
        for y in range(self.height):
            for x in range(self.width):
                tile_changes = self.grid[y][x].tick()
                for res_name, amount in tile_changes.items():
                    if res_name in global_changes:
                        global_changes[res_name] += amount
                        
        return global_changes

    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        """
        Safely retrieves a Tile object at coordinates (x, y).
        Returns None if coordinates are out of bounds.
        
        Args:
            x (int): X-coordinate.
            y (int): Y-coordinate.
            
        Returns:
            Optional[Tile]: The Tile at (x, y) or None.
        """
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return None

    def get_stats(self) -> Dict[str, Any]:
        """
        Aggregates statistical details of the world state, including
        terrain distribution counts and current resource sums.
        
        Returns:
            Dict[str, Any]: A dictionary containing world statistics.
        """
        stats = {
            "tile_counts": {k: 0 for k in TILE_PROBABILITIES.keys()},
            "resources": {"wood": 0.0, "food": 0.0},
            "walkable_count": 0,
            "total_tiles": self.width * self.height
        }
        
        for y in range(self.height):
            for x in range(self.width):
                tile = self.grid[y][x]
                
                # Count terrain type
                if tile.type in stats["tile_counts"]:
                    stats["tile_counts"][tile.type] += 1
                    
                # Walkability
                if tile.walkable:
                    stats["walkable_count"] += 1
                    
                # Accumulate resources
                for res_name, amount in tile.resources.items():
                    if res_name in stats["resources"]:
                        stats["resources"][res_name] += amount
                        
        return stats
