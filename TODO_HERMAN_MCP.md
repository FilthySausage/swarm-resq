# 🔵 Herman's MCP Engineer Checklist
> **Role:** Member 2 — MCP Engineer
> **Domain:** `/mcp_server` (do not touch other folders without coordinating)
> **Server file:** `mcp_server/server.py`
> **Depends on:** Kaibin's `environment/drone.py` and `environment/grid.py`

---

## ✅ How to Run Your Server
```cmd
venv\Scripts\activate
uvicorn mcp_server.server:app --reload --port 8000
```
Test it is live:
```cmd
curl http://localhost:8000/mcp
```

---

## 🗓️ Days 1–2 — Setup & Learn

- [ ] Clone repo, set up `venv`, install dependencies
  ```cmd
  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements.txt
  ```
- [ ] Copy `.env.example` → `.env`, fill in `GOOGLE_API_KEY`
- [ ] Read the [FastMCP quickstart](https://gofastmcp.com/getting-started/welcome) — build the toy `add_numbers(a, b)` example locally to understand the `@mcp.tool()` decorator pattern
- [ ] Confirm the current boilerplate server boots without errors:
  ```cmd
  uvicorn mcp_server.server:app --reload --port 8000
  ```
- [ ] Ping Kaibin to confirm his `Drone` class method signatures (you need `move_to`, `thermal_scan`, `get_battery_status` to be finalised before Day 3)

---

## 🗓️ Days 3–4 — Build the MCP Tools

> All work goes in `mcp_server/server.py`. Import Kaibin's classes at the top.

### 🔧 Tool 1 — `list_active_drones`
**Purpose:** Allows the agent to dynamically discover all drones instead of hardcoding IDs.

- [ ] Implement `list_active_drones() -> dict`
  - Returns all drone IDs and their current state dicts
  - Example return:
    ```json
    {
      "drones": [
        {"drone_id": "drone-1", "x": 0, "y": 0, "battery": 100, "status": "idle"},
        {"drone_id": "drone-2", "x": 19, "y": 0, "battery": 100, "status": "idle"}
      ]
    }
    ```
- [ ] Decorate with `@mcp.tool()` and write a clear docstring (the LLM reads this!)

---

### 🔧 Tool 2 — `command_drone_move`
**Purpose:** Replaces the old `move_drone(dx, dy)` delta approach with an absolute `move_to(new_x, new_y)` call.

- [ ] Implement `command_drone_move(drone_id: str, new_x: int, new_y: int) -> dict`
  - Validates `drone_id` exists — return `{"success": False, "error": "..."}` if not
  - Validates `new_x` and `new_y` are within `0–19`
  - Calls Kaibin's `Drone.move_to(new_x, new_y)`
  - Returns a human-readable confirmation string + updated drone state:
    ```json
    {
      "success": true,
      "message": "Drone drone-1 moved to (5, 7). Battery at 92%.",
      "drone": { ... }
    }
    ```
- [ ] Decorate with `@mcp.tool()` and write a clear docstring

---

### 🔧 Tool 3 — `thermal_scan`
**Purpose:** Lets the agent scan for survivors at a drone's current position.

- [ ] Implement `thermal_scan(drone_id: str) -> dict`
  - Calls Kaibin's `Drone.thermal_scan()`
  - Returns whether a survivor was detected at the current cell
  - Example return:
    ```json
    {
      "success": true,
      "drone_id": "drone-1",
      "position": {"x": 5, "y": 7},
      "survivor_detected": true,
      "survivor_id": "survivor-3"
    }
    ```
- [ ] Decorate with `@mcp.tool()` and write a clear docstring

---

### 🔧 Tool 4 — `get_battery_status`
**Purpose:** Lets the agent check battery before assigning long missions.

- [ ] Implement `get_battery_status(drone_id: str) -> dict`
  - Calls Kaibin's `Drone.get_battery_status()`
  - Returns battery level, status flag (`ok` / `low` / `critical`), and a recommended action
  - Thresholds: `> 50%` = ok, `20–50%` = low, `< 20%` = critical
  - Example return:
    ```json
    {
      "drone_id": "drone-1",
      "battery": 17,
      "status": "critical",
      "recommendation": "Return to base immediately."
    }
    ```
- [ ] Decorate with `@mcp.tool()` and write a clear docstring

---

### 🔧 Tool 5 — `get_grid_state`
**Purpose:** Gives the agent and the UI a full snapshot of the world.

- [ ] Implement `get_grid_state() -> dict`
  - Returns `_grid.to_dict()` — the full serialized 20×20 grid
  - Also embeds a summary: `survivors_remaining`, `survivors_rescued`, `active_drones`
  - Example return:
    ```json
    {
      "grid": { "width": 20, "height": 20, "cells": [ ... ] },
      "summary": {
        "survivors_remaining": 4,
        "survivors_rescued": 1,
        "active_drones": 3
      }
    }
    ```
- [ ] Decorate with `@mcp.tool()` and write a clear docstring

---

### 🔧 Tool 6 — `rescue_survivor` *(Day 4, if time allows)*
**Purpose:** Marks the survivor at the drone's current location as rescued.

- [ ] Implement `rescue_survivor(drone_id: str) -> dict`
  - Only succeeds if `thermal_scan` would return `survivor_detected: true`
  - Sets the cell to `CellType.RESCUED` on the grid
  - Sets `drone.cargo` to the survivor's ID
  - Returns confirmation + updated drone state

---

### 🔧 Tool 7 — `return_to_base` *(Day 4, if time allows)*
**Purpose:** Issues a high-priority return command for low-battery drones.

- [ ] Implement `return_to_base(drone_id: str) -> dict`
  - Sets drone status to `DroneStatus.RETURNING`
  - Pathfinds back to `(0, 0)` — for now a simple step-by-step Manhattan path is fine
  - Returns estimated steps to base and current battery

---

## 🗓️ Days 5–6 — Integration with Agent & UI

- [ ] Run full loop test with Siewfeng: agent calls `list_active_drones()` → picks a drone → calls `command_drone_move()` → calls `thermal_scan()`
- [ ] Verify all tool **docstrings** are clear — the LLM uses them to decide when/how to call each tool
- [ ] Add `reset_simulation(num_survivors: int = 5)` tool so Weikang can reset from the UI:
  - Rebuilds `_grid` and `_swarm` with fresh state
  - Re-seeds survivors and hazards
- [ ] Share a `curl` test snippet with Weikang so he can hit `get_grid_state` independently

---

## 🗓️ Days 7–8 — Harden & Demo

- [ ] Add input validation guards to every tool (bad types, out-of-range coords, unknown IDs)
- [ ] Add consistent error format across all tools:
  ```json
  { "success": false, "error": "Drone 'drone-99' not found.", "tool": "thermal_scan" }
  ```
- [ ] Stress test: have Siewfeng's agent command 5 drones in rapid succession — verify no state corruption
- [ ] Write a **MCP Server API Reference** table in `README.md` listing every tool, its args, and its return shape
- [ ] Confirm server restarts cleanly between demo runs without stale state

---

## 🧱 Current State of `mcp_server/server.py` (Boilerplate to Replace)

| Old Tool | Status | Replace With |
|---|---|---|
| `move_drone(drone_id, dx, dy)` | ⚠️ Delta-based, replace | `command_drone_move(drone_id, new_x, new_y)` |
| `scan_area(drone_id, radius)` | ⚠️ Generic, replace | `thermal_scan(drone_id)` |
| `get_swarm_state()` | ✅ Keep, rename | `get_grid_state()` — add summary block |
| `get_drone_state(drone_id)` | ✅ Keep | `get_battery_status(drone_id)` — merge or keep both |
| *(missing)* | ❌ Add | `list_active_drones()` |
| *(missing)* | ❌ Add | `rescue_survivor(drone_id)` |
| *(missing)* | ❌ Add | `return_to_base(drone_id)` |
| *(missing)* | ❌ Add | `reset_simulation(num_survivors)` |

---

## 📞 Who to Ping for What

| Blocker | Person |
|---|---|
| `Drone.move_to()` signature changed | **Kaibin** |
| `thermal_scan()` returns unexpected format | **Kaibin** |
| Agent can't discover tools / wrong tool name | **Siewfeng** |
| UI not receiving `get_grid_state` correctly | **Weikang** |

---

## 🔖 Useful References
- [FastMCP Docs](https://gofastmcp.com)
- [MCP Tool Docstring Best Practices](https://modelcontextprotocol.io/docs/concepts/tools)
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [uvicorn CLI reference](https://www.uvicorn.org/settings/)
