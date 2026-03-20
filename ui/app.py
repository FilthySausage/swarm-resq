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
import re
import httpx
from pathlib import Path

# Get the project root directory (universal path setup)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import orchestrator.model_loader as model_loader
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

get_model_list = model_loader.get_model_list
get_model_by_name = model_loader.get_model_by_name
get_default_model = model_loader.get_default_model
add_custom_model = model_loader.add_custom_model
remove_custom_model = getattr(model_loader, "remove_custom_model", None)

# Load environment variables
load_dotenv()

# MCP Server Configuration
MCP_SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
ACTIVE_MCP_SERVER_URL = MCP_SERVER_URL


def _build_mcp_base_urls() -> list[str]:
    """Return preferred MCP server URLs with local 8000/8001 fallback."""
    urls = [MCP_SERVER_URL]
    if MCP_SERVER_URL.endswith(":8000"):
        urls.append(MCP_SERVER_URL.replace(":8000", ":8001"))
    elif MCP_SERVER_URL.endswith(":8001"):
        urls.append(MCP_SERVER_URL.replace(":8001", ":8000"))
    return list(dict.fromkeys(urls))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GRID_WIDTH = 20
GRID_HEIGHT = 20
POLL_INTERVAL = 2  # seconds between auto-refresh

CELL_COLORS = {
    ".": "⬜",  # Empty
    "#": "⬛",  # Obstacle
    "S": "�",  # Survivor
    "X": "🔴",  # Hazard
    "D": "🔵",  # Drone
    "R": "🟢",  # Rescued
}

# MCP Client Helper Functions
async def call_mcp_tool(tool_name: str, **params) -> dict:
    """Call MCP server tool via REST endpoint."""
    global ACTIVE_MCP_SERVER_URL

    last_error = None
    base_urls = [ACTIVE_MCP_SERVER_URL] + [u for u in _build_mcp_base_urls() if u != ACTIVE_MCP_SERVER_URL]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for base_url in base_urls:
            try:
                url = f"{base_url}/tools/{tool_name}"
                if tool_name in ["get_swarm_state", "get_survivor_counts", "get_movement_paths"]:
                    response = await client.get(url, params=params)
                else:
                    response = await client.post(url, params=params)

                if response.status_code == 200:
                    ACTIVE_MCP_SERVER_URL = base_url
                    return response.json()

                last_error = f"{base_url} -> HTTP {response.status_code}: {response.text}"
            except Exception as e:
                last_error = f"{base_url} -> {e}"

    return {"success": False, "error": str(last_error or "MCP server unreachable")}

def call_mcp_tool_sync(tool_name: str, **params) -> dict:
    """Synchronous wrapper for MCP tool calls."""
    return asyncio.run(call_mcp_tool(tool_name, **params))


def get_installed_ollama_models(base_url: str = "http://localhost:11434/v1") -> list[str]:
    """Return locally installed Ollama model names, or empty list if unavailable."""
    try:
        ollama_host = base_url.rstrip("/")
        if ollama_host.endswith("/v1"):
            ollama_host = ollama_host[:-3]
        tags_url = f"{ollama_host}/api/tags"
        response = httpx.get(tags_url, timeout=3.0)
        response.raise_for_status()
        payload = response.json() or {}
        models = payload.get("models", [])
        names = [m.get("name", "").strip() for m in models if m.get("name")]
        return sorted(set(names))
    except Exception:
        return []

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
# View Log Dialog
# ---------------------------------------------------------------------------
@st.dialog("Log Viewer", width="large")
def view_log_modal(title: str, file_path: str):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        st.text_area(title, value=content, height=600)
    else:
        st.warning(f"File {file_path} not found.")

