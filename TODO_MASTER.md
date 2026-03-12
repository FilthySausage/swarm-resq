# 📋 Swarm-ResQ — Master To-Do Checklist
> **Hackathon:** Varsity Hack 2026 | **Deadline:** 8 days from Day 1
> 
> | Handle | Role | Domain |
> |--------|------|--------|
> | **Siewfeng** | Member 1 — Agentic Brain | `/orchestrator` |
> | **Herman** | Member 2 — MCP Engineer | `/mcp_server` |
> | **Kaibin** | Member 3 — Environment Simulator | `/environment` |
> | **Weikang** | Member 4 — UI & Integration Lead | `/ui` |

---

## 🗓️ Phase 1 — Foundation `Days 1–2`

### 🌐 All Members
- [ ] Initialize Git repository and share access with all 4 members
- [ ] Each member clones the repo and creates their local `venv`
  ```cmd
  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements.txt
  ```
- [ ] Each member copies `.env.example` → `.env` and fills in `GOOGLE_API_KEY`
- [ ] Confirm everyone can import packages without errors (`python -c "import langchain"`)

### 🟢 Kaibin (M3 — Environment)
- [ ] Implement `DisasterMap` class in `environment/grid.py`
  - 20×20 grid using a 2D Python array
  - `place_survivors(count)` — randomly seeds survivor coordinates
  - `place_hazards(count)` — randomly seeds hazard coordinates
  - `place_obstacles(count)` — randomly seeds obstacle coordinates
  - `to_dict()` serializer for UI/MCP consumption
- [ ] Implement `Drone` class in `environment/drone.py`
  - Attributes: `drone_id`, `x`, `y`, `battery=100`, `status`, `cargo`
  - `move_to(new_x, new_y)` — deducts battery proportional to Manhattan distance
  - `thermal_scan()` — checks if current cell contains a survivor
  - `get_battery_status()` — returns formatted battery report dict
  - Battery depletes on every move; raise error / flag if battery ≤ 0

---

## 🗓️ Phase 2 — Core Systems `Days 3–4`

### 🔵 Herman (M2 — MCP Server)
- [ ] Verify FastMCP server boots cleanly:
  ```cmd
  uvicorn mcp_server.server:app --reload --port 8000
  ```
- [ ] Replace placeholder `move_drone(dx, dy)` tool with `command_drone_move(drone_id, new_x, new_y)` that calls Kaibin's `move_to()`
- [ ] Replace placeholder `scan_area()` tool with `thermal_scan(drone_id)` that calls Kaibin's `thermal_scan()`
- [ ] Add `get_battery_status(drone_id)` MCP tool wrapping Kaibin's method
- [ ] Add `list_active_drones()` MCP tool — returns all drone IDs + current state (enables real-time tool discovery by the agent)
- [ ] Add `get_grid_state()` MCP tool — returns full serialized grid for the UI
- [ ] Test all tools manually using the MCP Inspector or `curl`

### 🟣 Siewfeng (M1 — Agent)
- [ ] Confirm `orchestrator/agent.py` loads `.env` and `GOOGLE_API_KEY` correctly
- [ ] Test `ChatGoogleGenerativeAI` connection with a simple prompt (no tools)
- [ ] Review and finalize the `SYSTEM_PROMPT` in `orchestrator/agent.py`
  - Must enforce THOUGHT block before every tool call
  - Must include battery threshold logic (< 20% → return to base)
  - Must instruct agent to call `list_active_drones()` first every turn
- [ ] Write `MISSION_START_PROMPT` and `MISSION_STATUS_PROMPT` in `orchestrator/prompts.py`
- [ ] Test `run_agent()` end-to-end with a live MCP server (coordinate with Herman)

### 🟢 Kaibin (M3 — Environment) continued
- [ ] Rename `drone.py` method signatures to match what Herman's MCP tools expect
- [ ] Ensure `DroneSwarm` supports `list_active_drones()` — returns all drone dicts
- [ ] Write unit tests for `move_to()` battery depletion in `environment/tests/`
- [ ] Confirm that a drone with 0% battery cannot move (raises or returns error)

---

## 🗓️ Phase 3 — Integration `Days 5–6`

### 🔵 Herman (M2) + 🟣 Siewfeng (M1) — Joint
- [ ] Run agent → MCP → environment full-loop test end-to-end
- [ ] Verify the agent uses `list_active_drones()` dynamically (not hardcoded IDs)
- [ ] Test commanding 3–5 drones simultaneously in a single agent cycle
- [ ] Verify battery depletion occurs correctly across multi-drone missions
- [ ] Document any tool schema changes in this file + notify Weikang

