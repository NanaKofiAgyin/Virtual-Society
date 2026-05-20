# engine/simulation.py

"""
Controls the persistent simulation loop, handles time ticks, and manages
the real-time terminal visualizer.
"""

import os
import sys
import time
from typing import Optional, Dict
from config import ANSI_RESET, ANSI_BOLD, ANSI_FG_YELLOW, ANSI_FG_CYAN
from engine.world import World

class Simulation:
    """
    The orchestrator of the simulation. Runs the loop, triggers tick updates
    on the world, and handles the CLI rendering of the grid and stats.
    """
    def __init__(self, world: World, tick_delay: float = 0.5, max_ticks: Optional[int] = None):
        """
        Initializes the simulation controller.
        
        Args:
            world (World): The simulated world grid.
            tick_delay (float): Seconds to sleep between ticks.
            max_ticks (Optional[int]): Maximum number of ticks to run. If None, runs indefinitely.
        """
        self.world: World = world
        self.tick_delay: float = tick_delay
        self.max_ticks: Optional[int] = max_ticks
        self.current_tick: int = 0
        self.last_net_changes: Dict[str, float] = {"wood": 0.0, "food": 0.0}

    def clear_console(self) -> None:
        """
        Clears the terminal screen and moves the cursor to the top-left corner
        using ANSI escape sequences to prevent visual flickering.
        """
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.flush()

    def render(self) -> None:
        """
        Renders the current state of the world to the console using ANSI styling.
        Includes a bordered map display and a detailed statistics panel.
        """
        stats = self.world.get_stats()
        total_tiles = stats["total_tiles"]
        
        # Build Title Header
        header = []
        header.append(f"{ANSI_BOLD}{ANSI_FG_YELLOW}=================================================={ANSI_RESET}")
        header.append(f"   {ANSI_BOLD}VIRTUAL SOCIETY - WORLD SIMULATION ENGINE{ANSI_RESET}")
        header.append(f"{ANSI_BOLD}{ANSI_FG_YELLOW}=================================================={ANSI_RESET}")
        
        limit_str = f" / {self.max_ticks}" if self.max_ticks is not None else ""
        header.append(f"Tick: {ANSI_BOLD}{self.current_tick}{ANSI_RESET}{limit_str}   |   Tick Delay: {self.tick_delay}s")
        header.append("")
        
        # Build Map Grid (Bordered)
        map_lines = []
        top_border = "┌" + "─" * (self.world.width * 2 + 1) + "┐"
        bottom_border = "└" + "─" * (self.world.width * 2 + 1) + "┘"
        
        map_lines.append(top_border)
        for y in range(self.world.height):
            row_chars = []
            for x in range(self.world.width):
                tile = self.world.grid[y][x]
                colored_char = f"{tile.color_code}{tile.display_char}{ANSI_RESET}"
                row_chars.append(colored_char)
            map_lines.append(f"│ {' '.join(row_chars)} │")
        map_lines.append(bottom_border)
        
        # Build Detailed Stats Panel
        stats_panel = []
        stats_panel.append(f"{ANSI_BOLD}[ World Statistics ]{ANSI_RESET}")
        stats_panel.append("Terrain Composition:")
        
        for tile_type, count in stats["tile_counts"].items():
            pct = (count / total_tiles) * 100
            stats_panel.append(f"  - {tile_type.capitalize():<8}: {pct:>5.1f}% ({count:>3}/{total_tiles})")
            
        stats_panel.append("")
        stats_panel.append("Global Resource Pools:")
        
        wood_val = stats["resources"]["wood"]
        wood_change = self.last_net_changes.get("wood", 0.0)
        wood_change_str = f"(+{wood_change:.1f})" if wood_change >= 0 else f"({wood_change:.1f})"
        
        food_val = stats["resources"]["food"]
        food_change = self.last_net_changes.get("food", 0.0)
        food_change_str = f"(+{food_change:.1f})" if food_change >= 0 else f"({food_change:.1f})"
        
        stats_panel.append(f"  - Wood: {ANSI_BOLD}{wood_val:>7.1f}{ANSI_RESET} {ANSI_FG_CYAN}{wood_change_str:<8}{ANSI_RESET}")
        stats_panel.append(f"  - Food: {ANSI_BOLD}{food_val:>7.1f}{ANSI_RESET} {ANSI_FG_CYAN}{food_change_str:<8}{ANSI_RESET}")
        
        stats_panel.append("")
        walk_pct = (stats["walkable_count"] / total_tiles) * 100
        stats_panel.append(f"Walkable Area: {stats['walkable_count']}/{total_tiles} tiles ({walk_pct:.1f}%)")
        stats_panel.append(f"{ANSI_BOLD}{ANSI_FG_YELLOW}=================================================={ANSI_RESET}")
        stats_panel.append("Press Ctrl+C to safely pause/exit the simulation.")
        
        # Combine all parts and output
        self.clear_console()
        output = "\n".join(header + map_lines + [""] + stats_panel)
        sys.stdout.write(output + "\n")
        sys.stdout.flush()

    def run(self) -> None:
        """
        Starts and maintains the simulation loop.
        Triggers tick transitions and sleep pauses, catching interrupts for a
        clean exit presentation.
        """
        self.render()  # Render initial state (Tick 0)
        
        try:
            while self.max_ticks is None or self.current_tick < self.max_ticks:
                time.sleep(self.tick_delay)
                self.current_tick += 1
                
                # Update all cells in the world and capture resource changes
                self.last_net_changes = self.world.tick()
                
                # Render the updated state
                self.render()
                
        except KeyboardInterrupt:
            # Handle graceful keyboard interrupt
            sys.stdout.write(f"\n\n{ANSI_BOLD}Simulation paused by user.{ANSI_RESET}\n")
            sys.stdout.write("Finalizing session state...\n")
            sys.stdout.flush()
            time.sleep(0.5)
            
        sys.stdout.write(f"{ANSI_BOLD}Simulation ended successfully at Tick {self.current_tick}.{ANSI_RESET}\n")
        sys.stdout.flush()
