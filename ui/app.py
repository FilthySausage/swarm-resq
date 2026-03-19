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
from typing import Optional, AsyncGenerator
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import json
import os
import sys
import httpx
from pathlib import Path

# Get the project root directory (universal path setup)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator.model_loader import get_model_list, get_model_by_name, get_default_model
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MCP Server Configuration
MCP_SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
MCP_TOOLS_URL = f"{MCP_SERVER_URL}/tools"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GRID_WIDTH = 20
GRID_HEIGHT = 20
POLL_INTERVAL = 2  # seconds between auto-refresh

CELL_COLORS = {
    ".": "⬜",  # Empty
    "#": "⬛",  # Obstacle
    "S": "🟡",  # Survivor
    "X": "🔴",  # Hazard
    "D": "🔵",  # Drone
    "R": "🟢",  # Rescued
}

# MCP Client Helper Functions
async def call_mcp_tool(tool_name: str, **params) -> dict:
    """Call MCP server tool via REST endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            url = f"{MCP_TOOLS_URL}/{tool_name}"
            if tool_name in ["get_swarm_state", "get_survivor_counts", "get_movement_paths"]:
                response = await client.get(url, params=params)
            else:
                response = await client.post(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

def call_mcp_tool_sync(tool_name: str, **params) -> dict:
    """Synchronous wrapper for MCP tool calls."""
    return asyncio.run(call_mcp_tool(tool_name, **params))

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
if "environment_initialized" not in st.session_state:
    st.session_state.environment_initialized = False
if "last_state" not in st.session_state:
    st.session_state.last_state = None
if "drone_paths" not in st.session_state:
    st.session_state.drone_paths = {}  # Track movement paths for visualization
if "show_paths" not in st.session_state:
    st.session_state.show_paths = True  # Display movement paths
if "selected_model" not in st.session_state:
    st.session_state.selected_model = get_default_model()["name"]  # Default AI model
if "identified_survivors" not in st.session_state:
    st.session_state.identified_survivors = []

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Control Panel")
    
    # AI Model Selection
    st.subheader("🤖 AI Model Selection")
    available_models = get_model_list()
    selected_model_name = st.selectbox(
        "Choose AI Model",
        options=available_models,
        index=available_models.index(st.session_state.selected_model) if st.session_state.selected_model in available_models else 0,
        help="Select which AI model to use for mission planning"
    )
    
    # Update session state if model changed
    if selected_model_name != st.session_state.selected_model:
        st.session_state.selected_model = selected_model_name
        st.success(f"✓ Model changed to: {selected_model_name}")
    
    # Display model info
    selected_model_config = get_model_by_name(selected_model_name)
    if selected_model_config:
        with st.expander("ℹ️ Model Info"):
            st.caption(f"**Provider:** {selected_model_config['provider']}")
            st.caption(f"**Model ID:** {selected_model_config['model_id']}")
            st.caption(f"**Description:** {selected_model_config['description']}")
    
    st.divider()
    
    # Environment initialization
    st.subheader("🌍 Environment Setup")
    col_init1, col_init2 = st.columns(2)
    with col_init1:
        grid_width = st.number_input("Grid Width", 10, 50, 20)
    with col_init2:
        grid_height = st.number_input("Grid Height", 10, 50, 20)
    
    col_init3, col_init4 = st.columns(2)
    with col_init3:
        drone_count = st.number_input("Number of Drones", 1, 10, 3)
    with col_init4:
        survivor_count = st.number_input("Number of Survivors", 1, 20, 5)
    
    init_btn = st.button(
        "🔧 Initialize Environment",
        use_container_width=True,
    )
    
    if init_btn:
        result = call_mcp_tool_sync(
            "initialize_mission",
            width=int(grid_width),
            height=int(grid_height),
            drone_count=int(drone_count),
            survivor_count=int(survivor_count),
        )
        if result.get("success"):
            st.session_state.environment_initialized = True
            st.session_state.identified_survivors = []
            st.success("✅ Environment initialized!")
        else:
            st.error(f"❌ Initialization failed: {result.get('error')}")
        st.rerun()
    
    # Force cache refresh button (fixes attribute errors from cached old versions)
    if st.button("🔄 Refresh Cache", use_container_width=True, help="Clear cached objects and reload"):
        st.cache_resource.clear()
        st.rerun()
    
    st.divider()
    
    # Mission briefing input
    st.subheader("🎯 Mission Briefing")
    mission_briefing = st.text_area(
        "Additional instructions for ARIA",
        placeholder="e.g., Prioritize high-battery drones for distant sectors.",
        height=100,
        disabled=not st.session_state.environment_initialized,
    )
    
    col1, col2 = st.columns(2)
    with col1:
        launch_btn = st.button(
            "🚀 Launch ARIA",
            type="primary",
            disabled=st.session_state.mission_active or not st.session_state.environment_initialized,
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
    st.session_state.show_paths = st.checkbox("Show Movement Paths", value=True)
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
    if not st.session_state.environment_initialized:
        return None
    
    try:
        state = call_mcp_tool_sync("get_swarm_state")
        if state.get("success") is False:
            st.warning(f"Error fetching state: {state.get('error')}", icon="⚠️")
            return None
        
        st.session_state.last_state = state
        
        # Sync movement paths from MCP server
        paths_result = call_mcp_tool_sync("get_movement_paths")
        if paths_result.get("success"):
            st.session_state.drone_paths = paths_result.get("paths", {})
        
        return state
    except Exception as e:
        st.warning(f"Error fetching state: {e}", icon="⚠️")
        return None


async def fetch_state_async() -> Optional[dict]:
    """Async state fetch for in-mission live UI updates."""
    if not st.session_state.environment_initialized:
        return None

    try:
        state = await call_mcp_tool("get_swarm_state")
        if state.get("success") is False:
            return None

        st.session_state.last_state = state

        paths_result = await call_mcp_tool("get_movement_paths")
        if paths_result.get("success"):
            st.session_state.drone_paths = paths_result.get("paths", {})

        return state
    except Exception:
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


def render_grid_plotly(grid_data: dict, drones: list, survivors: list, drone_paths: dict = None) -> go.Figure:
    """Render interactive grid visualization with drones, survivors, and movement paths using Plotly."""
    if drone_paths is None:
        drone_paths = {}
    if not grid_data or "cells" not in grid_data:
        return None
    
    cells = grid_data.get("cells", [])
    height = len(cells)
    width = len(cells[0]) if cells else 0
    
    # Create grid visualization matrix (z values for heatmap)
    grid_visual = [[0 for _ in range(width)] for _ in range(height)]
    grid_labels = [[" " for _ in range(width)] for _ in range(height)]
    
    # Map cell types to numeric values for color coding
    cell_color_map = {
        ".": 0,   # Empty - light
        "#": 3,   # Obstacle - dark
        "S": 2,   # Survivor - orange target
        "X": 1,   # Hazard - red warning
        "R": 4,   # Rescued - green
    }
    
    # Fill the grid
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            cell_type = cell.get("type", ".")
            grid_visual[y][x] = cell_color_map.get(cell_type, 0)
            grid_labels[y][x] = cell_type
    
    # Create figure with custom colorscale
    fig = go.Figure()
    
    # Add heatmap for the grid
    fig.add_trace(go.Heatmap(
        z=grid_visual,
        colorscale=[
            [0.0, "#FFFFFF"],   # Empty - white
            [0.25, "#FF4444"],  # Hazard - red
            [0.5, "#FF9900"],   # Survivor - orange
            [0.75, "#444444"],  # Obstacle - dark gray
            [1.0, "#00CC00"],   # Rescued - green
        ],
        colorbar=dict(
            title="Cell Type",
            tickvals=[0, 1, 2, 3, 4],
            ticktext=["Empty", "Hazard", "Survivor", "Obstacle", "Rescued"],
            len=0.5,
        ),
        showscale=True,
        hovertext=grid_labels,
        hoverinfo="text",
        name="Grid",
    ))
    
    # Add drone markers
    if drones:
        drone_xs = []
        drone_ys = []
        drone_ids = []
        drone_batteries = []
        drone_colors = []
        
        for drone in drones:
            x = drone.get("x")
            y = drone.get("y")
            if x is not None and y is not None:
                drone_xs.append(x)
                drone_ys.append(y)
                drone_ids.append(drone.get("drone_id", "?"))
                battery = drone.get("battery", 0)
                drone_batteries.append(battery)
                
                # Color by battery level
                if battery > 60:
                    drone_colors.append("blue")
                elif battery > 30:
                    drone_colors.append("orange")
                else:
                    drone_colors.append("red")
        
        if drone_xs:
            fig.add_trace(go.Scatter(
                x=drone_xs,
                y=drone_ys,
                mode="markers+text",
                marker=dict(
                    size=12,
                    color=drone_colors,
                    symbol="diamond",
                    line=dict(width=2, color="white"),
                ),
                text=drone_ids,
                textposition="top center",
                textfont=dict(size=10, color="black"),
                hovertext=[
                    f"<b>{drone_ids[i]}</b><br>Pos: ({drone_xs[i]}, {drone_ys[i]})<br>Battery: {drone_batteries[i]}%"
                    for i in range(len(drone_ids))
                ],
                hoverinfo="text",
                name="Drones",
            ))
    
    # Add movement path traces if available
    if drone_paths:
        for drone_id, path_info in drone_paths.items():
            path = path_info.get("path", [])
            if len(path) > 1:
                path_xs = [p["x"] for p in path]
                path_ys = [p["y"] for p in path]
                
                # Find corresponding drone for color matching
                drone_color = "lightblue"
                for drone in drones:
                    if drone.get("drone_id") == drone_id:
                        battery = drone.get("battery", 0)
                        if battery > 60:
                            drone_color = "blue"
                        elif battery > 30:
                            drone_color = "orange"
                        else:
                            drone_color = "red"
                        break
                
                # Add path line
                fig.add_trace(go.Scatter(
                    x=path_xs,
                    y=path_ys,
                    mode="lines+markers",
                    line=dict(
                        color=drone_color,
                        width=2,
                        dash="dash",
                    ),
                    marker=dict(
                        size=4,
                        color=drone_color,
                        opacity=0.6,
                    ),
                    name=f"{drone_id} Path",
                    hoverinfo="skip",
                    showlegend=False,
                ))
    

    if survivors:
        survivor_xs = []
        survivor_ys = []
        survivor_ids = []
        
        for survivor in survivors:
            x = survivor.get("x")
            y = survivor.get("y")
            if x is not None and y is not None:
                survivor_xs.append(x)
                survivor_ys.append(y)
                survivor_ids.append(survivor.get("id", "S"))
        
        if survivor_xs:
            fig.add_trace(go.Scatter(
                x=survivor_xs,
                y=survivor_ys,
                mode="markers+text",
                marker=dict(
                    size=14,
                    color="orange",
                    symbol="star",
                    line=dict(width=2, color="darkorange"),
                ),
                text=survivor_ids,
                textposition="top center",
                textfont=dict(size=9, color="darkred"),
                hovertext=[
                    f"<b>Survivor {survivor_ids[i]}</b><br>Pos: ({survivor_xs[i]}, {survivor_ys[i]})"
                    for i in range(len(survivor_ids))
                ],
                hoverinfo="text",
                name="Survivors",
            ))
    
    # Update layout
    fig.update_layout(
        title=dict(
            text="🗺️ Swarm-ResQ Mission Map - Real-time Drone Tracking",
            font=dict(size=20),
        ),
        xaxis=dict(
            title="X Position",
            showgrid=True,
            gridwidth=1,
            gridcolor="lightgray",
        ),
        yaxis=dict(
            title="Y Position",
            showgrid=True,
            gridwidth=1,
            gridcolor="lightgray",
            # FIXED: Removed autorange="reversed" - now (0,0) is bottom-left
        ),
        width=800,
        height=700,
        hovermode="closest",
        margin=dict(l=50, r=50, t=80, b=50),
    )
    
    return fig


def render_drone_heatmap(drones: list, grid_size: tuple) -> go.Figure:
    """Render heatmap of drone coverage/density."""
    if not drones or not grid_size:
        return None
    
    width, height = grid_size
    coverage = np.zeros((height, width))
    
    # Increment coverage for drone proximity
    for drone in drones:
        x = drone.get("x")
        y = drone.get("y")
        if x is not None and y is not None:
            coverage[int(y), int(x)] += 1
    
    fig = go.Figure(data=go.Heatmap(
        z=coverage,
        colorscale="Viridis",
        name="Coverage Density",
    ))
    
    fig.update_layout(
        title="Drone Coverage Density",
        xaxis_title="X Position",
        yaxis_title="Y Position",
        height=400,
        width=500,
    )
    
    return fig


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
# Agent streaming function using Langchain + MCP
# ---------------------------------------------------------------------------

def create_langchain_tools():
    """Create Langchain tools that interface with MCP server."""
    
    @tool
    def get_swarm_state() -> str:
        """Get the current swarm state including all drones, grid, and survivors."""
        result = call_mcp_tool_sync("get_swarm_state")
        return json.dumps(result)
    
    @tool
    def move_drone(drone_id: str, dx: int, dy: int) -> str:
        """Move a drone by relative coordinates (dx, dy) where each is -1, 0, or 1."""
        result = call_mcp_tool_sync("move_drone", drone_id=drone_id, dx=dx, dy=dy)
        return json.dumps(result)
    
    @tool
    def scan_area(drone_id: str, radius: int = 2) -> str:
        """Scan the area around a drone to reveal surrounding cells."""
        result = call_mcp_tool_sync("scan_area", drone_id=drone_id, radius=radius)
        return json.dumps(result)
    
    @tool
    def rescue_survivor(drone_id: str, target_x: int, target_y: int) -> str:
        """Rescue a survivor at the target location (drone must be adjacent)."""
        result = call_mcp_tool_sync("rescue_survivor", drone_id=drone_id, target_x=target_x, target_y=target_y)
        return json.dumps(result)
    
    @tool
    def return_to_base(drone_id: str) -> str:
        """Return a drone to base (0,0) and deliver cargo if carrying."""
        result = call_mcp_tool_sync("return_to_base", drone_id=drone_id)
        return json.dumps(result)
    
    @tool
    def get_survivor_counts() -> str:
        """Get counts of total, rescued, and remaining survivors."""
        result = call_mcp_tool_sync("get_survivor_counts")
        return json.dumps(result)
    
    @tool
    def get_drone_state(drone_id: str) -> str:
        """Get the state of a specific drone."""
        result = call_mcp_tool_sync("get_drone_state", drone_id=drone_id)
        return json.dumps(result)
    
    return [
        get_swarm_state,
        move_drone,
        scan_area,
        rescue_survivor,
        return_to_base,
        get_survivor_counts,
        get_drone_state,
    ]


async def run_stream_agent(briefing: str, model_name: str = None):
    """Run mission using single-prompt controller.
    
    Args:
        briefing: Mission briefing text
        model_name: Display name of the model to use
    """
    from orchestrator.mission_controller import MissionController
    
    status_placeholder = st.empty()
    log_placeholder = st.empty()
    with col_grid:
        live_grid_placeholder = st.empty()
    with col_metrics:
        live_summary_placeholder = st.empty()
        live_drone_table_placeholder = st.empty()
        live_survivor_placeholder = st.empty()
    
    controller = MissionController(model_name=model_name)

    async def refresh_live_sections() -> None:
        state = await fetch_state_async()
        if not state:
            return

        with live_grid_placeholder.container():
            fig = render_grid_plotly(
                state.get("grid", {}),
                state.get("drones", []),
                state.get("survivors", []),
                st.session_state.drone_paths if st.session_state.show_paths else {},
            )
            if fig:
                st.plotly_chart(fig, use_container_width=True, key="live_grid_plot")

        with live_summary_placeholder.container():
            st.subheader("📊 Mission Status")
            st.markdown(render_mission_summary(state))

        with live_drone_table_placeholder.container():
            st.subheader("🚁 Drone Fleet")
            drone_df = render_drone_table(state.get("drones", []))
            if not drone_df.empty:
                st.dataframe(drone_df, use_container_width=True, hide_index=True)

        with live_survivor_placeholder.container():
            st.subheader("📍 Identified Survivor Coordinates")
            if st.session_state.identified_survivors:
                coords = sorted(
                    st.session_state.identified_survivors,
                    key=lambda c: (c["x"], c["y"]),
                )
                st.dataframe(pd.DataFrame(coords), use_container_width=True, hide_index=True)
            else:
                st.caption("No survivors identified yet.")
    
    try:
        status_placeholder.info("Initializing AI and starting mission...")
        
        full_log = ""
        await refresh_live_sections()
        
        # Stream mission execution
        async for chunk in controller.stream_mission(briefing):
            if chunk.startswith("__EVENT__"):
                try:
                    event = json.loads(chunk[len("__EVENT__"):].strip())
                except json.JSONDecodeError:
                    event = {}

                event_type = event.get("type")
                if event_type == "movement_step":
                    full_log += (
                        f"STEP: {event.get('drone_id')} -> ({event.get('x')}, {event.get('y')}) "
                        f"battery={event.get('battery')}%\n"
                    )
                    status_placeholder.info(
                        f"{event.get('drone_id')} moved to ({event.get('x')}, {event.get('y')})"
                    )
                elif event_type == "survivor_detected":
                    coord = {"x": int(event.get("x", -1)), "y": int(event.get("y", -1))}
                    if coord not in st.session_state.identified_survivors:
                        st.session_state.identified_survivors.append(coord)
                        full_log += f"SURVIVOR DETECTED at ({coord['x']}, {coord['y']})\n"
                        status_placeholder.success(
                            f"Survivor identified at ({coord['x']}, {coord['y']})"
                        )

                await refresh_live_sections()
            else:
                full_log += chunk

            await asyncio.sleep(0.01)

            with log_placeholder.container():
                st.markdown("### MISSION LOG")
                st.code(full_log[-5000:], language="text")
        
        # Final log update
        with log_placeholder.container():
            st.markdown("### MISSION LOG")
            st.code(full_log, language="text")

        await refresh_live_sections()
        
        status_placeholder.success("Mission complete!")
        
    except Exception as e:
        full_log += f"\nERROR: {str(e)}\n"
        status_placeholder.error(f"Mission failed: {e}")
        with log_placeholder.container():
            st.markdown("### MISSION LOG")
            st.code(full_log, language="text")
    
    st.session_state.mission_log = full_log
    return full_log


# ---------------------------------------------------------------------------
# Mission launch logic
# ---------------------------------------------------------------------------

if launch_btn:
    st.session_state.mission_active = True
    st.session_state.mission_complete = False
    st.session_state.identified_survivors = []
    st.rerun()

if stop_btn:
    st.session_state.mission_active = False
    st.session_state.mission_complete = True
    st.rerun()

# Run agent if mission is active
if st.session_state.mission_active and not st.session_state.mission_complete:
    # Run the streaming agent with selected model
    agent_output = asyncio.run(run_stream_agent(mission_briefing, st.session_state.selected_model))
    st.session_state.mission_log = agent_output
    st.session_state.mission_active = False
    st.session_state.mission_complete = True

# Display mission log if available
if st.session_state.mission_log:
    with col_log:
        st.markdown("### 📋 ARIA Mission Log")
        st.code(st.session_state.mission_log, language="text")

# ---------------------------------------------------------------------------
# Grid and status display
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Grid and status display
# ---------------------------------------------------------------------------

if not st.session_state.environment_initialized:
    col_grid.info("🔧 Please initialize the environment using the Control Panel on the left.")
else:
    with st.spinner("Fetching mission state..."):
        state = fetch_state()
    
    if state:
        with col_grid:
            if show_grid:
                # Render interactive Plotly map with movement paths
                fig = render_grid_plotly(
                    state.get("grid", {}),
                    state.get("drones", []),
                    state.get("survivors", []),
                    st.session_state.drone_paths if st.session_state.show_paths else {}
                )
                if fig:
                    st.plotly_chart(fig, use_container_width=True, key="main_grid_plot")
                else:
                    st.warning("Cannot render grid map.")
        
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

            st.subheader("📍 Identified Survivor Coordinates")
            if st.session_state.identified_survivors:
                coords = sorted(
                    st.session_state.identified_survivors,
                    key=lambda c: (c["x"], c["y"]),
                )
                st.dataframe(pd.DataFrame(coords), use_container_width=True, hide_index=True)
            else:
                st.caption("No survivors identified yet.")
    else:
        with col_grid:
            st.error(
                "❌ Cannot fetch environment state. "
                "Please ensure environment is properly initialized."
            )

# ---------------------------------------------------------------------------
# Movement Status Display
# ---------------------------------------------------------------------------
if st.session_state.drone_paths:
    st.divider()
    st.subheader("📍 Movement Paths")
    
    # Create columns for path information
    path_cols = st.columns(len(st.session_state.drone_paths))
    
    for idx, (drone_id, path_info) in enumerate(st.session_state.drone_paths.items()):
        with path_cols[idx]:
            st.markdown(f"**{drone_id}**")
            
            if isinstance(path_info, dict) and "path" in path_info:
                path = path_info.get("path", [])
                stopped_reason = path_info.get("stopped_reason", "unknown")
                battery_used = path_info.get("battery_used", 0)
                battery_remaining = path_info.get("battery_remaining", 0)
                moves_count = path_info.get("moves_count", len(path) - 1)
                
                # Display path stats
                st.metric("Steps", moves_count)
                st.metric("Stopped By", stopped_reason.replace("_", " ").title())
                st.metric("Battery Used", battery_used)
                
                # Display path coordinates
                if len(path) > 1:
                    with st.expander(f"Path Coordinates ({len(path)} positions)"):
                        path_text = "→ ".join([f"({p['x']}, {p['y']})" for p in path])
                        st.caption(path_text)
            else:
                st.caption("No path data available")

# ---------------------------------------------------------------------------
# Session/debug info
# ---------------------------------------------------------------------------
if st.checkbox("Show debug info"):
    st.write("**Session State:**", st.session_state)
    with st.expander("Full API Response"):
        st.json(state if state else {})

