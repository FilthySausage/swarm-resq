# 📋 Swarm-ResQ — Master To-Do Checklist
> **Hackathon:** Varsity Hack 2026 | **Deadline:** TOMORROW
> **Solo Sprint Mode** — Herman completing all remaining work

---

## ✅ Phase 1 — Foundation `DONE`

- [x] Git repository initialized, all members onboarded
- [x] `venv` + `requirements.txt` set up
- [x] `.env.example` created, `.env` configured with `GOOGLE_API_KEY`
- [x] `environment/grid.py` — `Grid`, `CellType`, `place_survivors/hazards/obstacles`, `to_dict()` ✅
- [x] `environment/drone.py` — `Drone`, `DroneSwarm`, `move_drone`, `scan_area`, `rescue_survivor`, `return_to_base`, `get_survivor_count` ✅

---

## ✅ Phase 2 — Core Systems `DONE`

- [x] `mcp_server/server.py` — `SimulationEngine` singleton with async lock ✅
- [x] All 8 MCP tools registered: `initialize_mission`, `get_swarm_state`, `move_drone`, `scan_area`, `rescue_survivor`, `return_to_base`, `get_survivor_counts`, `get_drone_state`, `reset_mission` ✅
- [x] REST endpoints mirrored at `/tools/*` for direct HTTP access ✅
- [x] `orchestrator/agent.py` — `MultiTurnAgent`, `run_cycle`, `stream_cycle`, REST tool calls via `httpx` ✅
- [x] `orchestrator/prompts.py` — `SYSTEM_PROMPT`, `MISSION_START_PROMPT`, `MISSION_STATUS_PROMPT` ✅
- [x] `orchestrator/memory.py` — `MissionMemory` + `ConversationMemoryBuffer` ✅
- [x] `orchestrator/mission.py` — `MissionMonitor` with completion detection ✅
- [x] `orchestrator/error_handler.py` — retry logic, battery/collision handlers ✅
- [x] `ui/app.py` — Streamlit dashboard with Plotly map, drone table, sidebar controls ✅
- [x] `ui/environment_manager.py` — local simulation manager ✅

---

## 🚨 TODAY — Critical Fixes (Do These First)

### 🔴 Fix 1 — `requirements.txt` missing packages
- [x] Add `httpx` and `numpy` to `requirements.txt` ✅

### 🔴 Fix 2 — `stream_cycle` bug in `orchestrator/agent.py`
- [x] Rewrote agent.py to use native LangChain `bind_tools` tool-calling ✅
- [x] Fixed streaming: now passes full `messages` list to `llm.astream()` ✅
- [x] Tool calls parsed from streamed chunks, not fragile regex ✅
- [x] `run_cycle` and `stream_cycle` both use same tool execution path ✅

### 🔴 Fix 3 — UI disconnected from MCP server (state split)
- [x] `ui/app.py` fully rewritten — now polls MCP server via REST for all state ✅
- [x] `fetch_state()` calls `GET /tools/get_swarm_state` ✅
- [x] "Initialize Environment" calls `POST /tools/initialize_mission` ✅
- [x] "Launch ARIA" calls `orchestrator.agent.stream_agent()` ✅
- [x] Server status indicator added to sidebar ✅
- [x] Battery progress bars + survivor metrics added ✅
- [x] Mission complete banner + balloons added ✅

### 🔴 Fix 4 — Drone ID mismatch
- [x] `ui/environment_manager.py` updated: `Drone-{i+1}` → `drone-{i+1}` ✅

---

## 🟡 TODAY — Integration Tasks (Do After Fixes)

### Step 1 — Verify MCP server boots and tools work
- [ ] Run: `uvicorn mcp_server.server:app --reload --port 8000`
- [ ] Test: `curl http://localhost:8000/health` → should return `{"status": "healthy"}`
- [ ] Test: `curl http://localhost:8000/tools/get_swarm_state` → should return grid + drones JSON
- [ ] Test: `curl -X POST "http://localhost:8000/tools/move_drone?drone_id=drone-1&dx=1&dy=0"` → should return success

