# engine/world.py

"""
Manages the grid coordinate system, randomly generates the world using
weighted probabilities, and handles cellular-automata-style ticks including
Moore neighborhood counts, terrain transitions, and resource dynamics.
"""

import random
from typing import List, Dict, Optional, Any
from config import (
    TILE_PROBABILITIES, DEFAULT_WIDTH, DEFAULT_HEIGHT,
    SPREAD_PROB_FOREST, SPREAD_PROB_WATER, SPREAD_PROB_GRASS,
    THRESHOLD_ISOLATED
)
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

    def get_neighbors(self, x: int, y: int) -> List[Tile]:
        """
        Retrieves all valid neighboring Tile objects using a Moore neighborhood (up to 8 directions).
        
        Args:
            x (int): X-coordinate of target tile.
            y (int): Y-coordinate of target tile.
            
        Returns:
            List[Tile]: Surrounding valid Tile objects.
        """
        neighbors = []
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                tile = self.get_tile(nx, ny)
                if tile:
                    neighbors.append(tile)
        return neighbors

    def tick(self) -> Dict[str, float]:
        """
        Ticks every single tile in the world grid using a two-pass cycle.
        Pass 1: Gathers neighbor influences, checks spread conditions, and schedules transitions.
        Pass 2: Triggers transitions and ticks individual resources under local pressures.
        
        Returns:
            Dict[str, float]: A mapping of resource types to their global changes.
        """
        transitions = {}  # maps (x, y) -> new_type string
        neighbor_counts = {}  # maps (x, y) -> same_type_count
        
        # Pass 1: Scan grid state and calculate dynamic transitions
        for y in range(self.height):
            for x in range(self.width):
                tile = self.grid[y][x]
                neighbors = self.get_neighbors(x, y)
                
                # Count matching types
                same_count = sum(1 for n in neighbors if n.type == tile.type)
                neighbor_counts[(x, y)] = same_count
                
                # Count adjacent neighbors of other types
                forest_count = sum(1 for n in neighbors if n.type == "forest")
                water_count = sum(1 for n in neighbors if n.type == "water")
                grass_count = sum(1 for n in neighbors if n.type == "grass")
                
                # Spreading transitions
                if tile.type == "grass":
                    # Forest spreading into grass
                    if forest_count > 0 and random.random() < (forest_count * SPREAD_PROB_FOREST):
                        transitions[(x, y)] = "forest"
                    # Water spreading into grass
                    elif water_count > 0 and random.random() < (water_count * SPREAD_PROB_WATER):
                        transitions[(x, y)] = "water"
                        
                elif tile.type == "mountain":
                    # Grass spreading/erosion into mountain
                    if grass_count > 0 and random.random() < (grass_count * SPREAD_PROB_GRASS):
                        transitions[(x, y)] = "grass"
                    # Isolated mountain erosion
                    elif same_count <= THRESHOLD_ISOLATED and random.random() < 0.05:
                        transitions[(x, y)] = "grass"
                        
                elif tile.type == "forest":
                    # Depleted forest reverts to grass
                    if tile.resources.get("wood", 0.0) <= 0.0:
                        transitions[(x, y)] = "grass"
                    # Isolated forest die-back risk
                    elif same_count <= THRESHOLD_ISOLATED and tile.resources.get("wood", 0.0) <= 10.0 and random.random() < 0.10:
                        transitions[(x, y)] = "grass"
                        
                elif tile.type == "water":
                    # Isolated water body drying up risk
                    if same_count <= THRESHOLD_ISOLATED and tile.resources.get("food", 0.0) <= 0.0 and random.random() < 0.10:
                        transitions[(x, y)] = "grass"
                        
        # Pass 2: Apply scheduled updates and execute resource ticks
        global_changes = {"wood": 0.0, "food": 0.0}
        
        for y in range(self.height):
            for x in range(self.width):
                tile = self.grid[y][x]
                
                # Apply terrain transition
                if (x, y) in transitions:
                    tile.transition_to(transitions[(x, y)])
                    
                # Execute tile tick passing matching neighbor pressure counts
                same_count = neighbor_counts.get((x, y), 3)
                tile_changes = tile.tick(same_neighbor_count=same_count)
                
                # Accumulate global changes
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