# ---------------------------------------------------------------------------
# Custom Model Dialog
# ---------------------------------------------------------------------------
@st.dialog("Add Custom Model")
def add_custom_model_dialog():
    st.write("Register a new local or custom model.")

    provider_base_urls = {
        "Ollama": "http://localhost:11434/v1",
        "OpenRouter": "https://openrouter.ai/api/v1",
        "OpenAI": "https://api.openai.com/v1",
    }
    provider_requires_key = {
        "Ollama": False,
        "OpenRouter": True,
        "OpenAI": True,
    }

    provider = st.selectbox(
        "Provider",
        options=["Ollama", "OpenRouter", "OpenAI"],
        index=0,
        help="Select one of the supported providers.",
    )
    model_name = st.text_input("Model Name", value="My Custom Model")

    base_url = provider_base_urls[provider]
    requires_key = provider_requires_key[provider]
    save_disabled = False

    if provider == "Ollama":
        ollama_models = get_installed_ollama_models(base_url)
        if ollama_models:
            model_id = st.selectbox(
                "Model ID (Installed in Ollama)",
                options=ollama_models,
                help="Only installed Ollama models are allowed.",
            )
        else:
            model_id = ""
            save_disabled = True
            st.warning(
                "No installed Ollama models detected. Pull a model first (e.g., 'ollama pull qwen2.5:3b') or choose OpenRouter/OpenAI.",
                icon="⚠️",
            )
    else:
        model_id = st.text_input("Model ID", value="")

    st.text_input("Base URL (Auto)", value=base_url, disabled=True)
    st.checkbox("Requires API Key", value=requires_key, disabled=True)

    if st.button("Save", type="primary", disabled=save_disabled):
        if not model_name.strip():
            st.error("Model Name is required.")
            return
        if not model_id.strip():
            st.error("Model ID is required.")
            return

        new_model_name = model_name.strip()
        new_model = {
            "name": new_model_name,
            "provider": provider,
            "model_id": model_id.strip(),
            "base_url": base_url,
            "requires_key": requires_key,
            "description": "Custom user-added model"
        }
        success = add_custom_model(new_model)
        if success:
            st.session_state.selected_model = new_model_name
            st.rerun()
        else:
            st.error("Failed to save custom model config.")


@st.dialog("Remove Custom Model")
def remove_custom_model_dialog():
    if remove_custom_model is None:
        st.error("Current runtime does not expose remove_custom_model yet. Restart Streamlit to reload latest model_loader.")
        return

    config_models = [get_model_by_name(name) for name in get_model_list()]
    custom_model_names = []
    for model in config_models:
        if not model:
            continue
        name = str(model.get("name", "")).strip()
        desc = str(model.get("description", "")).strip().lower()
        is_custom = name.endswith("(Custom)") or desc == "custom user-added model"
        if is_custom:
            custom_model_names.append(name)

    if not custom_model_names:
        st.info("No custom models available to remove.")
        return

    target_name = st.selectbox("Choose custom model to remove", custom_model_names)
    if st.button("Remove", type="secondary"):
        ok = remove_custom_model(target_name)
        if ok:
            remaining = get_model_list()
            if st.session_state.selected_model == target_name and remaining:
                st.session_state.selected_model = remaining[0]
            st.rerun()
        else:
            st.error("Failed to remove model.")

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
if "use_snapshot_state" not in st.session_state:
    st.session_state.use_snapshot_state = False
if "drone_paths" not in st.session_state:
    st.session_state.drone_paths = {}  # Track movement paths for visualization
if "show_paths" not in st.session_state:
    st.session_state.show_paths = True  # Display movement paths
if "selected_model" not in st.session_state:
    st.session_state.selected_model = get_default_model()["name"]  # Default AI model
if "identified_survivors" not in st.session_state:
    st.session_state.identified_survivors = []
if "identified_survivor_set" not in st.session_state:
    st.session_state.identified_survivor_set = set()
if "init_error" not in st.session_state:
    st.session_state.init_error = ""
if "init_status" not in st.session_state:
    st.session_state.init_status = ""
if "last_init_result" not in st.session_state:
    st.session_state.last_init_result = None
if "step_logs" not in st.session_state:
    st.session_state.step_logs = []
if "last_live_render_ts" not in st.session_state:
    st.session_state.last_live_render_ts = 0.0
