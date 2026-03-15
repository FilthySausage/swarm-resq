"""
app.py — Streamlit Dashboard
Member 4 (UI/Integration) workspace.

Real-time visualization of drone swarm missions with live agent streaming,
mission tracking, and grid visualization.

Run with:
    streamlit run ui/app.py
"""

import asyncio
import time
from typing import Optional
import requests
import pandas as pd
import streamlit as st

try:
    from orchestrator.agent import stream_agent
except ImportError:
    stream_agent = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MCP_STATE_URL = "http://localhost:8000/mcp"
POLL_INTERVAL = 2  # seconds between auto-refresh

CELL_COLORS = {
    ".": "⬜",  # Empty
    "#": "⬛",  # Obstacle
    "S": "🟡",  # Survivor
    "X": "🔴",  # Hazard
    "D": "🔵",  # Drone
    "R": "🟢",  # Rescued
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Swarm-ResQ Command Center",
    page_icon="🚁",
    layout="wide",
)

st.title("🚁 Swarm-ResQ — Command Center")
st.caption("Real-time rescue drone swarm visualization & mission control")

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "mission_active" not in st.session_state:
    st.session_state.mission_active = False
if "mission_log" not in st.session_state:
    st.session_state.mission_log = ""
if "mission_complete" not in st.session_state:
    st.session_state.mission_complete = False

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Control Panel")
    
    # Mission briefing input
    st.subheader("🎯 Mission Briefing")
    mission_briefing = st.text_area(
        "Additional instructions for ARIA",
        placeholder="e.g., Prioritize high-battery drones for distant sectors.",
        height=100,
    )
    
    col1, col2 = st.columns(2)
    with col1:
        launch_btn = st.button(
            "🚀 Launch ARIA",
            type="primary",
            disabled=st.session_state.mission_active,
            use_container_width=True,
        )
    with col2:
        stop_btn = st.button(
            "⏹️ Stop Mission",
            disabled=not st.session_state.mission_active,
            use_container_width=True,
        )
    
    st.divider()
    
    # Visualization settings
    st.subheader("📊 Display Options")
    show_grid = st.checkbox("Show Grid", value=True)
    show_legend = st.checkbox("Show Legend", value=True)
    auto_refresh = st.checkbox("Auto-refresh", value=True)
    
    if auto_refresh:
        refresh_rate = st.slider("Refresh rate (s)", 1, 10, POLL_INTERVAL)
    
    st.divider()
    
    # Legend
    if show_legend:
        st.subheader("ℹ️ Legend")
        for symbol, emoji in CELL_COLORS.items():
            labels = {
                ".": "Empty",
                "#": "Obstacle",
                "S": "Survivor",
                "X": "Hazard",
                "D": "Drone",
                "R": "Rescued",
            }
            st.write(f"{emoji}  {labels.get(symbol, '?')}")

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

# Top row: Grid + Status
col_grid, col_metrics = st.columns([2, 1])

# Bottom row: Mission Log
col_log = st.container()

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def fetch_state() -> Optional[dict]:
    """Fetch current swarm state from MCP server."""
    try:
        resp = requests.post(
            MCP_STATE_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_swarm_state", "arguments": {}},
            },
            timeout=3,
        )
        resp.raise_for_status()
        data = resp.json()
        result_text = data.get("result", {}).get("content", [{}])[0].get("text")
        if isinstance(result_text, str):
            import json
            return json.loads(result_text)
        return result_text
    except Exception as e:
        st.warning(f"Cannot reach MCP server: {e}", icon="⚠️")
        return None


def render_grid_emoji(grid_data: dict) -> str:
    """Render grid as emoji matrix."""
    if not grid_data or "cells" not in grid_data:
        return "No grid data available"
    
    cells = grid_data.get("cells", [])
    rows = []
    for row in cells:
        row_str = " ".join(CELL_COLORS.get(c.get("type", "."), "❓") for c in row)
        rows.append(row_str)
    return "\n".join(rows)


def render_drone_table(drones: list) -> pd.DataFrame:
    """Convert drone data to DataFrame for display."""
    if not drones:
        return pd.DataFrame()
    
    data = []
    for drone in drones:
        data.append({
            "Drone": drone.get("drone_id", "?"),
            "Position": f"({drone.get('x', '?')}, {drone.get('y', '?')})",
            "Battery": f"{drone.get('battery', '?')}%",
            "Status": drone.get("status", "unknown").upper(),
            "Cargo": drone.get("cargo", "—"),
        })
    
    return pd.DataFrame(data)


