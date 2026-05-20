# config.py

"""
Configuration settings for the grid-based world simulation engine.
This file centralizes environment attributes, probabilities, visual characters,
and resource behaviors (regeneration/decay) to ensure clean modularity.
"""

# World Dimensions
DEFAULT_WIDTH = 20
DEFAULT_HEIGHT = 20

# Weighted generation probabilities (must sum to 1.0)
TILE_PROBABILITIES = {
    "grass": 0.50,
    "forest": 0.20,
    "water": 0.20,
    "mountain": 0.10
}

# ANSI Escape Codes for styling CLI visual output
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_FG_GREEN = "\033[32m"
ANSI_FG_BRIGHT_GREEN = "\033[92m"
ANSI_FG_BLUE = "\033[34m"
ANSI_FG_WHITE = "\033[37m"
ANSI_FG_CYAN = "\033[36m"
ANSI_FG_YELLOW = "\033[33m"

# Attributes per Tile Type
# - walkable: Boolean flag indicating if agents/entities can traverse
# - display_char: Visual representation of the tile in the terminal
# - color_code: ANSI escape sequence for visual representation
# - pygame_color: RGB tuple representing the tile in the Pygame visualizer
# - resources: Dictionary mapping resource type -> {base, max, regen_rate}
TILE_SPECS = {
    "grass": {
        "walkable": True,
        "display_char": ".",
        "color_code": ANSI_FG_BRIGHT_GREEN,
        "pygame_color": (46, 204, 113),  # Emerald Green
        "resources": {
            "wood": {
                "base": 0.0,
                "max": 0.0,
                "regen_rate": 0.0
            },
            "food": {
                "base": 2.0,
                "max": 10.0,
                "regen_rate": 0.2
            }
        }
    },
    "forest": {
        "walkable": True,
        "display_char": "♣",
        "color_code": ANSI_FG_GREEN + ANSI_BOLD,
        "pygame_color": (39, 174, 96),   # Darker Forest Green
        "resources": {
            "wood": {
                "base": 15.0,
                "max": 100.0,
                "regen_rate": 1.5
            },
            "food": {
                "base": 5.0,
                "max": 20.0,
                "regen_rate": 0.4
            }
        }
    },
    "water": {
        "walkable": False,
        "display_char": "~",
        "color_code": ANSI_FG_BLUE,
        "pygame_color": (41, 128, 185),  # River Blue
        "resources": {
            "wood": {
                "base": 0.0,
                "max": 0.0,
                "regen_rate": 0.0
            },
            "food": {
                "base": 4.0,
                "max": 25.0,
                "regen_rate": 0.8  # Fish reproducing
            }
        }
    },
    "mountain": {
        "walkable": False,
        "display_char": "▲",
        "color_code": ANSI_FG_WHITE + ANSI_BOLD,
        "pygame_color": (127, 140, 141), # Steel Grey
        "resources": {
            "wood": {
                "base": 0.0,
                "max": 0.0,
                "regen_rate": 0.0
            },
            "food": {
                "base": 0.0,
                "max": 0.0,
                "regen_rate": 0.0
            }
        }
    }
}

# Simulation default behaviors
DEFAULT_TICK_DELAY = 0.5  # Seconds between ticks

# Pygame Window & GUI configuration parameters
PYGAME_CELL_SIZE = 30           # Screen pixels per square cell
PYGAME_SIDEBAR_WIDTH = 280      # Screen pixels for statistics panel
PYGAME_FPS = 60                 # Frame rate for user event reactivity

# Pygame GUI Palette (RGB Tuples)
PYGAME_COLOR_BG = (44, 62, 80)       # Dark slate blue background
PYGAME_COLOR_GRID = (52, 73, 94)     # Secondary grid divider lines
PYGAME_COLOR_TEXT = (236, 240, 241)  # Off-white for labels and values
PYGAME_COLOR_ACCENT = (241, 196, 15)  # Custom accent color for headings (yellow)
PYGAME_COLOR_MUTED = (149, 165, 166)  # Neutral grey for hover keys/subtitles
PYGAME_COLOR_HIGHLIGHT = (231, 76, 60) # Coral highlight for impassable/active indicators

# Phase 2: Ecological Dynamics & Environmental Pressures
# - Spreading Probabilities (per matching neighbor in Moore neighborhood per tick)
SPREAD_PROB_FOREST = 0.02   # 2% chance per adjacent forest neighbor to convert grass -> forest
SPREAD_PROB_WATER = 0.005   # 0.5% chance per adjacent water neighbor to convert grass -> water
SPREAD_PROB_GRASS = 0.01    # 1% chance per adjacent grass neighbor to convert mountain -> grass (erosion)

# - Environmental Pressure limits & rates
THRESHOLD_OVERCROWDED = 6   # halving growth factor if >= 6 similar neighbors
THRESHOLD_ISOLATED = 1       # natural resource decay penalty if <= 1 similar neighbors
PENALTY_ISOLATED_DECAY = 0.5 # amount subtracted from wood/food when isolated per tick
