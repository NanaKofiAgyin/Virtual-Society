"""FastAPI server for Virtual Society with background simulation thread and read cache."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from simulation.engine import Simulation
from simulation.lod import TimeScale
from simulation.storage import Storage

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


class ControlRequest(BaseModel):
    running: bool | None = None
    speed: float | None = None


class ResetRequest(BaseModel):
    seed: int | None = None


class FastForwardRequest(BaseModel):
    days: int = 7


class SimulationRunner:
    """Runs `Simulation` in a background thread and caches snapshots for lock-free reads."""

    def __init__(
        self, seed: int = settings.world_seed, width: int = settings.world_width,
        height: int = settings.world_height, db_path: str | Path = settings.database_path,
    ) -> None:
        self.width, self.height = width, height
        self.storage = Storage(db_path)
        self.sim = Simulation(seed=seed, width=width, height=height, storage=self.storage)
        self.lock, self._cache_lock = threading.Lock(), threading.Lock()
        self.running, self.speed = False, 1.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._map_cache: dict[str, Any] = {}
        self._layers_cache: dict[str, Any] = {}
        self._state_cache: dict[str, Any] = {}
        self._agents_cache: dict[str, dict[str, Any]] = {}
        self._events_cache: list[dict[str, Any]] = []
        self._history_cache: dict[str, Any] = {}
        self._refresh_cache()

    def _refresh_cache(self) -> None:
        """Build fresh read-only dicts from `self.sim` (called while holding `self.lock`)."""
        w = self.sim.world
        map_data = w.to_compact_dict()
        layers_data = {
            "width": w.width, "height": w.height,
            "elevation": np.clip(w.elevation * 255, 0, 255).astype(np.uint8).ravel().tolist(),
            "temperature": np.clip(w.temperature * 255, 0, 255).astype(np.uint8).ravel().tolist(),
            "ocean_depth": np.clip(w.ocean_depth * 255, 0, 255).astype(np.uint8).ravel().tolist(),
        }
        humans = [h.detail() for h in self.sim.humans]
        animals = [a.to_dict() for a in self.sim.animals]
        agents = {h["id"]: h for h in humans}
        agents.update({a["id"]: a for a in animals})
        names_by_id = {h.id: h.name for h in self.sim.humans}
        minds = {h.id: self.sim.dialogue.ensure_mind(h, w).to_dict(names_by_id) for h in self.sim.humans if h.alive}
        events = list(self.sim.events)[-50:]
        state_data = {
            "seed": self.sim.seed, "running": self.running, "speed": self.speed,
            "environment": self.sim.environment.to_dict(),
            "humans": humans, "animals": animals, "counts": self.sim.population_counts(),
            "society": self.sim.stats.society, "minds": minds, "tech_tree": self.sim.progress.to_tech_tree_dict(),
            "conversations": [c.to_dict() for c in list(self.sim.dialogue.logs)[-50:]],
            "glossaries": self.sim.dialogue.build_glossaries(self.sim.humans),
            "llm_mode": self.sim.llm_client.mode, "llm_usage": self.sim.llm_client.usage.summary(),
        }
        history_data = {
            **self.sim.history.to_dict(self.sim.environment.year),
            "phylo_tree": [n.to_dict() for n in self.sim.evolution.tree.values()],
        }
        with self._cache_lock:
            self._map_cache, self._layers_cache = map_data, layers_data
            self._state_cache, self._agents_cache = state_data, agents
            self._events_cache, self._history_cache = events, history_data

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="sim-loop")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.storage.close()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if self.running:
                with self.lock:
                    self.sim.tick()
                    self._refresh_cache()
                self._stop_event.wait(max(0.05, 1.0 / max(0.2, self.speed)))
            else:
                self._stop_event.wait(0.1)

    def step_once(self) -> dict[str, Any]:
        with self.lock:
            result = self.sim.tick()
            self._refresh_cache()
            return result

    def fast_forward(self, days: int = 7) -> dict[str, Any]:
        """Advance `days` rapidly using FAST (1 day/tick) scale, then restore NORMAL."""
        with self.lock:
            prev = self.sim.lod.time_scale
            self.sim.lod.time_scale = TimeScale.FAST
            try:
                for _ in range(max(1, min(365, days))):
                    self.sim.tick()
            finally:
                self.sim.lod.time_scale = prev
            self._refresh_cache()
            return {"tick": self.sim.environment.tick, "year": self.sim.environment.year, "counts": self.sim.population_counts()}

    def set_control(self, running: bool | None, speed: float | None) -> dict[str, Any]:
        if running is not None:
            self.running = running
        if speed is not None:
            self.speed = max(0.2, min(20.0, float(speed)))
        with self._cache_lock:
            self._state_cache = {**self._state_cache, "running": self.running, "speed": self.speed}
        return {"running": self.running, "speed": self.speed}

    def save(self) -> dict[str, Any]:
        with self.lock:
            return {"snapshot_id": self.storage.save_snapshot(self.sim), "tick": self.sim.environment.tick}

    def load(self) -> dict[str, Any] | None:
        with self.lock:
            loaded = self.storage.load_latest_snapshot()
            if loaded is None:
                return None
            self.sim = loaded
            self._refresh_cache()
            return {"tick": self.sim.environment.tick, "counts": self.sim.population_counts()}

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        with self.lock:
            self.running = False
            new_seed = self.sim.seed if seed is None else seed
            self.sim = Simulation(seed=new_seed, width=self.width, height=self.height, storage=self.storage)
            self._refresh_cache()
            return {"seed": self.sim.seed, "tick": self.sim.environment.tick}

    def get_map(self) -> dict[str, Any]:
        with self._cache_lock:
            return self._map_cache

    def get_layers(self) -> dict[str, Any]:
        with self._cache_lock:
            return self._layers_cache

    def get_state(self) -> dict[str, Any]:
        with self._cache_lock:
            return self._state_cache

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._cache_lock:
            return self._agents_cache.get(agent_id)

    def get_events(self) -> list[dict[str, Any]]:
        with self._cache_lock:
            return self._events_cache

    def get_history(self) -> dict[str, Any]:
        with self._cache_lock:
            return self._history_cache


def create_app(
    seed: int = settings.world_seed, width: int = settings.world_width,
    height: int = settings.world_height, db_path: str | Path = settings.database_path,
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

    api = FastAPI(title="Virtual Society", version="0.2.0", lifespan=lifespan)
    api.state.runner = runner
    if STATIC_DIR.is_dir():
        api.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if ASSETS_DIR.is_dir():
        api.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

    api.add_api_route("/health", lambda: {"status": "ok"}, methods=["GET"])
    api.add_api_route("/", lambda: FileResponse(STATIC_DIR / "index.html"), methods=["GET"])
    api.add_api_route("/api/map", runner.get_map, methods=["GET"])
    api.add_api_route("/api/layers", runner.get_layers, methods=["GET"])
    api.add_api_route("/api/state", runner.get_state, methods=["GET"])
    api.add_api_route("/api/events", lambda: {"events": runner.get_events()}, methods=["GET"])
    api.add_api_route("/api/history", runner.get_history, methods=["GET"])
    api.add_api_route("/api/step", runner.step_once, methods=["POST"])
    api.add_api_route("/api/save", runner.save, methods=["POST"])

    @api.get("/api/agent/{agent_id}")
    def api_agent(agent_id: str) -> dict[str, Any]:
        agent = runner.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        return agent

    @api.post("/api/control")
    def api_control(body: ControlRequest) -> dict[str, Any]: return runner.set_control(running=body.running, speed=body.speed)

    @api.post("/api/fast_forward")
    def api_fast_forward(body: FastForwardRequest | None = None) -> dict[str, Any]: return runner.fast_forward(days=body.days if body else 7)

    @api.post("/api/load")
    def api_load() -> dict[str, Any]:
        restored = runner.load()
        if restored is None:
            raise HTTPException(status_code=404, detail="No saved snapshot found")
        return restored

    @api.post("/api/reset")
    def api_reset(body: ResetRequest | None = None) -> dict[str, Any]: return runner.reset(seed=body.seed if body else None)

    return api


app = create_app()