### 🟡 Weikang (M4 — UI)
- [ ] Scaffold `ui/dashboard.py` (rename from `app.py` to match plan — coordinate with team)
- [ ] Left panel: Drone position plot on a 20×20 grid
  - Use `st.scatter_chart` or Plotly `go.Heatmap`
  - Poll `get_grid_state()` from MCP server every N seconds
- [ ] Right panel: Scrolling mission log text box
  - Capture agent `THOUGHT:` blocks and tool call results
  - Display in `st.text_area` or `st.markdown` with auto-scroll
- [ ] Add sidebar controls: Start Mission, Refresh Rate slider, Mission Briefing input
- [ ] Wire the "Launch ARIA" button to call `orchestrator.agent.run_agent()`
- [ ] Add survivor found / rescued counters at the top of the dashboard

### 🟢 Kaibin (M3) — Support
- [ ] Expose a `reset_simulation(width, height, num_survivors)` function so Weikang can reset the map from the UI button
- [ ] Provide Weikang with sample serialized `grid.to_dict()` output so UI development is unblocked

---

## 🗓️ Phase 4 — Polish & Delivery `Days 7–8`

### 🌐 All Members
- [ ] Run full end-to-end simulation: agent commands 3–5 drones, rescues all survivors, all drones return to base
- [ ] Verify all drones return to base `(0, 0)` before battery hits 0%
- [ ] Confirm `THOUGHT:` reasoning blocks appear in the Streamlit log panel
- [ ] Fix any tool schema mismatches between MCP server and agent expectations

### 🟣 Siewfeng (M1)
- [ ] Wire `stream_agent()` generator into the UI (coordinate with Weikang)
- [ ] Save Mission Log to a timestamped `.txt` / `.md` file after each run
- [ ] Tune `max_iterations` and prompt if agent loops or fails to complete mission
- [ ] Ensure agent handles "all survivors rescued" gracefully and stops

### 🔵 Herman (M2)
- [ ] Harden error handling in all MCP tools (invalid drone ID, out-of-bounds moves, etc.)
- [ ] Add `rescue_survivor(drone_id)` and `return_to_base(drone_id)` tools if not yet done
- [ ] Stress-test server with 5 drones issuing commands simultaneously
- [ ] Write a one-paragraph "MCP Server API Reference" section in `README.md`

### 🟢 Kaibin (M3)
- [ ] Final check: battery math is deterministic and reproducible
- [ ] Ensure `DroneSwarm.get_state()` returns all data Weikang needs for the UI
- [ ] Seed random with a fixed value option for repeatable demo runs

### 🟡 Weikang (M4)
- [ ] Polish the Streamlit UI layout and colour scheme
- [ ] Add a "Mission Complete 🎉" banner when all survivors are rescued
- [ ] Add a drone battery indicator bar per drone in the sidebar
- [ ] Record the final demo video showing:
  1. Dashboard with drones moving on the grid
  2. Visible `THOUGHT:` Chain-of-Thought logs in real time
  3. Mission complete state

---

## 🔗 Cross-Module Interface Contract
> Keep this table updated whenever a function signature changes. Tag the person to notify.

| Tool / Function | Defined by | Consumed by | Current Signature |
|---|---|---|---|
| `move_to(new_x, new_y)` | Kaibin (M3) | Herman (M2) | `Drone.move_to(new_x: int, new_y: int) -> dict` |
| `thermal_scan()` | Kaibin (M3) | Herman (M2) | `Drone.thermal_scan() -> dict` |
| `get_battery_status()` | Kaibin (M3) | Herman (M2) | `Drone.get_battery_status() -> dict` |
| `command_drone_move` | Herman (M2) | Siewfeng (M1) | MCP tool: `drone_id, new_x, new_y` |
| `thermal_scan` | Herman (M2) | Siewfeng (M1) | MCP tool: `drone_id` |
| `list_active_drones` | Herman (M2) | Siewfeng (M1) & Weikang (M4) | MCP tool: no args |
| `get_grid_state` | Herman (M2) | Weikang (M4) | MCP tool: no args |
| `run_agent(briefing)` | Siewfeng (M1) | Weikang (M4) | `async def run_agent(mission_briefing: str) -> str` |
| `stream_agent(briefing)` | Siewfeng (M1) | Weikang (M4) | `async def stream_agent(...) -> AsyncGenerator` |
| `grid.to_dict()` | Kaibin (M3) | Herman (M2) & Weikang (M4) | `Grid.to_dict() -> dict` |

---

## ⚠️ Merge Conflict Rules
1. **Never edit outside your assigned folder** without announcing in the group chat first.
2. The only shared files are `requirements.txt`, `README.md`, and `TODO_MASTER.md` — coordinate before editing.
3. Always `git pull origin main` before starting any work session.
4. Use the branch naming convention: `feat/<your-name>/<short-description>`
