"""
app.py — Streamlit Dashboard
Member 4 (UI/Integration) workspace.

Renders the live 2D grid, drone positions, and mission log.
Connects to the MCP server's REST state endpoint to poll for updates.

Run with:
    streamlit run ui/app.py
"""

import time
import requests
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MCP_STATE_URL = "http://localhost:8000/mcp"  # TODO: confirm endpoint with Member 2
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
st.caption("Real-time rescue drone swarm visualization")

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Controls")
    auto_refresh = st.toggle("Auto-refresh", value=True)
    poll_interval = st.slider("Refresh interval (s)", 1, 10, POLL_INTERVAL)
    st.divider()

    st.header("🎯 Mission Brief")
    mission_input = st.text_area(
        "Additional mission briefing for ARIA",
        placeholder="e.g. Prioritize the north-east quadrant first.",
        height=120,
    )
    launch_btn = st.button("🚀 Launch ARIA Agent", type="primary", use_container_width=True)
    st.divider()

    st.header("ℹ️ Legend")
    for symbol, emoji in CELL_COLORS.items():
        labels = {
            ".": "Empty", "#": "Obstacle", "S": "Survivor",
            "X": "Hazard",  "D": "Drone",    "R": "Rescued",
        }
        st.write(f"{emoji}  {labels[symbol]}")

# ---------------------------------------------------------------------------
# Helper: fetch grid state from MCP server
# ---------------------------------------------------------------------------
def fetch_state() -> dict | None:
    try:
        # TODO (Member 4): Adjust to the correct REST endpoint once
        #                  Member 2 confirms the URL structure.
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
        return data.get("result", {}).get("content", [{}])[0].get("text")
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# Helper: render grid as emoji matrix
# ---------------------------------------------------------------------------
def render_grid(grid_data: dict) -> None:
    cells = grid_data.get("cells", [])
    rows = []
    for row in cells:
        row_str = " ".join(CELL_COLORS.get(c["type"], "❓") for c in row)
        rows.append(row_str)
    st.code("\n".join(rows), language=None)


# ---------------------------------------------------------------------------
# Helper: render drone table
# ---------------------------------------------------------------------------
def render_drone_table(drones: list[dict]) -> None:
    if not drones:
        st.info("No drones registered yet.")
        return
    df = pd.DataFrame(drones)
    df["battery"] = df["battery"].apply(lambda b: f"{b}%")
    st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
col_grid, col_info = st.columns([3, 1])

grid_placeholder = col_grid.empty()
drone_placeholder = col_info.empty()

status_placeholder = st.empty()

# ---------------------------------------------------------------------------
# Agent launch
# ---------------------------------------------------------------------------
if launch_btn:
    with st.spinner("Launching ARIA..."):
        # TODO (Member 4): Call orchestrator agent here.
        # import asyncio
        # from orchestrator.agent import run_agent
        # output = asyncio.run(run_agent(mission_input))
        # st.session_state["agent_log"] = output
        st.session_state["agent_log"] = (
            "⚠️ Agent integration placeholder — connect orchestrator.agent here."
        )

if "agent_log" in st.session_state:
    with st.expander("📋 ARIA Mission Log", expanded=True):
        st.write(st.session_state["agent_log"])

# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------
while True:
    state_raw = fetch_state()

    if state_raw is None:
        status_placeholder.warning(
            "⚠️ Cannot reach MCP server. Make sure `uvicorn mcp_server.server:app` is running."
        )
        with grid_placeholder.container():
            st.info("Waiting for simulation data...")
        with drone_placeholder.container():
            pass
    else:
        import json
        try:
            state = json.loads(state_raw) if isinstance(state_raw, str) else state_raw
            status_placeholder.success("✅ Connected to simulation")

            with grid_placeholder.container():
                st.subheader("🗺️ Grid")
                render_grid(state.get("grid", {}))

            with drone_placeholder.container():
                st.subheader("🚁 Drones")
                render_drone_table(state.get("drones", []))

        except Exception as e:
            status_placeholder.error(f"Error parsing state: {e}")

    if not auto_refresh:
        break

    time.sleep(poll_interval)
    st.rerun()


# ---------------------------------------------------------------------------
# TODO (Member 4):
#   - Add Plotly heatmap visualization of the grid
#   - Add survivor count / rescue progress bar
#   - Integrate agent streaming output into the mission log
# ---------------------------------------------------------------------------
