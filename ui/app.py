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
from pathlib import Path

# Get the project root directory (universal path setup)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ui.environment_manager import EnvironmentManager
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize environment manager as Streamlit singleton
@st.cache_resource
def get_environment_manager():
    return EnvironmentManager(width=20, height=20)

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

# Initialize environment manager
env_manager = get_environment_manager()

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

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Control Panel")
    
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
        result = env_manager.initialize_mission(
            width=int(grid_width),
            height=int(grid_height),
            drone_count=int(drone_count),
            survivor_count=int(survivor_count),
        )
        st.session_state.environment_initialized = True
        st.success("✅ Environment initialized!")
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
    """Fetch current swarm state from local environment manager."""
    if not st.session_state.environment_initialized:
        return None
    
    try:
        state = env_manager.get_state()
        st.session_state.last_state = state
        
        # Sync movement paths from environment manager (if method exists)
        if hasattr(env_manager, 'get_movement_paths'):
            paths_result = env_manager.get_movement_paths()
            if paths_result.get("success"):
                st.session_state.drone_paths = paths_result.get("paths", {})
        
        return state
    except Exception as e:
        st.warning(f"Error fetching state: {e}", icon="⚠️")
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
            autorange="reversed",  # Invert Y axis so (0,0) is top-left
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
    """Create Langchain tools that interface with local environment manager."""
    
    @tool
    def get_swarm_state() -> str:
        """Get the current swarm state including all drones, grid, and survivors."""
        state = env_manager.get_state()
        return json.dumps(state)
    
    @tool
    def move_drone(drone_id: str, dx: int, dy: int) -> str:
        """Move a drone by relative coordinates (dx, dy) where each is -1, 0, or 1."""
        result = env_manager.move_drone(drone_id, dx, dy)
        return json.dumps(result)
    
    @tool
    def scan_area(drone_id: str, radius: int = 2) -> str:
        """Scan the area around a drone to reveal surrounding cells."""
        result = env_manager.scan_area(drone_id, radius)
        return json.dumps(result)
    
    @tool
    def rescue_survivor(drone_id: str, target_x: int, target_y: int) -> str:
        """Rescue a survivor at the target location (drone must be adjacent)."""
        result = env_manager.rescue_survivor(drone_id, target_x, target_y)
        return json.dumps(result)
    
    @tool
    def return_to_base(drone_id: str) -> str:
        """Return a drone to base (0,0) and deliver cargo if carrying."""
        result = env_manager.return_to_base(drone_id)
        return json.dumps(result)
    
    @tool
    def get_survivor_counts() -> str:
        """Get counts of total, rescued, and remaining survivors."""
        result = env_manager.get_survivor_counts()
        return json.dumps(result)
    
    @tool
    def get_drone_state(drone_id: str) -> str:
        """Get the state of a specific drone."""
        result = env_manager.get_drone_state(drone_id)
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


