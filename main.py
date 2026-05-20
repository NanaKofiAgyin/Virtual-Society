# main.py

"""
Main entry point for the Virtual Society Grid-Based World Simulation Engine.
Parses CLI parameters, initializes the simulation structures, and starts the loop.
"""

import argparse
from config import DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_TICK_DELAY
from engine.world import World
from engine.simulation import Simulation
from engine.pygame_renderer import PygameRenderer

def main() -> None:
    """
    Parses command-line arguments, instantiates a world of designated dimensions,
    and launches the persistent simulation execution loop in Pygame or CLI mode.
    """
    parser = argparse.ArgumentParser(
        description="Virtual Society - Grid-Based World Simulation Engine Foundation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "-W", "--width",
        type=int,
        default=DEFAULT_WIDTH,
        help="Width of the simulated grid (columns)"
    )
    
    parser.add_argument(
        "-H", "--height",
        type=int,
        default=DEFAULT_HEIGHT,
        help="Height of the simulated grid (rows)"
    )
    
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=DEFAULT_TICK_DELAY,
        help="Tick update delay in seconds"
    )
    
    parser.add_argument(
        "-t", "--ticks",
        type=int,
        default=None,
        help="Maximum tick limit to execute. Omit to run continuously in a persistent loop"
    )
    
    parser.add_argument(
        "-m", "--mode",
        type=str,
        choices=["cli", "pygame"],
        default="pygame",
        help="Visualization mode (pygame GUI or CLI terminal visualizer)"
    )
    
    args = parser.parse_args()
    
    # Boundary checks for CLI inputs
    if args.width <= 0 or args.height <= 0:
        parser.error("Grid width and height must be positive, non-zero integers.")
    if args.delay < 0.0:
        parser.error("Tick update delay must be a non-negative float.")
    if args.ticks is not None and args.ticks <= 0:
        parser.error("Ticks limit must be a positive integer.")
        
    print("Initializing World Grid...")
    # Initialize World
    world = World(width=args.width, height=args.height)
    
    if args.mode == "pygame":
        print("Launching Pygame Visualizer...")
        # Start Pygame visualizer
        renderer = PygameRenderer(world=world, tick_delay=args.delay, max_ticks=args.ticks)
        renderer.run()
    else:
        print("Setting up CLI Simulation parameters...")
        # Initialize and configure the Simulation runner
        sim = Simulation(world=world, tick_delay=args.delay, max_ticks=args.ticks)
        print("Launching CLI Engine...")
        sim.run()

if __name__ == "__main__":
    main()
