# tests/test_agent.py

"""
Unit tests verifying state initialization, utility action choices (EAT, REST, REPRODUCE, MOVE),
metabolic reductions, reproduction splits, and starvation limits of autonomous Agents.
"""

import unittest
from unittest.mock import MagicMock
from engine.agent import Agent
from engine.world import World
from engine.tile import Tile
from config import (
    AGENT_START_ENERGY, AGENT_MAX_ENERGY, AGENT_REPRODUCE_THRESHOLD,
    AGENT_METABOLISM, AGENT_MOVE_COST, AGENT_REST_GAIN, AGENT_EAT_AMOUNT,
    AGENT_FOOD_TO_ENERGY_RATIO
)

class TestAgent(unittest.TestCase):
    """
    Tests Agent autonomy behaviors and state actions inside mock/live World environments.
    """
    
    def test_initialization(self):
        """Verifies agents construct with correct default positioning and energy properties."""
        agent = Agent(x=4, y=7)
        self.assertEqual(agent.x, 4)
        self.assertEqual(agent.y, 7)
        self.assertEqual(agent.energy, AGENT_START_ENERGY)

    def test_reproduction_split(self):
        """Ensures agents split energy exactly in half with their offspring when reproducing."""
        agent = Agent(x=2, y=2, energy=90.0)
        
        # Create a mock world
        mock_world = MagicMock()
        mock_world.get_tile.return_value = Tile(x=2, y=2, tile_type="grass")
        
        # Force high energy reproduce utility best action by running act
        child = agent.decide_and_act(mock_world)
        
        self.assertIsNotNone(child)
        self.assertIsInstance(child, Agent)
        self.assertEqual(child.x, 2)
        self.assertEqual(child.y, 2)
        
        # Child gets exactly 90.0 / 2 = 45.0
        self.assertEqual(child.energy, 45.0)
        # Parent gets 45.0 - metabolism (1.0) = 44.0
        self.assertEqual(agent.energy, 45.0 - AGENT_METABOLISM)

    def test_eating_behavior(self):
        """Verifies that an extremely hungry agent consumes food on its tile and restores energy."""
        # Low energy: 20.0
        agent = Agent(x=0, y=0, energy=20.0)
        
        # Set up a real tile and a mock world
        tile = Tile(x=0, y=0, tile_type="grass")
        tile.resources["food"] = 8.0 # ample food
        
        mock_world = MagicMock()
        mock_world.get_tile.return_value = tile
        
        # When checking moves, return no moves or negative moves to force EAT
        mock_world.get_tile.side_effect = lambda x, y: tile if (x == 0 and y == 0) else None
        
        child = agent.decide_and_act(mock_world)
        
        self.assertIsNone(child)
        # Ample food: eats AGENT_EAT_AMOUNT = 3.0
        # Grass food drops from 8.0 to 5.0
        self.assertEqual(tile.resources["food"], 5.0)
        
        # Energy change: +3.0 * AGENT_FOOD_TO_ENERGY_RATIO (8.0) - AGENT_METABOLISM (1.0) = +23.0
        # Expected final: 20.0 + 23.0 = 43.0
        self.assertEqual(agent.energy, 43.0)

    def test_resting_behavior(self):
        """Verifies that a moderately tired agent rests when no food is available."""
        # Energy: 30.0 (slightly tired, rest score positive, eat score is 0 due to no food)
        agent = Agent(x=0, y=0, energy=30.0)
        
        tile = Tile(x=0, y=0, tile_type="mountain") # mountain has no food
        
        mock_world = MagicMock()
        mock_world.get_tile.return_value = tile
        mock_world.get_tile.side_effect = lambda x, y: tile if (x == 0 and y == 0) else None
        
        child = agent.decide_and_act(mock_world)
        
        self.assertIsNone(child)
        # Should rest and gain AGENT_REST_GAIN (1.0) energy
        # Final energy: 30.0 + 1.0 = 31.0
        self.assertEqual(agent.energy, 31.0)

    def test_moving_behavior(self):
        """Verifies that agents choose to move towards tiles with high food resources."""
        # High energy agent (doesn't want to eat immediately, but move utility will dominate)
        agent = Agent(x=1, y=1, energy=70.0)
        
        tile_current = Tile(x=1, y=1, tile_type="grass")
        tile_current.resources["food"] = 0.0 # empty
        
        tile_target = Tile(x=2, y=2, tile_type="grass")
        tile_target.resources["food"] = 10.0 # full of food!
        
        mock_world = MagicMock()
        
        def mock_get_tile(x, y):
            if x == 1 and y == 1:
                return tile_current
            if x == 2 and y == 2:
                return tile_target
            # return basic empty walkable tile for others
            return Tile(x, y, tile_type="grass")
            
        mock_world.get_tile.side_effect = mock_get_tile
        
        child = agent.decide_and_act(mock_world)
        
        self.assertIsNone(child)
        # Agent should have moved to (2, 2)
        self.assertEqual(agent.x, 2)
        self.assertEqual(agent.y, 2)
        
        # Energy cost: - (AGENT_MOVE_COST (2.0) + AGENT_METABOLISM (1.0)) = -3.0
        # Final: 70.0 - 3.0 = 67.0
        self.assertEqual(agent.energy, 67.0)

if __name__ == "__main__":
    unittest.main()
