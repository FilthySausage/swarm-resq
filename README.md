# 🚁 Swarm-ResQ
### Decentralized Swarm Intelligence via the Model Context Protocol (MCP)

> **Hackathon:** Varsity Hack 2026 | **Deadline:** 8 days | **Team Size:** 4

---

## 📖 Project Overview

**Swarm-ResQ** is a simulated "First Responder of the Future" system. An AI Command Agent — powered by LangChain — manages a swarm of rescue drones operating on a 2D grid environment. The agent interacts with the drones exclusively through a **FastMCP server**, which exposes drone actions (move, scan, rescue) as structured tools. A live **Streamlit dashboard** visualizes the simulation in real-time.

```
┌─────────────────────────────────────────────────────┐
│               Streamlit Dashboard (UI)              │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│         LangChain AI Command Agent (Orchestrator)   │
└──────────────────────┬──────────────────────────────┘
                       │  MCP Tool Calls
┌──────────────────────▼──────────────────────────────┐
│              FastMCP Server (mcp_server)             │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│         2D Grid Simulation & Drone Logic (env)       │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ Local Setup Instructions

Follow these steps exactly to get your local environment running.

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd swarm-resq
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
```

### 3. Activate the Virtual Environment

**Windows (CMD):**
```cmd
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
