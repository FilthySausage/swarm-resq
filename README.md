# 🚁 Swarm-ResQ

### Multi-Agent Autonomous Rescue Swarm with LangChain & MCP

> **Project Type:** AI-Powered Simulation  
> **Stack:** Python, LangChain, FastMCP, Streamlit, Google Gemini  
> **Status:** ✅ Production-Ready

---

## 🎯 Project Overview

**Swarm-ResQ** is a comprehensive autonomous rescue system that demonstrates multi-agent coordination using:

- **LLM-Driven Decision Making**: Google Gemini 1.5 Flash powers Chain-of-Thought reasoning
- **Multi-Agent Coordination**: 3-5 drones coordinate without collisions or conflicts
- **Persistent Memory**: Multi-turn context remembers explored areas, survivor locations, hazards
- **Real-Time Streaming UI**: Live visualization of agent reasoning and mission progress
- **Robust Error Handling**: Graceful degradation for edge cases (low battery, unreachable survivors, timeouts)

### System Architecture

```
┌────────────────────────────────────────────────────┐
│        Streamlit Web Dashboard (ui/app.py)         │
├────────────────────────────────────────────────────┤
│ - Grid visualization (emoji-based)                 │
│ - Real-time agent reasoning display (streaming)    │
│ - Drone fleet status & battery monitoring          │
│ - Mission briefing input & control                 │
└─────────────────────┬────────────────────────────┘
                      │ (async streaming)
┌─────────────────────▼────────────────────────────┐
│  ARIA Agent (orchestrator/agent.py)               │
├────────────────────────────────────────────────────┤
│ - MultiTurnAgent with memory & mission tracking   │
│ - stream_agent() & run_agent() entry points       │
│ - LangChain ReAct loop (Thought → Action)         │
│ - Memory: explored cells, survivors, hazards      │
│ - Mission completion detection                     │
└─────────────────────┬────────────────────────────┘
                      │ (MCP tool calls)
┌─────────────────────▼────────────────────────────┐
│      FastMCP Server (mcp_server/server.py)        │
├────────────────────────────────────────────────────┤
│ Tools exposed:                                     │
│ - move_drone(id, dx, dy)                          │
│ - scan_area(id, radius)                           │
│ - rescue_survivor(id, x, y)                       │
│ - return_to_base(id)                              │
│ - get_swarm_state() / get_drone_state()           │
│ - get_survivor_counts()                           │
└─────────────────────┬────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────┐
│     Environment Simulation (environment/)         │
├────────────────────────────────────────────────────┤
│ Grid (20x20): cells with EMPTY, OBSTACLE,        │
│              SURVIVOR (S), HAZARD (X), DRONE (D) │
│ Swarm: 3 drones with battery, position, cargo    │
└────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Google Gemini API Key (free tier at https://aistudio.google.com/app/apikey)

### Installation

1. **Clone & Setup**
```bash
git clone <repo-url>
cd swarm-resq
python -m venv venv
```

2. **Activate Virtual Environment**

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
venv\Scripts\activate.bat
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure Environment**
```bash
cp .env.example .env
# Edit .env and insert your GOOGLE_API_KEY
```

### Running the System

**Terminal 1 - Start MCP Server:**
```bash
uvicorn mcp_server.server:app --reload --port 8000
# Output: Uvicorn running on http://127.0.0.1:8000
```

**Terminal 2 - Start Streamlit UI:**
```bash
streamlit run ui/app.py
# Output: You can now view your Streamlit app in your browser at http://localhost:8501
```

**Terminal 3 - Launch Mission (Optional CLI Mode):**
```bash
python -m orchestrator.agent
# Or use the Streamlit UI button: "🚀 Launch ARIA"
```

---

## 📁 Project Structure

```
swarm-resq/
├── environment/
│   ├── __init__.py
│   ├── grid.py              # 20x20 grid world, cell types
│   └── drone.py             # Drone state, swarm management, rescue logic
├── mcp_server/
│   ├── __init__.py
│   └── server.py            # FastMCP server exposing 6 tools
├── orchestrator/
│   ├── __init__.py
│   ├── agent.py             # LangChain ReAct agent + multi-turn memory
│   ├── prompts.py           # System & mission prompts
│   ├── memory.py            # ConversationMemoryBuffer + MissionMemory
│   ├── mission.py           # Mission completion tracking & metrics
│   └── error_handler.py     # Error handling, retry logic, validation
├── ui/
│   ├── __init__.py
│   └── app.py               # Streamlit dashboard (live streaming, controls)
├── .env.example             # Environment template (copy to .env)
├── requirements.txt         # Python dependencies
├── README.md                # This file
└── MISSION_LOG_EXAMPLE.md   # Detailed walkthrough of a complete mission
```

---

## 📚 Documentation

This project includes comprehensive documentation for different use cases:

### For MCP Server Setup & Tool Reference
→ **[MCP_SERVER_GUIDE.md](MCP_SERVER_GUIDE.md)**
- Complete tool documentation (all 8 tools)
- Architecture overview
- Testing examples with cURL & Python
- LangChain integration patterns
- Performance considerations
- Troubleshooting guide

### For Production Deployment
→ **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**
- Local development setup
- Docker container deployment
- Kubernetes cluster deployment
- Monitoring & observability
- Scaling strategies
- Security best practices
- Production checklist

### For Testing & Validation
→ **[test_mcp_server.py](test_mcp_server.py)**
- Comprehensive test suite with pytest
- Concurrency tests
- Error handling validation
- LangChain integration tests
- Performance benchmarks

### For Mission Examples & Walkthroughs
→ **[MISSION_LOG_EXAMPLE.md](MISSION_LOG_EXAMPLE.md)**
- Step-by-step mission walkthrough
- Agent reasoning visible at each step
- Rescue operations demonstrated
- Final metrics and completion report

---

## 🤖 How It Works

### 1. **Agent Initialization**
The agent boots with a system prompt defining:
- Mission objectives (explore grid, rescue survivors, manage battery)
- Operational rules (avoid collisions, scan before entering unknowns, battery thresholds)
- Chain-of-Thought protocol (THOUGHT block before every tool call)

### 2. **Multi-Turn Loop**
Each mission cycle:
```
1. Agent calls get_swarm_state() to understand current situation
2. Agent issues THOUGHT block explaining its reasoning
3. Agent calls tools: move_drone, scan_area, rescue_survivor, etc.
4. Results fed back into agent's context
5. Agent generates STATUS REPORT with metrics
6. Turn complete; mission state persists in memory
```

### 3. **Memory Persistence**
- **MissionMemory**: Tracks explored cells, survivor locations, hazards, obstacle map
- **ConversationMemoryBuffer**: Stores last 20 turns of human/AI messages
- **Combined Context**: Sent to LLM each turn to maintain strategic continuity

### 4. **Real-Time Streaming**
- Agent output streamed token-by-token to Streamlit
- UI updates live as agent reasons
- Users see full reasoning chain (THOUGHT → Action → Result)

### 5. **Mission Completion**
Automatically detects when:
- All survivors rescued → COMPLETED_SUCCESS
- All drones inactive (battery 0%) + survivors rescued < total → COMPLETED_FAILURE
- Grid fully explored with no survivors remaining → COMPLETED_FAILURE

---

## 🛠️ Core Components

### Agent (`orchestrator/agent.py`)

#### `MultiTurnAgent` Class
```python
agent = MultiTurnAgent()  # Contains memory + mission tracker
await agent.run_cycle(mcp_client, mission_briefing="...")  # Execute one turn
async for chunk in agent.stream_cycle(...):  # Streaming variant
    print(chunk, end="")  # Real-time token output
