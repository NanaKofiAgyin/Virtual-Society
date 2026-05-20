# Virtual Society

> A persistent, modular, and self-contained 2D grid world simulation engine with dynamic ecological dynamics, cellular automata spreading, and utility-driven autonomous agents.

[![Build Status](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Virtual Society** is a persistent simulation system designed in pure Python. It features a fully decoupled architecture where a dynamic environmental simulation and a utility-based autonomous agent population run in a multi-pass cellular-automata cycle, with an optional real-time visual rendering layer powered by Pygame.

---

## 🚀 Key Architectural Features

The project is structured around clean modular boundaries and strict decoupling:

```
Virtual-Society/
│
├── config.py                 # Central ecological, agent, and visual configurations
├── main.py                   # Entry point routing to CLI or Pygame rendering modes
│
├── engine/
│   ├── tile.py               # Cell properties, resource bounds, and environment pressures
│   ├── world.py              # Grid coordinates, Moore neighborhood scans, and agent ticks
│   ├── agent.py              # Independent utility-based decision loop
│   └── pygame_renderer.py    # Decoupled visualization layer with dashboard & inspector
│
└── tests/
    ├── test_tile.py          # Unit tests for tiles, transitions, and pressures
    ├── test_world.py         # Unit tests for Moore neighbors and tick propagation
    └── test_agent.py         # Unit tests for agent metabolism, eating, and reproduction
```

---

## 🌲 Core Simulation Mechanics

### Phase 1: Spatial Grid World
* **Procedural Weighted Generation**: Generates a 2D grid (default `20x20`) using weighted probabilities: **Grass** (50%), **Forest** (20%), **Water** (20%), and **Mountain** (10%).
* **Cell Attributes**: Cells manage their specific walking states, representation symbols, current resource levels (wood, food), and baseline growth.

### Phase 2: World Dynamics & Ecological Pressures
* **Moore Neighborhood Spreads**: 
  - *Forest Spreading*: Forests spread into adjacent Grass tiles based on adjacent forest density.
  - *Water Expansion*: Water slightly floods adjacent Grass tiles.
  - *Erosion*: Grass erodes adjacent Mountain tiles, gradually flattening them.
* **Two-Pass cellular updates**: Inside the world tick, Phase 1 gathers spatial influences globally, and Phase 2 executes terrain transitions simultaneously, avoiding update-order sweeping biases.
* **Environmental Pressures**:
  - *Overcrowding Limit*: If a tile is surrounded by $\ge 6$ similar tiles, its growth/replenishment rate is halved (50% multiplier).
  - *Isolation Decay*: If a tile has $\le 1$ similar neighbors, its resources decay by `-0.5` units per tick.
  - *Starvation Reversions*: Dry forests (0 wood) revert to Grass; dry isolated water bodies turn back to Grass.

### Phase 3: Autonomous Agent System
* **Vision & Sensing**: Agents sense their local 5x5 area (a 2-tile vision radius) looking for walkable cells.
* **Utility-Based Autonomy**: Agents independently choose actions (EAT, REST, REPRODUCE, MOVE) by maximizing dynamic utility scores:
  - **EAT**: Utility peaks when the agent is highly hungry and food is available on the current tile.
  - **REST**: Utility peaks at low-to-medium energy when food is scarce, allowing agents to conserve energy.
  - **REPRODUCE**: Utility triggers only when energy is abundant ($\ge 80$).
  - **MOVE**: Scoring evaluates distance penalties against food attraction on neighboring tiles, drawing agents toward fertile zones.
* **Energy Conservation Reproduction**: When reproducing, an agent splits its current energy exactly in half: the parent keeps `parent_energy / 2` and spawns a newborn child starting with `parent_energy / 2`. This keeps energy conservation realistic and prevents population explosions.
* **Mortality**: Metabolic loss reduces energy every tick; if an agent's energy drops to $\le 0$, it starves and is cleanly removed from the simulation.

---

## 🎨 Graphic Visualization & Interface

* **Resource Brightness Shading**: Cell visual brightness dynamically interpolates between **`40%` (fully depleted)** and **`100%` (pristine/rich)** based on current resource levels. Forests and waterways visibly pulse and darken as agents consume their resources.
* **Crimson Agent Overlay**: Active agents are rendered as crimson circles with distinct borders.
* **Dashboard Panel**: Displays real-time simulation statistics, active population counts, and global resource pools with net tick gains.
* **Layout-Stable Hover Inspector**: Hovering coordinates highlights detailed tile resource metrics and agent energies. The panel dynamically pads visual heights to prevent legend elements from jumping, keeping the interface completely static.

---

## ⚙️ Installation & Running

### 1. Set Up Environment
Create and activate a virtual environment, then install the Pygame dependency:
```bash
# Initialize Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install pygame
```

### 2. Launch Simulation Modes

#### 🎮 Graphic Pygame Visualizer (Default)
Runs the live visualization loop. You can hover your mouse to inspect tiles and track population changes:
```bash
# Run visualizer persistently
python main.py --mode pygame

# Run visualizer with customized tick limits and speeds
python main.py --mode pygame --ticks 300 --delay 0.05
```

#### 📟 Retro CLI Mode
Runs a backwards-compatible terminal ANSI-colored visual visualizer:
```bash
python main.py --mode cli --ticks 100 --delay 0.1
```

---

## 🧪 Running Automated Tests

A robust suite of **21 unit tests** covers tile dynamics, Moore neighbors, world tick propagations, metabolic losses, reproduction splits, search logic, and starvation mortalities:
```bash
.venv/bin/python -m unittest discover -s tests
```
* **Expected Result**: `Ran 21 tests... OK`
