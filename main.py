"""Application entry point for Virtual Society.

Usage:
    python main.py                        # Start FastAPI server + viewer
    python main.py --headless --days 30   # Run headless simulation and print summary
"""

from __future__ import annotations

import argparse

import uvicorn

from config import settings
from simulation import Simulation


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for server or headless simulation mode."""
    parser = argparse.ArgumentParser(description="Virtual Society simulation runner")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run simulation without starting the web server",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of simulated days to run in headless mode (24 ticks/day)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=settings.world_seed,
        help="Random seed for reproducible simulation runs",
    )
    return parser.parse_args()


def main() -> None:
    """Run either the headless simulation or the FastAPI server."""
    args = parse_args()
    if args.headless:
        sim = Simulation(
            seed=args.seed,
            width=settings.world_width,
            height=settings.world_height,
        )
        sim.run(ticks=max(0, args.days) * 24)
        print(sim.summary())
        return

    uvicorn.run(
        "server.app:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