async def run_stream_agent(briefing: str):
    """Run Langchain ARIA agent with local environment manager."""
    
    # Get placeholders for real-time updates
    status_placeholder = st.empty()
    log_placeholder = st.empty()
    
    full_log = "🚁 ARIA Agent Initialized\n"
    full_log += f"User Briefing: {briefing if briefing else 'Standard rescue protocol'}\n\n"
    
    try:
        # Initialize Langchain components
        # --------- OPENROUTER (Active) ---------
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        if not api_key:
            status_placeholder.error("❌ OPENROUTER_API_KEY not set. Add it to .env file.")
            return full_log
        
        # Create LLM with OpenRouter
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
        )
        
        # Create tools
        tools = create_langchain_tools()
        
        # Create agent prompt
        system_prompt = """You are ARIA (Autonomous Rescue Intelligence Agent), commanding a drone swarm in a rescue operation.

OBJECTIVES (priority order):
1. Explore the entire grid to find all survivors and hazards
2. Rescue every survivor and return them to base (0,0)
3. Manage drone battery levels (return to base when < 20%)
4. Avoid hazards and obstacles

RULES:
- Always start by calling get_swarm_state() to see current situation
- Drone movements use move_drone() with dx,dy each being -1, 0, or 1
- Scan before moving to unknown areas
- When you find survivors (S), move adjacent and use rescue_survivor()
- When carrying cargo, return to base with return_to_base()
- Continuously monitor battery levels, especially drones with battery < 20%

At each turn, provide:
1. Current situation analysis
2. Planned actions for each drone
3. Critical issues or hazards detected

Be concise but strategic."""
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", f"Mission briefing: {briefing if briefing else 'Execute standard rescue protocol with drone swarm.'}")
        ])
        
        # Bind tools to LLM
        llm_with_tools = llm.bind_tools(tools)
        
        # Run agent loop
        status_placeholder.info("🌀 ARIA Agent Starting Mission...")
        
        messages = [SystemMessage(content=system_prompt)]
        mission_active = True
        turn_count = 0

        while mission_active and turn_count < 15:  # Limit to 15 turns
            turn_count += 1
            turn_log = f"\n--- TURN {turn_count} ---\n"

            # Get state
            state = env_manager.get_state()
            survivors_remaining = state.get("survivors_at_base", [])
            all_survivors = len(state.get("survivors", []))

            # Check win condition
            rescuedcount = len(state.get("survivors_at_base", []))
            if rescuedcount == all_survivors:
                turn_log += "✅ ALL SURVIVORS RESCUED! Mission complete!\n"
                full_log += turn_log
                mission_active = False
                break

            # Add user message for this turn
            user_msg = f"Turn {turn_count}: {rescuedcount}/{all_survivors} survivors rescued. Execute next action."
            messages.append(HumanMessage(content=user_msg))

            # Get LLM response
            response = llm_with_tools.invoke(messages)

            # Add assistant response to messages (response is already an AIMessage)
            messages.append(response)

            # Extract text content for logging (content may be a string or list)
            if isinstance(response.content, str):
                turn_log += response.content + "\n"
            elif isinstance(response.content, list):
                for block in response.content:
                    if isinstance(block, str):
                        turn_log += block + "\n"
                    elif isinstance(block, dict) and block.get("type") == "text":
                        turn_log += block.get("text", "") + "\n"

            # Process tool calls if any
            if hasattr(response, 'tool_calls') and response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call['args']
                    tool_call_id = tool_call.get('id', tool_name)
                    turn_log += f"🔧 Executing: {tool_name}({tool_args})\n"

                    # Execute the tool
                    result_str = ""
                    for t in tools:
                        if t.name == tool_name:
                            try:
                                result_str = t.func(**tool_args)
                                result_dict = json.loads(result_str)
                                if result_dict.get("success"):
                                    turn_log += f"✓ {tool_name} succeeded\n"
                                else:
                                    turn_log += f"✗ {tool_name}: {result_dict.get('error', 'Unknown error')}\n"
                            except Exception as e:
                                result_str = json.dumps({"error": str(e)})
                                turn_log += f"✗ Tool error: {str(e)}\n"
                            break

                    # Feed tool result back to the LLM
                    messages.append(ToolMessage(
                        content=result_str,
                        tool_call_id=tool_call_id,
                    ))
            
            # Update UI with real-time log
            full_log += turn_log
            with log_placeholder.container():
                st.markdown("### 📋 ARIA Mission Log")
                st.code(full_log, language="text")
            
            await asyncio.sleep(0.5)
        
        # Final status
        state = env_manager.get_state()
        final_status = f"\n✅ Mission completed after {turn_count} turns\n"
        final_status += f"Survivors rescued: {len(state.get('survivors_at_base', []))} / {len(state.get('survivors', []))}\n"
        full_log += final_status
        
        status_placeholder.success("✅ ARIA mission cycle complete!")
        
    except Exception as e:
        full_log += f"\n❌ Agent error: {str(e)}\n"
        status_placeholder.error(f"❌ Agent error: {e}")
    
    st.session_state.mission_log = full_log
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
                    st.plotly_chart(fig, use_container_width=True)
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

