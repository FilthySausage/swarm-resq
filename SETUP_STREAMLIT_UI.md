# Streamlit UI Setup Guide - Self-Contained Local Simulation

## Quick Start

This guide explains how to run the **Swarm-ResQ Command Center** Streamlit UI with a self-contained local simulation (no external servers required).

### Prerequisites

1. **Python 3.8+** installed
2. **Google API Key** for Gemini LLM (free tier available at https://aistudio.google.com/app/apikey)
3. **Environment configured** with `.env` file

### Installation Steps

#### 1. Create/Update `.env` File

Copy from `.env.example` and add your Google API key:

```bash
cp .env.example .env
```

Then edit `.env`:
```
GOOGLE_API_KEY=your_api_key_here
SERVER_URL=http://127.0.0.1:8000  # Optional, for future MCP server integration
```

#### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Key packages:**
- `streamlit` - UI framework
- `plotly` - Interactive visualizations
- `langchain-google-genai` - Google Gemini integration
- `mcp` - Model Context Protocol SDK
- Plus others from requirements.txt

#### 3. Verify Installation

```bash
python -c "from ui.environment_manager import EnvironmentManager; print('✓ Environment manager imported successfully')"
```

### Running the Streamlit App

From the project root directory:

```bash
streamlit run ui/app.py
```

**Expected output:**
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

Browser window should open automatically at `http://localhost:8501`

### Using the Command Center

#### Step 1: Initialize Environment

On the left sidebar (**Control Panel**):

1. **Grid Width**: Set to 20 (or adjust as needed)
2. **Grid Height**: Set to 20 (or adjust as needed)
3. **Number of Drones**: Set to 3-5 (more drones = faster rescue)
4. **Number of Survivors**: Set to 5-10 (more survivors = longer mission)
5. Click **"🔧 Initialize Environment"**

You should see: `✅ Environment initialized!`

#### Step 2: View the Mission Map

The main area shows:
- **Interactive Plotly Map** (left): Real-time grid visualization
  - 🟡 Yellow = Empty cells
  - 🔴 Red = Hazards
  - 🟠 Orange = Survivors (star markers)
  - ⬛ Dark = Obstacles
  - 🔵 Blue/Orange/Red diamonds = Drones (colored by battery level)
  
- **Mission Status** (right): 
  - Grid exploration percentage
  - Drone fleet status
  - Battery levels
  - Survivors rescued count

#### Step 3: Launch ARIA Agent

1. (Optional) Add mission briefing in the text area
   - Example: "Prioritize survivors in sector 15-20. Avoid extensive exploration."
2. Click **"🚀 Launch ARIA"**
3. Watch the real-time mission log

**Agent Behavior:**
- Automatically moves drones to explore
- Scans areas before entering
- Adjusts strategy based on battery levels
- Rescues survivors when found
- Returns to base when battery < 20%
- Completes when all survivors are rescued

#### Step 4:Monitor Progress

- **Mission Log** (bottom): Real-time agent actions and decisions
- **Map (left)**: Updates drone positions in real-time
- **Status (right)**: Live metrics

### Troubleshooting

#### Issue: "GOOGLE_API_KEY not set"
**Solution**: Add your API key to `.env` file. Get one free at https://aistudio.google.com/app/apikey

#### Issue: "Cannot import EnvironmentManager"
**Solution**: Ensure you're running from the project root directory with correct Python path

#### Issue: Agent doesn't respond
**Solution**: 
- Check that environment is initialized
- Verify GOOGLE_API_KEY in .env
- Check internet connection (for Gemini API calls)
- Agent has max 15 turns limit; if survivors > 10, may need more turns

#### Issue: Slow performance
**Solution**:
- Reduce grid size to 15x15
- Reduce number of survivors
- Reduce number of drones (paradoxically, too many slows planning)

### Architecture Overview

```
Streamlit UI (ui/app.py)
├── EnvironmentManager (ui/environment_manager.py)
│   ├── Grid (environment/grid.py)
│   ├── DroneSwarm (environment/drone.py)
│   └── Survivors (local dataclass)
│
└── Langchain Agent Loop
    ├── Tools (MCP-based)
    ├── Google Gemini LLM
    └── Real-time Agent Reasoning
```

### Files Modified/Created

**New Files:**
- `ui/environment_manager.py` - Local simulation manager (400+ lines)

**Modified Files:**
- `ui/app.py` - Complete refactor to use local manager + Langchain

**Unchanged:**
- `environment/` - Grid and Drone classes (used by local manager)
- `orchestrator/` - Kept for future integration
- `mcp_server/` - Can be started independently if needed

### Features

✅ **Self-Contained**: No external servers required  
✅ **Real-Time Visualization**: Interactive Plotly maps with live updates  
✅ **Intelligent Agent**: Langchain-based ARIA with decision-making  
✅ **Configurable**: Adjust grid, drones, survivors on-the-fly  
✅ **Battery Management**: Realistic drone power constraints  
✅ **Hazard Avoidance**: Intelligent pathfinding around obstacles  
✅ **Progress Tracking**: Live mission log and status metrics  

### Next Steps / Future Enhancements

1. **Persistent Storage**: Save missions to JSON/database
2. **Manual Control**: Button to manually move drones
3. **Advanced Visualization**: 3D grid view, drone path trails
4. **Multi-Agent Comparison**: Run different LLM strategies side-by-side
5. **Benchmark Metrics**: Success rate, efficiency, battery usage analysis

### Support

For issues with:
- **Streamlit**: https://docs.streamlit.io
- **Langchain**: https://python.langchain.com
- **MCP**: https://modelcontextprotocol.io
- **Google Gemini API**: https://ai.google.dev

---

**Last Updated**: March 2026  
**Framework**: Streamlit + Langchain + MCP SDK  
**LLM**: Google Gemini 2.5 Flash
