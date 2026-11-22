"""Central configuration loader for Virtual Society (stdlib only).

Reads optional `.env` key=value pairs without third-party dependencies and
exposes typed application settings. No paid API keys are used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_file(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE lines from `.env` into os.environ if not already set."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv_file()


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    # Free local LLM configuration
    llm_mode: str = os.getenv("LLM_MODE", "mock")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model_main: str = os.getenv("OLLAMA_MODEL_MAIN", "llama3.2:3b")
    ollama_model_cheap: str = os.getenv("OLLAMA_MODEL_CHEAP", "llama3.2:1b")
    max_calls_per_minute: int = int(os.getenv("MAX_CALLS_PER_MINUTE", "60"))

    # World & simulation defaults (1 tick = 1 simulated hour)
    world_width: int = int(os.getenv("WORLD_WIDTH", "200"))
    world_height: int = int(os.getenv("WORLD_HEIGHT", "200"))
    world_seed: int = int(os.getenv("WORLD_SEED", "42"))
    founding_humans: int = int(os.getenv("FOUNDING_HUMANS", "12"))
    max_total_agents: int = int(os.getenv("MAX_TOTAL_AGENTS", "300"))
    tick_interval_seconds: float = float(os.getenv("TICK_INTERVAL_SECONDS", "1.0"))
    database_path: str = os.getenv("DATABASE_PATH", "virtual_society.db")

    # Server settings
    server_host: str = os.getenv("SERVER_HOST", "127.0.0.1")
    server_port: int = int(os.getenv("SERVER_PORT", "8000"))


settings = Settings()