### Step 2 — Verify agent connects to MCP server
- [ ] Run: `python -m orchestrator.agent` (with MCP server running in another terminal)
- [ ] Confirm agent calls `get_swarm_state` on first turn
- [ ] Confirm `THOUGHT:` blocks appear in output
- [ ] Confirm agent issues `move_drone` / `scan_area` tool calls
- [ ] Confirm agent stops when all survivors rescued

### Step 3 — Wire UI to use agent + MCP server
- [ ] In `ui/app.py`, replace `run_stream_agent()` body to call `stream_agent()` from `orchestrator.agent`
- [ ] In `fetch_state()`, poll `GET /tools/get_swarm_state` via `httpx` or `requests`
- [ ] Test: launch Streamlit, click "Initialize Environment" → calls `POST /tools/initialize_mission`
- [ ] Test: click "Launch ARIA" → agent streams reasoning into mission log panel
- [ ] Test: grid map updates as drones move

### Step 4 — End-to-end demo run
- [ ] Run full mission: 3 drones, 5 survivors, 20×20 grid
- [ ] Confirm `THOUGHT:` blocks visible in Streamlit log
- [ ] Confirm drones return to base when battery < 20%
- [ ] Confirm "Mission Complete" state when all survivors rescued
- [ ] Screenshot or screen-record for submission

---

## 🟢 TODAY — Polish (Do If Time Allows)

- [ ] Add `httpx` import guard in `ui/app.py` with fallback error message if MCP server is down
- [ ] Add "Mission Complete 🎉" banner in Streamlit when `survivors_rescued == total_survivors`
- [ ] Add per-drone battery progress bars in sidebar
- [ ] Increase `max_iterations` in `agent.py` to 20 if agent times out before completing mission
- [ ] Add `initialize_mission` call in UI "Initialize Environment" button (currently only calls local `env_manager`)

---

## 🔗 Current Interface Contract (Actual — as implemented)

| Tool / Endpoint | Location | Signature |
|---|---|---|
| `move_drone` | `mcp_server/server.py` | `move_drone(drone_id: str, dx: int, dy: int) -> dict` |
| `scan_area` | `mcp_server/server.py` | `scan_area(drone_id: str, radius: int = 2) -> dict` |
| `rescue_survivor` | `mcp_server/server.py` | `rescue_survivor(drone_id: str, target_x: int, target_y: int) -> dict` |
| `return_to_base` | `mcp_server/server.py` | `return_to_base(drone_id: str) -> dict` |
| `get_swarm_state` | `mcp_server/server.py` | `get_swarm_state() -> dict` |
| `get_survivor_counts` | `mcp_server/server.py` | `get_survivor_counts() -> dict` |
| `initialize_mission` | `mcp_server/server.py` | `initialize_mission(width, height, drone_count, survivor_count) -> dict` |
| `run_agent(briefing)` | `orchestrator/agent.py` | `async def run_agent(mission_briefing: str) -> str` |
| `stream_agent(briefing)` | `orchestrator/agent.py` | `async def stream_agent(...) -> AsyncGenerator[str, None]` |
| `Grid.to_dict()` | `environment/grid.py` | `-> dict` with `width`, `height`, `cells[][]` |

---

## 🏁 Minimum Viable Demo Checklist (Submission Requirements)

- [ ] **Deliverable 1 — The Orchestrator**: Agent manages 3+ drones, issues tool calls, shows Chain-of-Thought `THOUGHT:` blocks
- [ ] **Deliverable 2 — MCP Server**: Server running, all tools callable, agent communicates exclusively via MCP/REST (no hardcoded moves)
- [ ] **Deliverable 3 — Mission Log**: Streamlit UI shows step-by-step agent reasoning + successful rescue completion

---

## 📋 Execution Order for Today

```
1. Fix requirements.txt          (~2 min)
2. Fix stream_cycle bug           (~5 min)
3. Test MCP server standalone     (~10 min)
4. Test agent standalone          (~15 min)
5. Wire UI → agent → MCP          (~1–2 hrs)
6. Full end-to-end demo run       (~30 min)
7. Polish + screenshot            (~30 min)
```

**Total estimated time: ~3–4 hours**