```

#### Entry Points
```python
# Non-streaming (wait for full response)
output = await run_agent(mission_briefing="")

# Streaming (real-time token-by-token)
async for chunk in stream_agent(mission_briefing=""):
    ui.append(chunk)  # Update UI with each token
```

### MCP Server (`mcp_server/server.py`)

Exposes 7 tools:
1. `move_drone(drone_id, dx, dy)` - Move ±1 cell
2. `scan_area(drone_id, radius=2)` - Detect nearby objects
3. `rescue_survivor(drone_id, x, y)` - Pick up survivor
4. `return_to_base(drone_id)` - Deliver cargo to (0,0)
5. `get_swarm_state()` - Full grid + drone states
6. `get_drone_state(drone_id)` - Single drone details
7. `get_survivor_counts()` - Rescue progress

### Environment (`environment/`)

**Grid.py:**
```python
Grid(width=20, height=20)
place_survivors(grid, count=5)     # Random placement
place_hazards(grid, count=8)
place_obstacles(grid, count=15)
```

**Drone.py:**
```python
swarm = DroneSwarm(grid)
swarm.add_drone("drone-1", x=0, y=0)
swarm.move_drone("drone-1", dx=1, dy=0)  # → (1,0)
swarm.scan_area("drone-1", radius=2)     # → nearby detections
swarm.rescue_survivor("drone-1", 1, 1)   # → pick up
swarm.return_to_base("drone-1")          # → deliver to (0,0)
```

---

## 📊 Mission Metrics

After each mission, view:
- **Duration**: Total time (simulated)
- **Success Rate**: Survivors rescued / total survivors
- **Drone Status**: Operational count, battery levels
- **Grid Explored**: % of cells visited
- **Total Moves**: Sum of all drone movements

Example output:
```
METRICS:
  duration_seconds: 847.3
  survivors_rescued: 5 / 5 (100%)
  drones_operational: 3 / 3
  grid_explored: 52.1%
  total_moves: 142
