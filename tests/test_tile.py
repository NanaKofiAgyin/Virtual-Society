# tests/test_tile.py

"""
Unit tests for checking initialization and dynamic tick updates of individual Tile objects.
"""

import unittest
from engine.tile import Tile
from config import TILE_SPECS

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
        # Forest tiles have significant resource regeneration rates
        tile = Tile(x=0, y=0, tile_type="forest")
        wood_base = tile.resources["wood"]
        food_base = tile.resources["food"]
        
        # Get configured rates
        wood_spec = TILE_SPECS["forest"]["resources"]["wood"]
        wood_regen = wood_spec["regen_rate"]
        
        changes = tile.tick()
        
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
        changes = tile.tick()
        
        # Should be capped at max_wood exactly
        self.assertEqual(tile.resources["wood"], max_wood)
        self.assertEqual(changes["wood"], 0.5)
        
        # Ticking again should produce zero net change and remain capped
        changes = tile.tick()
        self.assertEqual(tile.resources["wood"], max_wood)
        self.assertEqual(changes["wood"], 0.0)

    def test_status_string(self):
        """Checks if get_status_str returns expected descriptive diagnostic data."""
        tile = Tile(x=2, y=3, tile_type="mountain")
        status = tile.get_status_str()
        self.assertIn("Tile(2,3)", status)
        self.assertIn("Mountain", status)
        self.assertIn("Impassable", status)

if __name__ == "__main__":
    unittest.main()