if "live_plot_seq" not in st.session_state:
    st.session_state.live_plot_seq = 0

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

    if st.button("➕ Add Custom Model", use_container_width=True):
        add_custom_model_dialog()

    if st.button("➖ Remove Custom Model", use_container_width=True):
        remove_custom_model_dialog()

    # Display model info
    selected_model_config = get_model_by_name(selected_model_name)
    if selected_model_config:
        with st.expander("ℹ️ Model Info"):
            st.caption(f"**Provider:** {selected_model_config['provider']}")
            st.caption(f"**Model ID:** {selected_model_config['model_id']}")
            st.caption(f"**Base URL:** {selected_model_config['base_url']}")
            st.caption(f"**Description:** {selected_model_config['description']}")

        provider_name = str(selected_model_config.get("provider", "")).lower()
        if selected_model_config.get("requires_key"):
            if provider_name == "openai" and not os.getenv("OPENAI_API_KEY", "").strip():
                st.warning(
                    "This model needs OPENAI_API_KEY. Add it to .env or switch to an Ollama (Local) model.",
                    icon="⚠️",
                )
            elif provider_name == "openrouter" and not os.getenv("OPENROUTER_API_KEY", "").strip():
                st.warning(
                    "This model needs OPENROUTER_API_KEY. Add it to .env or switch to an Ollama (Local) model.",
                    icon="⚠️",
                )

        if provider_name == "ollama":
            st.info(
                "Using local Ollama backend. Ensure Ollama is running and model is pulled (e.g., `ollama run llama2`).",
                icon="🖥️",
            )
    
    st.divider()
    
    # Environment initialization
    st.subheader("🌍 Environment Setup")
    env_locked = st.session_state.get("mission_active", False)
    
    grid_width = st.number_input("Grid Width", 10, 50, 20, disabled=env_locked)
    grid_height = st.number_input("Grid Height", 10, 50, 20, disabled=env_locked)
    
    drone_count = st.number_input("Number of Drones", 1, 10, 3, disabled=env_locked)
    survivor_count = st.number_input("Number of Survivors", 1, 20, 5, disabled=env_locked)
    
    init_btn = st.button(
        "🔧 Initialize Environment",
        disabled=env_locked,
        use_container_width=True,
    )
    
    if init_btn:
        st.session_state.init_status = "Initializing environment..."
        st.session_state.init_error = ""
        result = call_mcp_tool_sync(
            "initialize_mission",
            width=int(grid_width),
            height=int(grid_height),
            drone_count=int(drone_count),
            survivor_count=int(survivor_count),
        )
        st.session_state.last_init_result = result
        if result.get("success"):
            st.session_state.environment_initialized = True
            st.session_state.mission_active = False
            st.session_state.mission_complete = False
            st.session_state.drone_paths = {}
            st.session_state.mission_log = ""
            st.session_state.step_logs = []
            st.session_state.live_plot_seq = 0
            st.session_state.use_snapshot_state = False
            st.session_state.identified_survivors = []
            st.session_state.identified_survivor_set = set()
            st.session_state.init_error = ""
            st.session_state.init_status = f"Environment initialized via {ACTIVE_MCP_SERVER_URL}"
            st.success("✅ Environment initialized!")
            st.rerun()
        else:
            st.session_state.environment_initialized = False
            st.session_state.init_error = f"❌ Initialization failed: {result.get('error')}"
            st.session_state.init_status = "Initialization failed"

    if st.session_state.init_status:
        st.info(st.session_state.init_status)

    if st.session_state.init_error:
        st.error(st.session_state.init_error)

    if st.session_state.last_init_result and not st.session_state.init_error:
        with st.expander("Initialization Result"):
            st.json(st.session_state.last_init_result)
    
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
    st.session_state.show_paths = st.checkbox("Show Movement Paths", value=True)
    auto_refresh = st.checkbox("Auto-refresh", value=True)

    if auto_refresh:
        refresh_rate = st.slider("Refresh rate (s)", 1, 10, POLL_INTERVAL)

    st.divider()

    st.subheader("🎨 Map Colors")
    st.session_state.color_obstacle = st.color_picker("Obstacle Color", value=st.session_state.get("color_obstacle", "#00AA00"))
    st.session_state.color_survivor = st.color_picker("Survivor Color", value=st.session_state.get("color_survivor", "#FF00FF"))
    st.session_state.color_hazard = st.color_picker("Hazard Color", value=st.session_state.get("color_hazard", "#FF4444"))
# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

