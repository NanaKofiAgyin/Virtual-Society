# tests/test_tile.py

"""
Unit tests for checking initialization and dynamic tick updates of individual Tile objects.
Upgraded in Phase 2 to cover dynamic terrain transitions, overcrowding limits, and isolation decay.
"""

import unittest
from engine.tile import Tile
from config import (
    TILE_SPECS, THRESHOLD_OVERCROWDED, THRESHOLD_ISOLATED, PENALTY_ISOLATED_DECAY
)

class TestTile(unittest.TestCase):
    """
    Tests tile behavior: initialization, walkable status, initial resources,
    and resource regeneration/decay bounds handling.
    """
    
    def test_initialization_valid(self):
        """Verifies that tiles are initialized with correct attributes based on config."""
        for tile_type, spec in TILE_SPECS.items():
            tile = Tile(x=5, y=5, tile_type=tile_type)
            self.assertEqual(tile.type, tile_type)
            self.assertEqual(tile.walkable, spec["walkable"])
            self.assertEqual(tile.display_char, spec["display_char"])
            
            # Check resource levels
            for res_name, res_spec in spec["resources"].items():
                self.assertEqual(tile.resources[res_name], float(res_spec["base"]))

    def test_initialization_invalid(self):
        """Ensures that passing an invalid tile type throws a ValueError."""
        with self.assertRaises(ValueError):
            Tile(x=0, y=0, tile_type="lava_fields_123")

    def test_resource_regeneration(self):
        """Tests that resource values increase appropriately during simulation ticks."""
        tile = Tile(x=0, y=0, tile_type="forest")
        wood_base = tile.resources["wood"]
        food_base = tile.resources["food"]
        
        # Get configured rates
        wood_spec = TILE_SPECS["forest"]["resources"]["wood"]
        wood_regen = wood_spec["regen_rate"]
        
        # Passing standard 3 neighbors (normal pressure)
        changes = tile.tick(same_neighbor_count=3)
        
        # Expectation
        expected_wood = wood_base + wood_regen
        self.assertEqual(tile.resources["wood"], expected_wood)
        self.assertEqual(changes["wood"], wood_regen)
        self.assertGreater(tile.resources["food"], food_base)

    def test_resource_limits_cap(self):
        """Ensures resources never exceed their designated maximum caps during regeneration."""
        tile = Tile(x=0, y=0, tile_type="forest")
        wood_spec = TILE_SPECS["forest"]["resources"]["wood"]
        max_wood = wood_spec["max"]
        
        # Manually inflate resources close to max to test clamp behavior
        tile.resources["wood"] = max_wood - 0.5
        
        # Tick the tile
        changes = tile.tick(same_neighbor_count=3)
        
        # Should be capped at max_wood exactly
        self.assertEqual(tile.resources["wood"], max_wood)
        self.assertEqual(changes["wood"], 0.5)
        
        # Ticking again should produce zero net change and remain capped
        changes = tile.tick(same_neighbor_count=3)
        self.assertEqual(tile.resources["wood"], max_wood)
        self.assertEqual(changes["wood"], 0.0)

    def test_transition_to(self):
        """Ensures tiles can transition to another type dynamically, updating attributes and resources."""
        tile = Tile(x=2, y=2, tile_type="grass")
        self.assertEqual(tile.type, "grass")
        self.assertTrue(tile.walkable)
        self.assertEqual(tile.resources["food"], 2.0)
        self.assertEqual(tile.resources["wood"], 0.0)
        
        # Transition to forest
        tile.transition_to("forest")
        self.assertEqual(tile.type, "forest")
        self.assertTrue(tile.walkable)
        self.assertEqual(tile.resources["wood"], 15.0)
        self.assertEqual(tile.resources["food"], 5.0)
        
        # Transition to mountain
        tile.transition_to("mountain")
        self.assertEqual(tile.type, "mountain")
        self.assertFalse(tile.walkable)
        self.assertEqual(tile.resources["wood"], 0.0)
        self.assertEqual(tile.resources["food"], 0.0)

    def test_overcrowding_pressure(self):
        """Verifies that growth/regeneration rate is halved when overcrowded."""
        tile = Tile(x=0, y=0, tile_type="forest")
        wood_base = tile.resources["wood"]
        
        wood_spec = TILE_SPECS["forest"]["resources"]["wood"]
        wood_regen = wood_spec["regen_rate"]
        
        # Tick with overcrowded neighbor count (e.g. 7)
        changes = tile.tick(same_neighbor_count=THRESHOLD_OVERCROWDED + 1)
        
        # Regen rate should be halved
        expected_wood = wood_base + (wood_regen * 0.5)
        self.assertEqual(tile.resources["wood"], expected_wood)
        self.assertEqual(changes["wood"], wood_regen * 0.5)

    def test_isolation_decay(self):
        """Verifies that isolated tiles experience dynamic resource decay penalty."""
        tile = Tile(x=0, y=0, tile_type="forest")
        # Artificially set wood to 50.0
        tile.resources["wood"] = 50.0
        
        wood_spec = TILE_SPECS["forest"]["resources"]["wood"]
        wood_regen = wood_spec["regen_rate"]
        
        # Tick with isolated neighbor count (e.g. 0)
        changes = tile.tick(same_neighbor_count=THRESHOLD_ISOLATED)
        
        # Net change should be: wood_regen - (base_decay + PENALTY_ISOLATED_DECAY)
        # For forest: base_decay = 0.0, wood_regen = 2.0. Isolated penalty = 0.5.
        # Net = 2.0 - 0.5 = 1.5
        expected_change = wood_regen - PENALTY_ISOLATED_DECAY
        self.assertEqual(changes["wood"], expected_change)
        self.assertEqual(tile.resources["wood"], 50.0 + expected_change)

    def test_status_string(self):
        """Checks if get_status_str returns expected descriptive diagnostic data."""
        tile = Tile(x=2, y=3, tile_type="mountain")
        status = tile.get_status_str()
        self.assertIn("Tile(2,3)", status)
        self.assertIn("Mountain", status)
        self.assertIn("Impassable", status)

if __name__ == "__main__":
    unittest.main()
