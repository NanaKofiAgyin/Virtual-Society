# Virtual Society

A **100% free** simulated 2D world with 10 AI humans and rule-based wildlife (`deer`, `rabbit`, `wolf`, `bird`). No paid APIs and no API keys are required. The core simulation (`world/`, `agents/`, `llm/`, `simulation/`) uses only the Python standard library; FastAPI + Uvicorn serve the live HTML5 Canvas viewer and SQLite stores snapshots and events.

## How to Run

### 1. Setup
```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

### 2. Run the Web Server + Canvas Viewer
```powershell
.venv\Scripts\python main.py
```
Open `http://127.0.0.1:8000` in your browser. Use the sidebar to **Play/Pause**, **Step**, adjust **Speed**, **Save/Load** SQLite snapshots, start a **New World**, and click any villager (in the list or on the canvas) to inspect their needs, daily plan, thoughts, relationships, and memories.

### 3. Run Headless (CLI)
```powershell
.venv\Scripts\python main.py --headless --days 30
.venv\Scripts\python main.py --headless --days 90 --seed 42
```

### 4. Run Tests
```powershell
.venv\Scripts\pytest -v
```

## How Mock Mode Works (Default)

By default, `LLM_MODE=mock` is active and **never touches the network**:
- **Animals** use pure rule-based logic configured in `data/species.json` (flee, hunt at 25% kill rate when hungry, forage, wander, age, starve, breed below `max_pop`).
- **Humans** use a free 7-step rule-based utility brain (`agents/utility.py`) for all routine survival and work (flee wolves, shelter/sleep at night or in storms, eat, share food with hungry neighbors, socialize, and perform village jobs).
- **Speech, 06:00 daily plans, and 23:00 reflections** use lightweight templates shaped by hunger, weather, job, and the day's memories.

## Turning On a Free Local Model (Ollama)

To upgrade human conversations, daily plans, and nightly reflections to a free local LLM:

1. Install **Ollama** from [ollama.com](https://ollama.com).
2. Pull the local model:
   ```powershell
   ollama pull llama3.2:3b
   ```
3. Copy `.env.example` to `.env` and enable Ollama:
   ```env
   LLM_MODE=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL_MAIN=llama3.2:3b
   OLLAMA_MODEL_CHEAP=llama3.2:3b
   MAX_CALLS_PER_MINUTE=60
   ```
4. Start the server (`python main.py`). The header badge will switch to **Brain: Local model (Ollama)**. If Ollama is ever unreachable or slow, the viewer stays responsive via the read cache and `ask()` automatically falls back to templates without crashing.
