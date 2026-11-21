"""FastAPI server for Virtual Society with background simulation thread and read cache."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from simulation.engine import Simulation
from simulation.storage import Storage

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ControlRequest(BaseModel):
    """Payload for `POST /api/control`."""

    running: bool | None = None
    speed: float | None = None


class ResetRequest(BaseModel):
    """Optional payload for `POST /api/reset`."""

    seed: int | None = None


class SimulationRunner:
    """Runs `Simulation` in a background thread and caches snapshots for lock-free reads."""

    def __init__(
        self,
        seed: int = settings.world_seed,
        width: int = settings.world_width,
        height: int = settings.world_height,
        db_path: str | Path = settings.database_path,
    ) -> None:
        self.width, self.height = width, height
        self.storage = Storage(db_path)
        self.sim = Simulation(seed=seed, width=width, height=height, storage=self.storage)
        self.lock, self._cache_lock = threading.Lock(), threading.Lock()
        self.running, self.speed = False, 1.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._map_cache: dict[str, Any] = {}
        self._state_cache: dict[str, Any] = {}
        self._agents_cache: dict[str, dict[str, Any]] = {}
        self._events_cache: list[dict[str, Any]] = []
        self._refresh_cache()

    def _refresh_cache(self) -> None:
        """Build fresh read-only dicts from `self.sim` (called while holding `self.lock`)."""
        world = self.sim.world
        map_data = {
            "width": world.width,
            "height": world.height,
            "tiles": [[t.to_dict() for t in row] for row in world.tiles],
        }
        humans = [h.detail() for h in self.sim.humans]
        animals = [a.to_dict() for a in self.sim.animals]
        agents = {h["id"]: h for h in humans}
        agents.update({a["id"]: a for a in animals})
        events = list(self.sim.events)[-50:]
        state_data = {
            "seed": self.sim.seed,
            "running": self.running,
            "speed": self.speed,
            "environment": self.sim.environment.to_dict(),
            "humans": humans,
            "animals": animals,
            "counts": self.sim.population_counts(),
            "llm_mode": self.sim.llm_client.mode,
            "llm_usage": self.sim.llm_client.usage.summary(),
        }
        with self._cache_lock:
            self._map_cache = map_data
            self._state_cache = state_data
            self._agents_cache = agents
            self._events_cache = events

    def start(self) -> None:
        """Start the daemon background loop thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sim-loop")
        self._thread.start()

    def stop(self) -> None:
        """Stop the background thread and close SQLite storage."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.storage.close()

    def _loop(self) -> None:
        """Background loop ticking the simulation while `self.running` is True."""
        while not self._stop_event.is_set():
            if self.running:
                with self.lock:
                    self.sim.tick()
                    self._refresh_cache()
                delay = max(0.05, 1.0 / max(0.2, self.speed))
                self._stop_event.wait(delay)
            else:
                self._stop_event.wait(0.1)

    def step_once(self) -> dict[str, Any]:
        """Advance the simulation by exactly one tick and refresh caches."""
        with self.lock:
            result = self.sim.tick()
            self._refresh_cache()
            return result

    def set_control(self, running: bool | None, speed: float | None) -> dict[str, Any]:
        """Update running state and tick speed without blocking on a running tick."""
        if running is not None:
            self.running = running
        if speed is not None:
            self.speed = max(0.2, min(20.0, float(speed)))
        with self._cache_lock:
            self._state_cache = {**self._state_cache, "running": self.running, "speed": self.speed}
        return {"running": self.running, "speed": self.speed}

    def save(self) -> dict[str, Any]:
        """Persist a full snapshot to SQLite."""
        with self.lock:
            snap_id = self.storage.save_snapshot(self.sim)
            return {"snapshot_id": snap_id, "tick": self.sim.environment.tick}

    def load(self) -> dict[str, Any] | None:
        """Restore the latest snapshot from SQLite and refresh caches."""
        with self.lock:
            loaded = self.storage.load_latest_snapshot()
            if loaded is None:
                return None
            self.sim = loaded
            self._refresh_cache()
            return {"tick": self.sim.environment.tick, "counts": self.sim.population_counts()}

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        """Reset to a fresh Simulation with an optional new seed."""
        with self.lock:
            self.running = False
            new_seed = self.sim.seed if seed is None else seed
            self.sim = Simulation(
                seed=new_seed, width=self.width, height=self.height, storage=self.storage
            )
            self._refresh_cache()
            return {"seed": self.sim.seed, "tick": self.sim.environment.tick}

    def get_map(self) -> dict[str, Any]:
        """Return cached map data without acquiring the simulation lock."""
        with self._cache_lock:
            return self._map_cache

    def get_state(self) -> dict[str, Any]:
        """Return cached simulation state without acquiring the simulation lock."""
        with self._cache_lock:
            return self._state_cache

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Return cached agent details by ID without acquiring the simulation lock."""
        with self._cache_lock:
            return self._agents_cache.get(agent_id)

    def get_events(self) -> list[dict[str, Any]]:
        """Return cached recent events without acquiring the simulation lock."""
        with self._cache_lock:
            return self._events_cache


def create_app(
    seed: int = settings.world_seed,
    width: int = settings.world_width,
    height: int = settings.world_height,
    db_path: str | Path = settings.database_path,
) -> FastAPI:
    """Create a configured FastAPI application bound to its own `SimulationRunner`."""
    runner = SimulationRunner(seed=seed, width=width, height=height, db_path=db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        runner.start()
        try:
            yield
        finally:
            runner.stop()

    api = FastAPI(title="Virtual Society", version="0.1.0", lifespan=lifespan)
    api.state.runner = runner
    if STATIC_DIR.is_dir():
        api.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    api.add_api_route("/health", lambda: {"status": "ok"}, methods=["GET"])
    api.add_api_route("/", lambda: FileResponse(STATIC_DIR / "index.html"), methods=["GET"])
    api.add_api_route("/api/map", runner.get_map, methods=["GET"])
    api.add_api_route("/api/state", runner.get_state, methods=["GET"])
    api.add_api_route("/api/events", lambda: {"events": runner.get_events()}, methods=["GET"])
    api.add_api_route("/api/step", runner.step_once, methods=["POST"])
    api.add_api_route("/api/save", runner.save, methods=["POST"])

    @api.get("/api/agent/{agent_id}")
    def api_agent(agent_id: str) -> dict[str, Any]:
        agent = runner.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        return agent

    @api.post("/api/control")
    def api_control(body: ControlRequest) -> dict[str, Any]:
        return runner.set_control(running=body.running, speed=body.speed)

    @api.post("/api/load")
    def api_load() -> dict[str, Any]:
        restored = runner.load()
        if restored is None:
            raise HTTPException(status_code=404, detail="No saved snapshot found")
        return restored

    @api.post("/api/reset")
    def api_reset(body: ResetRequest | None = None) -> dict[str, Any]:
        return runner.reset(seed=body.seed if body else None)

    return api


app = create_app()