def render_mission_summary(state: dict) -> str:
    """Generate a brief mission summary."""
    drones = state.get("drones", [])
    grid = state.get("grid", {})
    survivors_rescued = len(state.get("survivors_rescued", []))
    
    # Calculate grid exploration
    if grid and "cells" in grid:
        total_cells = len(grid["cells"]) * len(grid["cells"][0])
        explored = sum(
            1 for row in grid["cells"]
            for cell in row if cell.get("type") != "."
        )
        explored_pct = (explored / max(1, total_cells)) * 100
    else:
        explored_pct = 0
    
    # Drone status
    operational = sum(1 for d in drones if d.get("battery", 0) > 0)
    low_battery = sum(1 for d in drones if 0 < d.get("battery", 0) <= 20)
    
    return f"""
    **Grid Explored:** {explored_pct:.1f}%
    
    **Drones:** {operational}/{len(drones)} operational | {low_battery} low battery
    
    **Survivors Rescued:** {survivors_rescued}
    """


# ---------------------------------------------------------------------------
# Agent streaming function
# ---------------------------------------------------------------------------

async def run_stream_agent(briefing: str):
    """Run agent with streaming output to Streamlit."""
    log_placeholder = col_log.empty()
    status_placeholder = col_grid.empty()
    
    full_log = ""
    
    if stream_agent is None:
        status_placeholder.error("❌ Cannot import stream_agent. Is orchestrator module available?")
        return
    
    status_placeholder.info("🌀 Launching ARIA Agent...")
    
    try:
        async for chunk in stream_agent(briefing):
            full_log += chunk
            # Update log in real-time
            with log_placeholder.container():
                st.markdown("### 📋 ARIA Mission Log")
                st.code(full_log, language="text")
            # Small delay to prevent overwhelming updates
            await asyncio.sleep(0.01)
        
        status_placeholder.success("✅ ARIA mission cycle complete!")
        st.session_state.mission_log = full_log
        return full_log
        
    except Exception as e:
        status_placeholder.error(f"❌ Agent error: {e}")
        st.write(f"Full error: {str(e)}")
        return full_log


# ---------------------------------------------------------------------------
# Mission launch logic
# ---------------------------------------------------------------------------

if launch_btn:
    st.session_state.mission_active = True
    st.rerun()

if stop_btn:
    st.session_state.mission_active = False
    st.session_state.mission_complete = True
    st.rerun()

# Run agent if mission is active
if st.session_state.mission_active and not st.session_state.mission_complete:
    # Run the streaming agent
    agent_output = asyncio.run(run_stream_agent(mission_briefing))
    st.session_state.mission_log = agent_output
    st.session_state.mission_active = False

# Display mission log if available
if st.session_state.mission_log:
    with col_log:
        st.markdown("### 📋 ARIA Mission Log")
        st.code(st.session_state.mission_log, language="text")

# ---------------------------------------------------------------------------
# Grid and status display
# ---------------------------------------------------------------------------

with st.spinner("Fetching mission state..."):
    state = fetch_state()

if state:
    with col_grid:
        if show_grid:
            st.subheader("🗺️ Grid State")
            grid_view = render_grid_emoji(state.get("grid", {}))
            st.code(grid_view, language=None)
    
    with col_metrics:
        st.subheader("📊 Mission Status")
        summary = render_mission_summary(state)
        st.markdown(summary)
        
        # Drone table
        st.subheader("🚁 Drone Fleet")
        drone_df = render_drone_table(state.get("drones", []))
        if not drone_df.empty:
            st.dataframe(drone_df, use_container_width=True, hide_index=True)
        else:
            st.info("No drone data available")
else:
    with col_grid:
        st.error(
            "❌ Cannot connect to MCP server. "
            "Ensure `uvicorn mcp_server.server:app` is running."
        )

# ---------------------------------------------------------------------------
# Session/debug info
# ---------------------------------------------------------------------------
if st.checkbox("Show debug info"):
    st.write("**Session State:**", st.session_state)
    with st.expander("Full API Response"):
        st.json(state if state else {})

