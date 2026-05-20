# engine/pygame_renderer.py

"""
Decoupled Graphic Visualizer module for Virtual Society using Pygame.
Draws the simulated grid world map, provides mouse-hover cell queries, and renders
a detailed statistics dashboard live.
"""

import sys
from typing import Dict, Any, Optional
import pygame

from config import (
    PYGAME_CELL_SIZE, PYGAME_SIDEBAR_WIDTH, PYGAME_FPS,
    PYGAME_COLOR_BG, PYGAME_COLOR_GRID, PYGAME_COLOR_TEXT,
    PYGAME_COLOR_ACCENT, PYGAME_COLOR_MUTED, PYGAME_COLOR_HIGHLIGHT,
    TILE_SPECS
)
from engine.world import World

class PygameRenderer:
    """
    Renders the World grid using Pygame. Runs a custom frame rate loop and
    maps ticks using Pygame custom timers. Fully decoupled from core logic.
    """
    def __init__(self, world: World, tick_delay: float = 0.5, max_ticks: Optional[int] = None):
        """
        Initializes the Pygame rendering layer.
        
        Args:
            world (World): The simulation grid.
            tick_delay (float): Seconds between world ticks.
            max_ticks (Optional[int]): Maximum number of ticks to run before auto-exiting.
        """
        self.world: World = world
        self.tick_delay: float = tick_delay
        self.max_ticks: Optional[int] = max_ticks
        
        # Dimensions
        self.grid_width_px: int = self.world.width * PYGAME_CELL_SIZE
        self.grid_height_px: int = self.world.height * PYGAME_CELL_SIZE
        self.win_width: int = self.grid_width_px + PYGAME_SIDEBAR_WIDTH
        self.win_height: int = self.grid_height_px
        
        # Simulation loop state
        self.current_tick: int = 0
        self.last_net_changes: Dict[str, float] = {"wood": 0.0, "food": 0.0}
        
        # Pygame resources (loaded in run())
        self.screen: Optional[pygame.Surface] = None
        self.clock: Optional[pygame.time.Clock] = None
        self.font_title: Optional[pygame.font.Font] = None
        self.font_header: Optional[pygame.font.Font] = None
        self.font_body: Optional[pygame.font.Font] = None
        self.font_small: Optional[pygame.font.Font] = None

    def _init_pygame(self) -> None:
        """
        Initializes the Pygame environment, sets up display, window title,
        custom fonts, and the tick event timer.
        """
        try:
            pygame.init()
            pygame.font.init()
        except pygame.error as err:
            print(f"\n[ERROR] Pygame failed to initialize the environment: {err}")
            raise err

        # Create screen
        try:
            self.screen = pygame.display.set_mode((self.win_width, self.win_height))
        except pygame.error as err:
            print(f"\n[ERROR] Pygame failed to open the graphic window device.")
            print(f"Error Details: {err}")
            print("Please confirm X11 or a desktop display environment is active.")
            print("To bypass, rerun simulation with the CLI runner: '--mode cli'\n")
            raise err
            
        pygame.display.set_caption("Virtual Society - Persistent World Engine")
        
        self.clock = pygame.time.Clock()
        
        # Load standard system fonts
        self.font_title = pygame.font.SysFont("Arial", 18, bold=True)
        self.font_header = pygame.font.SysFont("Arial", 14, bold=True)
        self.font_body = pygame.font.SysFont("Arial", 13)
        self.font_small = pygame.font.SysFont("Arial", 11)
        
        # Setup Tick Event Timer
        self.TICK_EVENT = pygame.USEREVENT + 1
        pygame.time.set_timer(self.TICK_EVENT, int(self.tick_delay * 1000))

    def _draw_text(self, text: str, x: int, y: int, color: tuple, font: pygame.font.Font) -> None:
        """Draws standard aliased text onto the screen."""
        text_surface = font.render(text, True, color)
        self.screen.blit(text_surface, (x, y))

    def _draw_grid(self) -> None:
        """Renders the grid world cells with dynamic brightness reflecting resource richness."""
        for y in range(self.world.height):
            for x in range(self.world.width):
                tile = self.world.grid[y][x]
                spec = TILE_SPECS.get(tile.type, {})
                base_color = spec.get("pygame_color", (0, 0, 0))
                
                # Determine richness ratio [0.0, 1.0] across all its resources
                resource_specs = spec.get("resources", {})
                ratios = []
                for res_name, res_spec in resource_specs.items():
                    max_limit = res_spec.get("max", 0.0)
                    if max_limit > 0.0:
                        current = tile.resources.get(res_name, 0.0)
                        ratios.append(current / max_limit)
                
                # Average ratio across available dynamic resources, defaulting to 1.0 (e.g. for mountain)
                ratio = sum(ratios) / len(ratios) if ratios else 1.0
                
                # Scale color intensity: 40% (depleted) to 100% (rich) brightness
                intensity_factor = 0.4 + 0.6 * ratio
                
                # Interpolate RGB color
                color = (
                    int(base_color[0] * intensity_factor),
                    int(base_color[1] * intensity_factor),
                    int(base_color[2] * intensity_factor)
                )
                
                rect = pygame.Rect(
                    x * PYGAME_CELL_SIZE,
                    y * PYGAME_CELL_SIZE,
                    PYGAME_CELL_SIZE,
                    PYGAME_CELL_SIZE
                )
                
                # Draw tile fill
                pygame.draw.rect(self.screen, color, rect)
                
                # Draw subtle grid boundary border
                pygame.draw.rect(self.screen, PYGAME_COLOR_GRID, rect, 1)

    def _draw_sidebar(self, stats: Dict[str, Any], mouse_pos: tuple) -> None:
        """
        Renders the right panel containing statistics, interactive hover data,
        and terrain legends.
        """
        # Draw background panel fill
        panel_rect = pygame.Rect(self.grid_width_px, 0, PYGAME_SIDEBAR_WIDTH, self.win_height)
        pygame.draw.rect(self.screen, PYGAME_COLOR_BG, panel_rect)
        
        # Draw dividing borderline
        pygame.draw.line(
            self.screen, PYGAME_COLOR_GRID,
            (self.grid_width_px, 0), (self.grid_width_px, self.win_height), 2
        )
        
        start_x = self.grid_width_px + 20
        y_offset = 15
        
        # 1. Branding Header
        self._draw_text("VIRTUAL SOCIETY", start_x, y_offset, PYGAME_COLOR_ACCENT, self.font_title)
        y_offset += 22
        self._draw_text("Persistent World Engine", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_small)
        
        # Divider Line
        y_offset += 18
        pygame.draw.line(
            self.screen, PYGAME_COLOR_GRID,
            (start_x, y_offset), (self.win_width - 20, y_offset), 1
        )
        
        # 2. General Simulation Stats
        y_offset += 15
        self._draw_text(f"Tick: {self.current_tick}", start_x, y_offset, PYGAME_COLOR_TEXT, self.font_header)
        y_offset += 18
        self._draw_text(f"Tick Delay: {self.tick_delay}s", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
        
        # 3. Global Resources
        y_offset += 25
        self._draw_text("Global Resource Pools:", start_x, y_offset, PYGAME_COLOR_TEXT, self.font_header)
        
        wood_val = stats["resources"]["wood"]
        wood_change = self.last_net_changes.get("wood", 0.0)
        wood_change_str = f"+{wood_change:.1f}" if wood_change >= 0 else f"{wood_change:.1f}"
        
        food_val = stats["resources"]["food"]
        food_change = self.last_net_changes.get("food", 0.0)
        food_change_str = f"+{food_change:.1f}" if food_change >= 0 else f"{food_change:.1f}"
        
        y_offset += 18
        self._draw_text(f"Wood: {wood_val:.1f} ({wood_change_str})", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
        y_offset += 16
        self._draw_text(f"Food: {food_val:.1f} ({food_change_str})", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
        
        # Divider Line
        y_offset += 25
        pygame.draw.line(
            self.screen, PYGAME_COLOR_GRID,
            (start_x, y_offset), (self.win_width - 20, y_offset), 1
        )
        
        # 4. Interactive Hover Inspector
        y_offset += 15
        self._draw_text("Hover Inspector:", start_x, y_offset, PYGAME_COLOR_TEXT, self.font_header)
        
        mouse_x, mouse_y = mouse_pos
        hover_x = mouse_x // PYGAME_CELL_SIZE
        hover_y = mouse_y // PYGAME_CELL_SIZE
        
        # Safely extract tile info if coordinates are over the grid
        tile = self.world.get_tile(hover_x, hover_y)
        if tile:
            y_offset += 18
            self._draw_text(f"Coordinate : ({tile.x}, {tile.y})", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
            
            y_offset += 16
            self._draw_text(f"Terrain Type: {tile.type.capitalize()}", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
            
            y_offset += 16
            walk_str = "Yes" if tile.walkable else "No"
            walk_color = PYGAME_COLOR_TEXT if tile.walkable else PYGAME_COLOR_HIGHLIGHT
            self._draw_text(f"Walkable     : {walk_str}", start_x, y_offset, walk_color, self.font_body)
            
            y_offset += 16
            wood_spec = TILE_SPECS[tile.type]["resources"]["wood"]
            max_w = wood_spec["max"]
            self._draw_text(f"Wood Level : {tile.resources.get('wood', 0.0):.1f} / {max_w:.0f}", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
            
            y_offset += 16
            food_spec = TILE_SPECS[tile.type]["resources"]["food"]
            max_f = food_spec["max"]
            self._draw_text(f"Food Level : {tile.resources.get('food', 0.0):.1f} / {max_f:.0f}", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
        else:
            y_offset += 25
            self._draw_text("Hover mouse over grid", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
            y_offset += 16
            self._draw_text("to inspect tile details.", start_x, y_offset, PYGAME_COLOR_MUTED, self.font_body)
            y_offset += 32  # Keep offset alignment stable
            
        # Divider Line
        y_offset += 25
        pygame.draw.line(
            self.screen, PYGAME_COLOR_GRID,
            (start_x, y_offset), (self.win_width - 20, y_offset), 1
        )
        
        # 5. Terrain Color Legend
        y_offset += 15
        self._draw_text("Terrain Color Legend:", start_x, y_offset, PYGAME_COLOR_TEXT, self.font_header)
        
        for tile_type, spec in TILE_SPECS.items():
            y_offset += 20
            color = spec.get("pygame_color", (0, 0, 0))
            
            # Draw color legend box
            box_rect = pygame.Rect(start_x, y_offset + 2, 12, 12)
            pygame.draw.rect(self.screen, color, box_rect)
            pygame.draw.rect(self.screen, PYGAME_COLOR_GRID, box_rect, 1)
            
            # Label
            self._draw_text(tile_type.capitalize(), start_x + 22, y_offset, PYGAME_COLOR_MUTED, self.font_body)

    def run(self) -> None:
        """Main rendering clock and event processing thread."""
        self._init_pygame()
        
        running = True
        try:
            while running:
                # 1. Event Polling
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        
                    elif event.type == self.TICK_EVENT:
                        # Advance simulation step
                        self.current_tick += 1
                        self.last_net_changes = self.world.tick()
                        
                        # Handle maximum ticks limitation
                        if self.max_ticks is not None and self.current_tick >= self.max_ticks:
                            running = False
                        
                # 2. Rendering Cycle
                self.screen.fill(PYGAME_COLOR_BG)
                
                # Fetch world calculations
                stats = self.world.get_stats()
                mouse_pos = pygame.mouse.get_pos()
                
                self._draw_grid()
                self._draw_sidebar(stats, mouse_pos)
                
                pygame.display.flip()
                
                # Regulate frame rate
                self.clock.tick(PYGAME_FPS)
                
        except Exception as err:
            print(f"\nException caught inside Pygame Rendering loop: {err}")
            
        finally:
            pygame.quit()
            print(f"Pygame Visualizer window closed. Stopped at Tick {self.current_tick}.")
