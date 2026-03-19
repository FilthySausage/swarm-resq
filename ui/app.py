"""
app.py — Streamlit Dashboard
Wired to MCP server (single source of truth) + orchestrator agent.

Run order:
    Terminal 1: uvicorn mcp_server.server:app --reload --port 8000
    Terminal 2: streamlit run ui/app.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Project root on path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MCP_SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
TOOLS_URL = f"{MCP_SERVER_URL}/tools"

CELL_COLORS = {
    ".": "[EMPTY]",
    "#": "[OBSTACLE]",
    "S": "[SURVIVOR]",
    "X": "[HAZARD]",
    "D": "[DRONE]",
    "R": "[RESCUED]",
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Swarm-ResQ Command Center",
    page_icon="drone",
    layout="wide",
)

st.title("Swarm-ResQ Command Center")
st.caption("Autonomous rescue drone swarm - Powered by ARIA + Gemini")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
for key, default in [
    ("mission_active", False),
    ("mission_log", ""),
    ("mission_complete", False),
    ("environment_initialized", False),
    ("last_state", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# MCP server helpers
# ---------------------------------------------------------------------------

def mcp_post(endpoint: str, **params) -> dict:
    """POST to a MCP REST tool endpoint."""
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(f"{TOOLS_URL}/{endpoint}", params=params)
            return r.json() if r.status_code == 200 else {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def mcp_get(endpoint: str, **params) -> dict:
    """GET from a MCP REST tool endpoint."""
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{TOOLS_URL}/{endpoint}", params=params)
            return r.json() if r.status_code == 200 else {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def server_is_up() -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{MCP_SERVER_URL}/health")
            return r.status_code == 200
    except Exception:
        return False


def fetch_state() -> Optional[dict]:
    """Fetch swarm state from MCP server."""
    state = mcp_get("get_swarm_state")
    if state.get("success") is False:
        return None
    st.session_state.last_state = state
    return state

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Control Panel")

    # Server status indicator
    if server_is_up():
        st.success("MCP Server online")
    else:
        st.error("MCP Server offline - start it first:\n`uvicorn mcp_server.server:app --reload --port 8000`")

    st.subheader("Environment Setup")
    col1, col2 = st.columns(2)
    with col1:
        grid_width = st.number_input("Grid Width", 10, 50, 20)
    with col2:
        grid_height = st.number_input("Grid Height", 10, 50, 20)

    col3, col4 = st.columns(2)
    with col3:
        drone_count = st.number_input("Drones", 1, 5, 3)
    with col4:
        survivor_count = st.number_input("Survivors", 1, 20, 5)

    if st.button("Initialize Environment", use_container_width=True):
        result = mcp_post(
            "initialize_mission",
            width=int(grid_width),
            height=int(grid_height),
            drone_count=int(drone_count),
            survivor_count=int(survivor_count),
        )
        if result.get("success"):
            st.session_state.environment_initialized = True
            st.session_state.mission_complete = False
            st.session_state.mission_log = ""
            st.success("Environment initialized!")
            st.rerun()
        else:
            st.error(f"Error: {result.get('error', 'Unknown error')}")

    st.divider()

    st.subheader("Mission Briefing")
    mission_briefing = st.text_area(
        "Additional instructions for ARIA",
        placeholder="e.g., Prioritize high-battery drones for distant sectors.",
        height=100,
        disabled=not st.session_state.environment_initialized,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        launch_btn = st.button(
            "Launch ARIA",
            type="primary",
            disabled=st.session_state.mission_active or not st.session_state.environment_initialized,
            use_container_width=True,
        )
    with col_b:
        stop_btn = st.button(
            "Stop Mission",
            disabled=not st.session_state.mission_active,
            use_container_width=True,
        )

    st.divider()

    st.subheader("Legend")
    labels = {".": "Empty", "#": "Obstacle", "S": "Survivor", "X": "Hazard", "D": "Drone", "R": "Rescued"}
    for sym, label in labels.items():
        st.write(f"{sym} = {label}")

# ---------------------------------------------------------------------------
# Layout (define containers upfront)
# ---------------------------------------------------------------------------
col_grid, col_metrics = st.columns([2, 1])
col_log = st.container()
status_container = st.empty()
log_container = st.empty()
map_container = col_grid.empty()

# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def render_grid_plotly(grid_data: dict, drones: list) -> Optional[go.Figure]:
    if not grid_data or "cells" not in grid_data:
        return None

    cells = grid_data["cells"]
    h = len(cells)
    w = len(cells[0]) if cells else 0

    cell_color_map = {".": 0, "#": 3, "S": 2, "X": 1, "R": 4, "D": 0}
    z = [[cell_color_map.get(cells[y][x].get("type", "."), 0) for x in range(w)] for y in range(h)]
    labels = [[cells[y][x].get("type", ".") for x in range(w)] for y in range(h)]

    # Create text annotations for each cell
    annotations = []
    for y in range(h):
        for x in range(w):
            cell_type = cells[y][x].get("type", ".")
            if cell_type != ".":  # Only label non-empty cells
                label_text = CELL_COLORS.get(cell_type, cell_type)
                annotations.append(
                    dict(
                        x=x, y=y,
                        text=label_text,
                        showarrow=False,
                        font=dict(size=8, color="white" if cell_type in ["#", "X"] else "black"),
                    )
                )

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        z=z,
        colorscale=[
            [0.0, "#F0F0F0"], [0.25, "#FF4444"],
            [0.5, "#FF9900"], [0.75, "#444444"], [1.0, "#00CC00"],
        ],
        colorbar=dict(
            tickvals=[0, 1, 2, 3, 4],
            ticktext=["Empty/Drone", "Hazard", "Survivor", "Obstacle", "Rescued"],
            len=0.5,
        ),
        hovertext=labels,
        hoverinfo="text",
        showscale=True,
    ))

    if drones:
        xs = [d["x"] for d in drones if d.get("x") is not None]
        ys = [d["y"] for d in drones if d.get("y") is not None]
        ids = [d.get("drone_id", "?") for d in drones if d.get("x") is not None]
        bats = [d.get("battery", 0) for d in drones if d.get("x") is not None]
        colors = ["blue" if b > 60 else "orange" if b > 20 else "red" for b in bats]

        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers+text",
            marker=dict(size=14, color=colors, symbol="diamond", line=dict(width=2, color="white")),
            text=ids,
            textposition="top center",
            textfont=dict(size=9, color="black"),
            hovertext=[f"<b>{ids[i]}</b><br>({xs[i]},{ys[i]}) bat={bats[i]}%" for i in range(len(ids))],
            hoverinfo="text",
            name="Drones",
        ))

    fig.update_layout(
        title="Mission Map",
        xaxis=dict(title="X", showgrid=True, gridcolor="lightgray"),
        yaxis=dict(title="Y", showgrid=True, gridcolor="lightgray", autorange="reversed"),
        height=650,
        hovermode="closest",
        margin=dict(l=40, r=40, t=60, b=40),
        annotations=annotations,
    )
    return fig


def render_drone_table(drones: list) -> pd.DataFrame:
    if not drones:
        return pd.DataFrame()
    return pd.DataFrame([{
        "Drone": d.get("drone_id", "?"),
        "Position": f"({d.get('x','?')}, {d.get('y','?')})",
        "Battery": f"{d.get('battery','?')}%",
        "Status": d.get("status", "unknown").upper(),
        "Cargo": d.get("cargo") or "—",
    } for d in drones])


def render_mission_summary(state: dict) -> str:
    drones = state.get("drones", [])
    rescued = len(state.get("survivors_rescued", []))
    grid = state.get("grid", {})

    if grid and "cells" in grid:
        total = len(grid["cells"]) * len(grid["cells"][0])
        non_empty = sum(1 for row in grid["cells"] for c in row if c.get("type") != ".")
        explored_pct = (non_empty / max(1, total)) * 100
    else:
        explored_pct = 0

    operational = sum(1 for d in drones if d.get("battery", 0) > 0)
    low_bat = sum(1 for d in drones if 0 < d.get("battery", 0) <= 20)

    return (
        f"**Grid Explored:** {explored_pct:.1f}%\n\n"
        f"**Drones:** {operational}/{len(drones)} operational | {low_bat} low battery\n\n"
        f"**Survivors Rescued:** {rescued}"
    )

# ---------------------------------------------------------------------------
# Agent runner (calls orchestrator.agent.stream_agent via MCP server)
# ---------------------------------------------------------------------------

async def run_aria_agent(briefing: str):
    """Stream ARIA agent output into the UI. Agent calls MCP server tools."""
    from orchestrator.agent import stream_agent

    status_container.info("ARIA Agent starting mission...")
    full_log = f"ARIA Initialized\nBriefing: {briefing or 'Standard rescue protocol'}\n\n"
    
    chunk_count = 0
    map_counter = 0

    try:
        async for chunk in stream_agent(mission_briefing=briefing):
            full_log += chunk
            chunk_count += 1
            
            # Update log
            log_container.code(full_log[-6000:], language="text")

            # Update map every 10 chunks
            if chunk_count % 10 == 0:
                state = fetch_state()
                if state:
                    fig = render_grid_plotly(state.get("grid", {}), state.get("drones", []))
                    if fig:
                        map_counter += 1
                        map_container.plotly_chart(fig, use_container_width=True, key=f"map_{map_counter}")

        # Final update
        state = fetch_state()
        if state:
            rescued = len(state.get("survivors_rescued", []))
            full_log += f"\n\n[MISSION COMPLETE] Survivors rescued: {rescued}"
            log_container.code(full_log[-6000:], language="text")
            
            fig = render_grid_plotly(state.get("grid", {}), state.get("drones", []))
            if fig:
                map_container.plotly_chart(fig, use_container_width=True, key="map_final")

        status_container.success("[SUCCESS] Mission complete!")

    except Exception as e:
        full_log += f"\n[ERROR] {e}"
        status_container.error(f"[ERROR] {e}")
        log_container.code(full_log[-6000:], language="text")

    # Save and stop
    st.session_state.mission_log = full_log
    st.session_state.mission_active = False
    st.session_state.mission_complete = True

# ---------------------------------------------------------------------------
# Button handlers
# ---------------------------------------------------------------------------
if launch_btn:
    st.session_state.mission_active = True
    st.session_state.mission_complete = False
    st.rerun()

if stop_btn:
    st.session_state.mission_active = False
    st.session_state.mission_complete = True
    st.rerun()

# ---------------------------------------------------------------------------
# Run agent if active
# ---------------------------------------------------------------------------
if st.session_state.mission_active:
    asyncio.run(run_aria_agent(mission_briefing))
    st.rerun()  # Rerun to show final state

# ---------------------------------------------------------------------------
# Display based on state
# ---------------------------------------------------------------------------
if not st.session_state.environment_initialized:
    col_grid.info("Initialize the environment using the Control Panel on the left.")

elif st.session_state.mission_complete:
    # Show final results
    state = fetch_state()
    if state:
        rescued = len(state.get("survivors_rescued", []))
        if rescued > 0:
            st.balloons()
            st.success(f"Mission Complete! {rescued} survivor(s) rescued.")
        else:
            st.warning(f"Mission Complete! {rescued} survivor(s) rescued.")
        
        with col_log:
            st.markdown("### ARIA Mission Log")
            st.code(st.session_state.mission_log[-6000:], language="text")
        
        with col_grid:
            fig = render_grid_plotly(state.get("grid", {}), state.get("drones", []))
            if fig:
                st.plotly_chart(fig, use_container_width=True, key="map_complete")
        
        with col_metrics:
            st.subheader("Final Mission Status")
            st.markdown(render_mission_summary(state))

            st.subheader("Final Drone Fleet")
            df = render_drone_table(state.get("drones", []))
            if not df.empty:
                for _, row in df.iterrows():
                    bat_val = int(row["Battery"].replace("%", ""))
                    color = "HIGH" if bat_val > 60 else "MEDIUM" if bat_val > 20 else "LOW"
                    st.write(f"[{color}] **{row['Drone']}** — {row['Position']} — {row['Battery']} — {row['Status']}")
                    st.progress(bat_val / 100)

            counts = mcp_get("get_survivor_counts")
            if counts and not counts.get("error"):
                st.subheader("Final Survivor Counts")
                st.metric("Total Rescued", counts.get("rescued", "?"))
                st.metric("Remaining", counts.get("on_grid", "?"))
                st.metric("In Transit", counts.get("in_cargo", "?"))

else:
    # Show pre-mission state
    state = fetch_state()
    if state:
        with col_grid:
            fig = render_grid_plotly(state.get("grid", {}), state.get("drones", []))
            if fig:
                st.plotly_chart(fig, use_container_width=True, key="map_static")

        with col_metrics:
            st.subheader("Mission Status")
            st.markdown(render_mission_summary(state))

            st.subheader("Drone Fleet")
            df = render_drone_table(state.get("drones", []))
            if not df.empty:
                for _, row in df.iterrows():
                    bat_val = int(row["Battery"].replace("%", ""))
                    color = "HIGH" if bat_val > 60 else "MEDIUM" if bat_val > 20 else "LOW"
                    st.write(f"[{color}] **{row['Drone']}** — {row['Position']} — {row['Battery']} — {row['Status']}")
                    st.progress(bat_val / 100)

            counts = mcp_get("get_survivor_counts")
            if counts and not counts.get("error"):
                st.subheader("Survivors")
                st.metric("On Grid", counts.get("on_grid", "?"))
                st.metric("Rescued", counts.get("rescued", "?"))
                st.metric("In Transit", counts.get("in_cargo", "?"))
    else:
        col_grid.error("Cannot reach MCP server. Is it running on port 8001?")

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
if st.checkbox("Show debug info", value=False):
    st.json(st.session_state.last_state or {})
