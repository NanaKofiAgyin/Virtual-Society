# tests/test_world.py

"""
Unit tests for checking initialization, random generation probabilities,
and state transitions of the World grid under dynamic environmental pressures.
"""

import unittest
from unittest.mock import patch
from engine.world import World
from engine.tile import Tile
from config import TILE_PROBABILITIES

class TestWorld(unittest.TestCase):
    """
    Tests spatial layouts, safety coordinate fetches, tick propagation,
    and statistical probability spreads in the simulated World grid.
    """
    
    def test_dimensions_and_types(self):
        """Validates world creates a grid with precise requested dimensions containing Tile objects."""
        width = 15
        height = 10
        world = World(width=width, height=height)
        
        self.assertEqual(world.width, width)
        self.assertEqual(world.height, height)
        self.assertEqual(len(world.grid), height)
        self.assertEqual(len(world.grid[0]), width)
        
        for y in range(height):
            for x in range(width):
                tile = world.grid[y][x]
                self.assertIsInstance(tile, Tile)
                self.assertEqual(tile.x, x)
                self.assertEqual(tile.y, y)

    def test_invalid_dimensions(self):
        """Ensures initiating world grids with 0 or negative coordinates raises ValueErrors."""
        with self.assertRaises(ValueError):
            World(width=0, height=10)
        with self.assertRaises(ValueError):
            World(width=10, height=-5)

    def test_safe_tile_retrieval(self):
        """Verifies boundary checking of get_tile for valid and out-of-bounds inputs."""
        world = World(width=5, height=5)
        
        # Valid fetches
        tile = world.get_tile(2, 2)
        self.assertIsNotNone(tile)
        self.assertEqual(tile.x, 2)
        self.assertEqual(tile.y, 2)
        
        # Boundary edges
        self.assertIsNone(world.get_tile(-1, 2))
        self.assertIsNone(world.get_tile(5, 2))
        self.assertIsNone(world.get_tile(2, -1))
        self.assertIsNone(world.get_tile(2, 5))

    def test_moore_neighbors(self):
        """Verifies that get_neighbors correctly computes Moore neighbors (up to 8, with boundary safety)."""
        world = World(width=3, height=3)
        # Center tile (1, 1) has exactly 8 neighbors in a 3x3 grid
        center_neighbors = world.get_neighbors(1, 1)
        self.assertEqual(len(center_neighbors), 8)
        
        # Corner tile (0, 0) has exactly 3 neighbors in a 3x3 grid
        corner_neighbors = world.get_neighbors(0, 0)
        self.assertEqual(len(corner_neighbors), 3)
        
        # Verify specific neighbors for (0,0) -> should be (1,0), (0,1), (1,1)
        coords = {(n.x, n.y) for n in corner_neighbors}
        self.assertEqual(coords, {(1, 0), (0, 1), (1, 1)})

    def test_world_tick_propagation(self):
        """Asserts that running a world-wide tick modifies global resource levels without random transitions."""
        world = World(width=5, height=5)
        # Clear agents to prevent food consumption from altering resource math
        world.agents = []
        
        initial_stats = world.get_stats()
        initial_wood = initial_stats["resources"]["wood"]
        initial_food = initial_stats["resources"]["food"]
        
        # Mock random.random to return 1.0 to disable any dynamic random terrain transitions
        with patch('random.random', return_value=1.0):
            global_changes = world.tick()
        
        updated_stats = world.get_stats()
        updated_wood = updated_stats["resources"]["wood"]
        updated_food = updated_stats["resources"]["food"]
        
        # Compare actual calculations
        self.assertAlmostEqual(updated_wood, initial_wood + global_changes["wood"])
        self.assertAlmostEqual(updated_food, initial_food + global_changes["food"])

    def test_terrain_depletion_transition(self):
        """Verifies that a forest tile with 0 wood resource transitions to grass on the next tick."""
        world = World(width=3, height=3)
        
        # Manually force all tiles to grass first
        for y in range(world.height):
            for x in range(world.width):
                world.grid[y][x].transition_to("grass")
                
        # Make the center tile a forest
        center_tile = world.grid[1][1]
        center_tile.transition_to("forest")
        
        # Set its wood resource to 0.0
        center_tile.resources["wood"] = 0.0
        
        # Tick the world
        world.tick()
        
        # The center tile should have reverted to grass
        self.assertEqual(center_tile.type, "grass")

    def test_generation_probabilities_spread(self):
        """
        Generates a large world to statistically verify that terrain distributions
        conform to configured probabilities within a reasonable variance margin.
        """
        # Create a large grid for statistical sample size
        world = World(width=50, height=50)  # 2500 tiles
        stats = world.get_stats()
        total_tiles = stats["total_tiles"]
        
        self.assertEqual(total_tiles, 2500)
        
        # Check that actual fractions are within a +- 10% margin of target values
        for tile_type, target_prob in TILE_PROBABILITIES.items():
            actual_count = stats["tile_counts"].get(tile_type, 0)
            actual_prob = actual_count / total_tiles
            
            # Allow variance due to random distributions
            margin = 0.10
            self.assertAlmostEqual(actual_prob, target_prob, delta=margin,
                                   msg=f"Type '{tile_type}' probability {actual_prob} drifted outside margin of {target_prob}")

    def test_agent_world_integration(self):
        """Verifies that the World initializes agents, updates them on ticks, and handles starvation mortality."""
        # Create world
        world = World(width=5, height=5)
        
        # Verify initial population was spawned
        from config import AGENT_INITIAL_POPULATION
        self.assertEqual(len(world.agents), AGENT_INITIAL_POPULATION)
        
        # Set all agents to 0.0 energy to test starvation cleanup on next tick
        for agent in world.agents:
            agent.energy = 0.0
            
        # Tick the world once
        world.tick()
        
        # Verify that all starved agents have been removed
        self.assertEqual(len(world.agents), 0)

if __name__ == "__main__":
    unittest.main()