# Top row: Grid + Step Log + Status
col_grid, col_step_log, col_metrics = st.columns([2, 1.2, 1])

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
    print("Calling render_grid_plotly", flush=True)
    if drone_paths is None:
        drone_paths = {}
    if not grid_data or "cells" not in grid_data:
        print("Returning None because no grid data or cells", flush=True)
        return None
    
    cells = grid_data.get("cells", [])
    height = len(cells)
    width = len(cells[0]) if cells else 0
    print(f"Grid size: {width}x{height}", flush=True)

    
    # Create grid visualization matrix (z values for heatmap)
    grid_visual = [[0 for _ in range(width)] for _ in range(height)]
    grid_labels = [[" " for _ in range(width)] for _ in range(height)]
    
    # Map cell types to numeric values for color coding
    cell_color_map = {
        ".": 0,   # Empty - light
        "X": 1,   # Hazard - red warning
        "S": 2,   # Survivor - orange target
        "#": 3,   # Obstacle - dark
        "scanned": 4,  # Scanned/Visited - unified color
    }

    # Map cell types to readable names for hover text
    cell_name_map = {
        ".": "Empty",
        "#": "Obstacle",
        "S": "Survivor",
        "X": "Hazard",
        "scanned": "Scanned/Visited",
    }

    # Fill the grid
    for row in cells:
        for cell in row:
            cx = cell.get("x", 0)
            cy = cell.get("y", 0)
            cell_type = cell.get("type", ".")
            is_scanned = cell.get("scanned", False)
            
            # Keep original colors for hazard, obstacle, and survivor
            # Only mark empty cells as scanned
            if is_scanned and cell_type == ".":
                grid_visual[cy][cx] = cell_color_map["scanned"]
                grid_labels[cy][cx] = f"({cx}, {cy})<br>Scanned/Visited"
            else:
                grid_visual[cy][cx] = cell_color_map.get(cell_type, 0)
                cell_label = cell_name_map.get(cell_type, "Unknown")
                if is_scanned:
                    grid_labels[cy][cx] = f"({cx}, {cy})<br>{cell_label}<br>(Scanned)"
                else:
                    grid_labels[cy][cx] = f"({cx}, {cy})<br>{cell_label}"
    
    # Create figure with custom colorscale
    fig = go.Figure()
    
    # Add heatmap for the grid
    fig.add_trace(go.Heatmap(
        z=grid_visual,
        zmin=0,
        zmax=4,
        colorscale=[
            [0.0, "#FFFFFF"],
            [0.125, "#FFFFFF"],
            [0.125, st.session_state.get("color_hazard", "#FF4444")],
            [0.375, st.session_state.get("color_hazard", "#FF4444")],
            [0.375, st.session_state.get("color_survivor", "#FF00FF")],
            [0.625, st.session_state.get("color_survivor", "#FF00FF")],
            [0.625, st.session_state.get("color_obstacle", "#00AA00")],
            [0.875, st.session_state.get("color_obstacle", "#00AA00")],
            [0.875, "#87CEEB"],
            [1.0, "#87CEEB"],
        ],
        colorbar=dict(
            title="Cell Type",
            tickvals=[0, 1, 2, 3, 4],
            ticktext=["Empty", "Hazard", "Survivor", "Obstacle", "Scanned/Visited"],
            len=0.5,
        ),
        showscale=True,
        hovertext=grid_labels,
        hoverinfo="text",
        name="Grid",
        xgap=1,
        ygap=1,
    ))

    # Base marker (charging station) at corner (0, 0) with unique color.
    fig.add_trace(go.Scatter(
        x=[0],
        y=[0],
        mode="markers+text",
        marker=dict(
            size=16,
            color="#FFD700",
            symbol="square",
            line=dict(width=2, color="#8B7500"),
        ),
        text=["BASE"],
        textposition="bottom center",
        textfont=dict(size=10, color="#8B7500"),
        hovertext=["Charging Base (0, 0)"],
        hoverinfo="text",
        name="Base",
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
                    color="magenta",
                    symbol="star",
                    line=dict(width=2, color="purple"),
                ),
                text=survivor_ids,
                textposition="top center",
                textfont=dict(size=11, color="purple"),
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
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title="Y Position",
            showgrid=False,
            zeroline=False,
        ),
        plot_bgcolor="#E5E5E5", # Use a gray background so white cells stand out and create lines
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
    survivors_identified = len(st.session_state.get("identified_survivors", []))

    # Calculate grid exploration
    if grid and "cells" in grid:
        total_cells = len(grid["cells"]) * len(grid["cells"][0])
        explored = sum(
            1 for row in grid["cells"]
            for cell in row if cell.get("scanned", False)
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

    **Survivors Identified:** {survivors_identified}
    """


def _step_log_to_row(index: int, text: str) -> dict:
    """Convert one step-log string to a compact table row."""
    msg = (text or "").strip()
    low = msg.lower()
    log_type = "AI"
    if "moved to" in low or low.startswith("movement result"):
        log_type = "MOVE"
    elif "survivor" in low and ("detected" in low or "discovered" in low):
        log_type = "DETECT"
    elif low.startswith("system event"):
        log_type = "EVENT"
    elif low.startswith("turn "):
        log_type = "TURN"
    elif low.startswith("selected strategy"):
        log_type = "STRATEGY"
    return {"Step": index, "Type": log_type, "Message": msg}


def render_step_log_panel(container, max_items: int = 80) -> None:
    """Render persistent AI step log in a compact table format."""
    with container.container():
        if not st.session_state.environment_initialized:
            return
        st.subheader("🧠 AI Step Log")
        logs = st.session_state.get("step_logs", [])
        if logs:
            tail = logs[-max_items:]
            rows = [_step_log_to_row(i + 1, msg) for i, msg in enumerate(tail)]
            st.dataframe(
                pd.DataFrame(rows), 
                use_container_width=False,
                hide_index=True,
                column_config={
                    "Message": st.column_config.TextColumn(
                        "Message",
                        width="large",
                    )
                }
            )
            
            if st.session_state.get("mission_complete", False):
                if st.button("👁️ View Step Log File", use_container_width=True):
                    view_log_modal("Step Log", "step_log.txt")
        else:
            st.caption("No step logs yet. Launch mission to see AI thought + decisions.")


def append_step_log(message: str) -> None:
    """Append step log message while avoiding immediate duplicates."""
    text = (message or "").strip()
    if not text:
        return
    logs = st.session_state.step_logs
    if not logs or logs[-1] != text:
        logs.append(text)


def interpret_mission_line(line: str) -> Optional[str]:
    """Convert raw mission output lines into plain-English step summaries."""
    text = (line or "").strip()
    if not text:
        return None

    upper = text.upper()
    if text.startswith("="):
        return None
    if upper.startswith("TURN "):
        return f"{text.title()} started."
    if upper == "EXECUTING MISSION PLAN":
        return "The AI started executing the mission plan."
    if upper == "EXECUTION COMPLETE":
        return "The AI completed this execution cycle."
    if upper.startswith("AI DECISION RECEIVED"):
        return "The AI finalized a plan for this turn and started execution."
    if text.startswith("[OK] Plan parsed successfully:"):
        strategy = text.split(":", 1)[1].strip().replace(" strategy", "")
        return f"Plan validation succeeded using strategy: {strategy}."
    if text.startswith("Thought:"):
        thought = text.split(":", 1)[1].strip()
        return f"AI thought: {thought}"
    if text.startswith("Strategy:"):
        return f"Selected strategy: {text.split(':', 1)[1].strip()}."
    if text.startswith("Assignments:"):
        return f"The AI created {text.split(':', 1)[1].strip()} assignments."
    if text.startswith("[drone-") and text.endswith("]"):
        return f"Now assigning tasks for {text[1:-1]}."
    if text.startswith("Action:"):
        action = text.split(":", 1)[1].strip().replace("_", " ")
        return f"Assigned action: {action}."
    if text.startswith("Reason:"):
        return f"Reason: {text.split(':', 1)[1].strip()}."
    if text.startswith("->") and "Searching" in text:
        return text.replace("->", "").strip().replace(" (continuous)", ".")
    if "[SURVIVOR] DETECTED at" in text:
        coords = text.split("at", 1)[1].strip()
        return f"A survivor was detected at {coords}."
    if text.startswith("[OK] moved"):
        moved = re.search(r"moved\s+(\d+)\s+steps", text)
        stopped = re.search(r"stopped by\s+([a-zA-Z_]+)", text)
        battery = re.search(r"battery:\s*(\d+)%", text)
        moved_steps = moved.group(1) if moved else "?"
        stop_reason = stopped.group(1).replace("_", " ") if stopped else "unknown reason"
        battery_pct = battery.group(1) if battery else "?"
        return f"Movement result: {moved_steps} steps, stopped by {stop_reason}, battery now {battery_pct}%."
    if text.startswith("Survivors discovered:"):
        return f"Summary: {text.lower()}."
    if re.match(r"^\d+\.\s*\(\d+\s*,\s*\d+\)", text):
        return f"Discovered survivor location {text}."

    keep_keywords = ["THOUGHT", "DECISION", "ACTION", "PLAN", "OBSERVATION"]
    if any(k in upper for k in keep_keywords):
        return f"AI update: {text}"

    return None


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
    with col_step_log:
        st.subheader("🧠 AI Step Log")
        live_step_log_df_placeholder = st.empty()
    with col_metrics:
        st.subheader("📊 Mission Status")
        live_status_txt = st.empty()
        st.subheader("🚁 Drone Fleet")
        live_drone_df = st.empty()
        st.subheader("📍 Identified Survivor Coordinates")
        live_survivor_df = st.empty()
    controller = MissionController(model_name=model_name)

    async def refresh_live_sections(render_map: bool = False) -> None:
        now = time.time()
        force_draw = render_map and (now - st.session_state.get("last_live_render_ts", 0.0) >= 0.01)
        state = await fetch_state_async()
        if not state:
            state = st.session_state.get("last_state")
        if not state:
            return

        fig = render_grid_plotly(
            state.get("grid", {}),
            state.get("drones", []),
            state.get("survivors", []),
            st.session_state.drone_paths if st.session_state.show_paths else {},
        )
        if fig and force_draw:
            # Updating grid using placeholder directly
            live_grid_placeholder.plotly_chart(
                fig,
                use_container_width=True,
                key=f"live_grid_plot_{st.session_state.live_plot_seq}",
            )
            st.session_state.live_plot_seq += 1
            st.session_state.last_live_render_ts = now

        # Update Step Log using placeholder directly
        logs = st.session_state.get("step_logs", [])
        if logs:
            tail = logs[-80:]
            rows = [_step_log_to_row(i + 1, msg) for i, msg in enumerate(tail)]
            live_step_log_df_placeholder.dataframe(
                pd.DataFrame(rows), 
                use_container_width=False, 
                hide_index=True,
                column_config={"Message": st.column_config.TextColumn("Message", width="large")}
            )
        else:
            live_step_log_df_placeholder.caption("No step logs yet. Launch mission to see AI thought + decisions.")

        # Update Metrics using placeholders directly
        live_status_txt.markdown(render_mission_summary(state))

        drone_df = render_drone_table(state.get("drones", []))
        if not drone_df.empty:
            live_drone_df.dataframe(drone_df, use_container_width=True, hide_index=True)
        else:
            live_drone_df.info("No drone data available")

        if st.session_state.identified_survivors:
            coords = sorted(
                st.session_state.identified_survivors,
                key=lambda c: (c["x"], c["y"]),
            )
            live_survivor_df.dataframe(pd.DataFrame(coords), use_container_width=True, hide_index=True)
        else:
            live_survivor_df.caption("No survivors identified yet.")

    try:
        status_placeholder.info("Initializing AI and starting mission...")
        
        full_log = ""
        # Clear out any previous paths directly here before we start rendering
        st.session_state.drone_paths = {}
        await refresh_live_sections(render_map=True)
        
        # Stream mission execution
        async for chunk in controller.stream_mission(briefing):
            if chunk.startswith("__EVENT__"):
                try:
                    event = json.loads(chunk[len("__EVENT__"):].strip())
                except json.JSONDecodeError:
                    event = {}

                event_type = event.get("type")
                if event_type == "movement_step":
                    step_line = (
                        f"{event.get('drone_id')} moved to ({event.get('x')}, {event.get('y')}). "
                        f"Battery is {event.get('battery')}%."
                    )
                    full_log += step_line + "\n"
                    append_step_log(step_line)
                    status_placeholder.info(
                        f"{event.get('drone_id')} moved to ({event.get('x')}, {event.get('y')})"
                    )
                elif event_type == "survivor_detected":
                    coord = {"x": int(event.get("x", -1)), "y": int(event.get("y", -1))}
                    coord_key = (coord["x"], coord["y"])
                    if coord_key not in st.session_state.identified_survivor_set:
                        st.session_state.identified_survivor_set.add(coord_key)
                        st.session_state.identified_survivors.append(coord)
                        step_line = f"A survivor was detected at ({coord['x']}, {coord['y']})."
                        full_log += step_line + "\n"
                        append_step_log(step_line)
                        status_placeholder.success(
                            f"Survivor identified at ({coord['x']}, {coord['y']})"
                        )
                elif event_type:
                    append_step_log(f"System event: {event_type}.")

                await refresh_live_sections(render_map=False)
            else:
                full_log += chunk
                should_render_map = False
                for raw_line in chunk.splitlines():
                    line = raw_line.strip()
                    if line.startswith("TURN ") or line == "EXECUTION COMPLETE":
                        should_render_map = True
                    interpreted = interpret_mission_line(raw_line)
                    if interpreted:
                        append_step_log(interpreted)

                if should_render_map:
                    await refresh_live_sections(render_map=True)

            await asyncio.sleep(0.01)

            st.session_state.mission_log = full_log
            with log_placeholder.container():
                st.markdown("### 📋 ARIA Mission Log")
                with st.container(height=600):
                    st.code(full_log[-5000:], language="text")

        # Final log update
        with log_placeholder.container():
            st.markdown("### 📋 ARIA Mission Log")
            with st.container(height=600):
                st.code(full_log, language="text")
        
        status_placeholder.success("Mission complete!")
        
    except Exception as e:
        full_log += f"\nERROR: {str(e)}\n"
        error_text = str(e)
        if "Connection refused" in error_text or "Failed to establish a new connection" in error_text:
            status_placeholder.error(
                "Mission failed: cannot connect to the selected model backend. If using Ollama, start it first (ollama serve)."
            )
        elif "OPENROUTER_API_KEY" in error_text:
            status_placeholder.error(
                "Mission failed: missing OPENROUTER_API_KEY for selected cloud model. Switch to Ollama Local or set the key in .env."
            )
        else:
            status_placeholder.error(f"Mission failed: {e}")
        with log_placeholder.container():
            st.markdown("### 📋 ARIA Mission Log")
            with st.container(height=600):
                st.code(full_log, language="text")

    st.session_state.mission_log = full_log
    return full_log


# ---------------------------------------------------------------------------
# Mission launch logic
# ---------------------------------------------------------------------------

if launch_btn:
    st.session_state.mission_active = True
    st.session_state.mission_complete = False
    st.session_state.use_snapshot_state = False
    st.session_state.identified_survivors = []
    st.session_state.identified_survivor_set = set()
    st.session_state.step_logs = []
    st.session_state.mission_log = ""
    st.session_state.live_plot_seq = 0
    
    # Reset log files on disk to prevent reading out-of-date runs
    with open("mission_log.txt", "w", encoding="utf-8") as f:
        f.write("")
    with open("step_log.txt", "w", encoding="utf-8") as f:
        f.write("")

    st.rerun()

if stop_btn:
    st.session_state.mission_active = False
    st.session_state.mission_complete = True
    # Freeze UI on latest known live state to avoid post-stop re-fetch artifacts.
    st.session_state.use_snapshot_state = True
    
    # Write full logs to disk even if manually stopped
    with open("mission_log.txt", "w", encoding="utf-8") as f:
        f.write(st.session_state.get("mission_log", ""))
    
    with open("step_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(st.session_state.get("step_logs", [])))

    st.rerun()

# Run agent if mission is active
if st.session_state.mission_active and not st.session_state.mission_complete:
    # Run the streaming agent with selected model
    agent_output = asyncio.run(run_stream_agent(mission_briefing, st.session_state.selected_model))
    st.session_state.mission_log = agent_output
    
    # Write full logs to disk
    with open("mission_log.txt", "w", encoding="utf-8") as f:
        f.write(agent_output)
    
    with open("step_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(st.session_state.get("step_logs", [])))

    st.session_state.mission_active = False
    st.session_state.mission_complete = True
    st.rerun()  # Force a clean redraw to show final state and avoid duplicate UI elements
    st.stop()

# Display mission log if available
if st.session_state.mission_log:
    with col_log:
        st.markdown("### 📋 ARIA Mission Log")
        with st.container(height=600):
            st.code(st.session_state.mission_log, language="text")

# ---------------------------------------------------------------------------
# Grid and status display
# ---------------------------------------------------------------------------

state = None

state: Optional[dict] = None
is_live_streaming = st.session_state.mission_active and not st.session_state.mission_complete

if not st.session_state.environment_initialized:
    col_grid.info("🔧 Please initialize the environment using the Control Panel on the left.")
    render_step_log_panel(col_step_log)
elif is_live_streaming:
    # Live sections are rendered inside run_stream_agent; skip static panels
    pass
else:
    if st.session_state.use_snapshot_state and st.session_state.last_state:
        state = st.session_state.last_state
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

        render_step_log_panel(col_step_log)

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
        render_step_log_panel(col_step_log)

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

# ---------------------------------------------------------------------------