```

---

## 🎛️ Configuration

### Environment Variables (`.env`)

```bash
# Required: Google Gemini API Key
GOOGLE_API_KEY=your_api_key_here

# Optional: MCP Server URL (default: http://localhost:8000/mcp)
MCP_SERVER_URL=http://localhost:8000/mcp
```

### Agent Parameters (`orchestrator/agent.py`)

```python
# LLM model
model="gemini-1.5-flash"  # Or use "gemini-pro" for higher quality
temperature=0  # Deterministic decisions

# Agent loop parameters
max_iterations=30  # Max ReAct loops per cycle
max_message_pairs=20  # Memory size (conversation buffer)

# Timeouts
timeout_seconds=30.0  # Max wait for LLM response
```

---

## 🐛 Error Handling

The system gracefully handles:

1. **Battery Emergencies**
   - If drone battery < 20% → Immediate return-to-base order

2. **Unreachable Survivors**
   - Detector: Hazard walls block access
   - Action: Log & skip, continue with reachable targets

3. **LLM Timeouts**
   - Exponential backoff retry (1s, 2s, 4s)
   - Max 3 attempts before mission abort

4. **Collision Avoidance**
   - Validator prevents two drones in same cell
   - Reassigns movements to safe alternative

5. **Invalid Tool Calls**
   - Catches malformed tool arguments
   - Replay with corrected parameters

---

## 📖 Example Mission

See **[MISSION_LOG_EXAMPLE.md](MISSION_LOG_EXAMPLE.md)** for a complete step-by-step walkthrough:
- Initial deployment
- Survivor detection
- Rescue operations
- Return-to-base maneuvers
- Mission completion report

---

## 🔬 Advanced Usage

### Custom Mission Briefing

**Via CLI:**
```bash
python -m orchestrator.agent
# (when prompted, add special instructions)
```

**Via UI:**
1. Open Streamlit dashboard
2. Enter briefing in sidebar textbox
3. Click "🚀 Launch ARIA"

Example briefings:
- `"Prioritize high-battery drones for distant sectors"`
- `"Skip hazard zones and focus on accessible survivors"`
- `"Maximize grid coverage even if rescue takes longer"`

### Multi-Turn Missions

Currently supports up to 20 conversation turns. Each turn:
- Agent remembers all prior actions
- Survivors found in turn 1 are still remembered in turn 15
- Hazard map continuously updated as new cells explored

---

## 🚀 Performance Optimization

### Prompt Engineering
- Chain-of-Thought forces deliberate reasoning
- Status reports kept concise (no token waste)
- Constraints listed explicitly for faster compliance

### Memory Management
```python
# Prevent bloat: only keep last 20 turns
ConversationMemoryBuffer(max_message_pairs=20)

# Batch tool calls when possible
# e.g., move 3 drones in parallel instead of sequential
```

### Drone Routing
```python
# Current: Greedy movement (move toward goal 1 cell at a time)
# Future: A* pathfinding for optimal routes
#         Collaborative swarm tactics
```

---

## 🛡️ Security Considerations

1. **API Key Protection**
   - Store in `.env` (never commit to git)
   - `.gitignore` contains `.env` entry

2. **Input Validation**
   - MCP tools validate all drone movements
   - Coordinates checked for bounds
   - Battery values clamped [0-100]

3. **LLM Safety**
   - `temperature=0` ensures deterministic, predictable behavior
   - No creative/risky actions
   - System prompt constraints agent to safe domain

---

## 📝 Development Notes

### Adding New Tools
1. Implement logic in `environment/` (e.g., `drone.py`)
2. Wrap in FastMCP decorator in `mcp_server/server.py`
3. Reference in agent prompt (`orchestrator/agent.py`)

### Extending Environment
- Add new cell types in `environment/grid.py`
- Add drone capabilities in `environment/drone.py`
- Update system prompt to explain new behaviors

### Testing Agent
```bash
# Test without Streamlit:
python -m orchestrator.agent

# Test MCP server directly:
# (curl or Python requests to localhost:8000)
```

---

## 📋 Deliverables Checklist

✅ **1. The Orchestrator** - Functional AI agent managing 3-5 drones
- Multi-turn memory
- Chain-of-Thought reasoning
- Mission completion detection
-Streaming output support

✅ **2. MCP Server Implementation** - Exposes 7 drone tools
- move_drone, scan_area, rescue_survivor, return_to_base
- get_swarm_state, get_drone_state, get_survivor_counts

✅ **3. Mission Log** - Complete demonstration
- Step-by-step reasoning visible
- Real-time UI streaming
- Success metrics & completion report

---

## 🤝 Contributing

Refer to the `TODO` comments in each file for planned enhancements:
- **agent.py**: Multi-turn ConversationBufferMemory
- **ui/app.py**: Plotly heatmap visualization, progress bars
- **environment/grid.py**: Procedural map generation

---

## 📄 License

[Your License Here]

---

## 📞 Support

For issues or questions:
1. Check `MISSION_LOG_EXAMPLE.md` for detailed workflow
2. Review `.env.example` for configuration
3. Ensure MCP server is running (`uvicorn` command)
4. Check that Streamlit can import orchestrator module
venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Set Up Environment Variables
Create a `.env` file in the project root (it is gitignored — never commit it):
```
OPENAI_API_KEY=your_openai_api_key_here
```

---

## 🚀 Running the Application

### Start the MCP Server
```bash
# TODO (Member 2): Fill in the correct uvicorn command
uvicorn mcp_server.server:app --reload --port 8000
```

### Start the Streamlit Dashboard
```bash
# TODO (Member 4): Fill in the correct streamlit command
streamlit run ui/app.py
```

---

## 👥 Team Roles & Workspaces

> ⚠️ **To avoid merge conflicts, each member works STRICTLY in their assigned directory.**

| Member | Role | Workspace | Key Responsibilities |
|--------|------|-----------|----------------------|
| **Member 1** | Agent / AI | `/orchestrator` | LangChain agent logic, system prompts, tool-calling strategy, decision loop |
| **Member 2** | MCP / API | `/mcp_server` | FastMCP server setup, drone tool definitions (`move`, `scan`, `rescue`), API endpoints |
| **Member 3** | Simulation | `/environment` | 2D grid world, drone state management, survivor/hazard placement, physics rules |
| **Member 4** | UI / Integration | `/ui` | Streamlit dashboard, grid visualization, real-time state rendering, integration glue |

### Shared Files (Coordinate before editing!)
- `requirements.txt` — notify the team before adding packages
- `README.md` — anyone can update
- Root-level config files (`.env`, `.gitignore`)

---

## 📁 Project Structure

```
swarm-resq/
├── environment/            # Member 3 — Simulation engine
│   ├── __init__.py
│   ├── grid.py             # 2D grid world definition
│   └── drone.py            # Drone state & movement logic
│
├── mcp_server/             # Member 2 — MCP tool server
│   ├── __init__.py
│   └── server.py           # FastMCP server & tool definitions
│
├── orchestrator/           # Member 1 — AI Command Agent
│   ├── __init__.py
│   ├── agent.py            # LangChain agent definition
│   └── prompts.py          # System & task prompts
│
├── ui/                     # Member 4 — Streamlit dashboard
│   ├── __init__.py
│   └── app.py              # Main Streamlit app
│
├── .env                    # !! NEVER COMMIT !! Local secrets
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🔗 Key Technologies

| Technology | Purpose |
|------------|---------|
| [FastMCP](https://github.com/jlowin/fastmcp) | MCP server framework exposing drone tools |
| [LangChain](https://python.langchain.com/) | AI agent orchestration framework |
| [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) | Bridges LangChain agents with MCP tools |
| [Streamlit](https://streamlit.io/) | Real-time simulation dashboard |
| [FastAPI](https://fastapi.tiangolo.com/) / [Uvicorn](https://www.uvicorn.org/) | HTTP layer for the MCP server |

---

## 📋 Git Workflow

```bash
# Always pull before starting work
git pull origin main

# Create a feature branch for your task
git checkout -b feature/<your-name>/<short-description>

# Stage, commit, and push
git add .
git commit -m "feat(environment): add grid boundary detection"
git push origin feature/<your-name>/<short-description>

# Open a Pull Request — get at least 1 review before merging to main
```

**Commit message format:** `type(scope): description`
- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation only
- `refactor` — code restructure

---

*Built with ☕ and urgency at Varsity Hack 2026.*
