"""
agent.py — LangChain AI Command Agent (OpenRouter)
Member 1 (Agent/AI) workspace.

Connects to the FastMCP server, loads drone tools via the
langchain-mcp-adapters bridge, and drives an OpenRouter ReAct agent loop
with multi-turn memory, mission tracking, and streaming support.

Prerequisites:
    - Copy .env.example → .env and set OPENROUTER_API_KEY.
    - pip install -r requirements.txt

Run standalone test:
    python -m orchestrator.agent
"""

import asyncio
import os
import json
from typing import Optional, AsyncGenerator, Callable, Any
import httpx

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from langchain_openai import ChatOpenAI

from orchestrator.prompts import MISSION_START_PROMPT
from orchestrator.memory import ConversationMemoryBuffer, MissionMemory
from orchestrator.mission import MissionMonitor, MissionStatus
from orchestrator.model_loader import get_model_by_name, get_default_model

# ---------------------------------------------------------------------------
# Load environment variables from .env (ignored by git)
# ---------------------------------------------------------------------------
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise EnvironmentError(
        "OPENROUTER_API_KEY is not set. "
        "Copy .env.example to .env and add your key from "
        "https://openrouter.ai/keys"
    )
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

# Server URLs
SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
TOOLS_BASE_URL = f"{SERVER_URL}/tools"

# Direct HTTP client for tool calls
async def call_tool(tool_name: str, **params) -> dict:
    """Call a tool via REST endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if tool_name == "initialize_mission":
                url = f"{TOOLS_BASE_URL}/initialize_mission"
                response = await client.post(url, params=params)
            elif tool_name == "get_swarm_state":
                url = f"{TOOLS_BASE_URL}/get_swarm_state"
                response = await client.get(url)
            elif tool_name == "move_drone":
                url = f"{TOOLS_BASE_URL}/move_drone"
                response = await client.post(url, params=params)
            elif tool_name == "move_continuous_until_stopped":
                url = f"{TOOLS_BASE_URL}/move_continuous_until_stopped"
                response = await client.post(url, params=params)
            elif tool_name == "scan_area":
                url = f"{TOOLS_BASE_URL}/scan_area"
                response = await client.post(url, params=params)
            elif tool_name == "rescue_survivor":
                url = f"{TOOLS_BASE_URL}/rescue_survivor"
                response = await client.post(url, params=params)
            elif tool_name == "return_to_base":
                url = f"{TOOLS_BASE_URL}/return_to_base"
                response = await client.post(url, params=params)
            elif tool_name == "get_survivor_counts":
                url = f"{TOOLS_BASE_URL}/get_survivor_counts"
                response = await client.get(url)
            elif tool_name == "get_drone_state":
                url = f"{TOOLS_BASE_URL}/get_drone_state"
                response = await client.get(url, params=params)
            elif tool_name == "reset_mission":
                url = f"{TOOLS_BASE_URL}/reset_mission"
                response = await client.post(url)
            elif tool_name == "get_exploration_status":
                url = f"{TOOLS_BASE_URL}/get_exploration_status"
                response = await client.get(url)
            elif tool_name == "get_direction_to_explore":
                url = f"{TOOLS_BASE_URL}/get_direction_to_explore"
                response = await client.post(url, params=params)
            elif tool_name == "get_unscanned_zones":
                url = f"{TOOLS_BASE_URL}/get_unscanned_zones"
                response = await client.get(url)
            else:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def create_language_tools():
    """Create LangChain tool definitions that call REST endpoints."""
    from langchain_core.tools import tool
    
    @tool
    def initialize_mission(width: int = 20, height: int = 20, drone_count: int = 3, survivor_count: int = 5) -> str:
        """Initialize a new rescue mission"""
        result = asyncio.run(call_tool("initialize_mission", width=width, height=height, drone_count=drone_count, survivor_count=survivor_count))
        return json.dumps(result)
    
    @tool
    def get_swarm_state() -> str:
        """Get the full swarm state and grid"""
        result = asyncio.run(call_tool("get_swarm_state"))
        return json.dumps(result)
    
    @tool
    def move_drone(drone_id: str, dx: int, dy: int) -> str:
        """Move a drone by (dx, dy)"""
        result = asyncio.run(call_tool("move_drone", drone_id=drone_id, dx=dx, dy=dy))
        return json.dumps(result)
    
    @tool
    def move_continuous_until_stopped(drone_id: str, direction_x: int, direction_y: int) -> str:
        """⭐ OPTIMIZED: Move a drone continuously in a direction until hitting boundary, obstacle, or low battery. Returns full path in single API call."""
        result = asyncio.run(call_tool("move_continuous_until_stopped", drone_id=drone_id, direction_x=direction_x, direction_y=direction_y))
        return json.dumps(result)
    
    @tool
    def scan_area(drone_id: str, radius: int = 2) -> str:
        """Scan the area around a drone"""
        result = asyncio.run(call_tool("scan_area", drone_id=drone_id, radius=radius))
        return json.dumps(result)
    
    @tool
    def rescue_survivor(drone_id: str, target_x: int, target_y: int) -> str:
        """Rescue a survivor at a location"""
        result = asyncio.run(call_tool("rescue_survivor", drone_id=drone_id, target_x=target_x, target_y=target_y))
        return json.dumps(result)
    
    @tool
    def return_to_base(drone_id: str) -> str:
        """Return a drone to base"""
        result = asyncio.run(call_tool("return_to_base", drone_id=drone_id))
        return json.dumps(result)
    
    @tool
    def get_survivor_counts() -> str:
        """Get counts of survivors"""
        result = asyncio.run(call_tool("get_survivor_counts"))
        return json.dumps(result)
    
    @tool
    def get_drone_state(drone_id: str) -> str:
        """Get state of a single drone"""
        result = asyncio.run(call_tool("get_drone_state", drone_id=drone_id))
        return json.dumps(result)
    
    @tool
    def get_exploration_status() -> str:
        """🔴 PRIORITY: Get real-time exploration status with per-drone guidance toward unscanned areas"""
        result = asyncio.run(call_tool("get_exploration_status"))
        return json.dumps(result)
    
    @tool
    def get_direction_to_explore(drone_id: str) -> str:
        """🔴 PRIORITY: Get optimal direction for a drone to explore unscanned areas. Shows nearest unscanned cell & escape routes for trapped drones."""
        result = asyncio.run(call_tool("get_direction_to_explore", drone_id=drone_id))
        return json.dumps(result)
    
    @tool
    def get_unscanned_zones() -> str:
        """Get all unscanned cells for strategic multi-drone coordination"""
        result = asyncio.run(call_tool("get_unscanned_zones"))
        return json.dumps(result)
    
    return [
        initialize_mission,
        get_swarm_state,
        move_drone,
        move_continuous_until_stopped,
        scan_area,
        rescue_survivor,
        return_to_base,
        get_survivor_counts,
        get_drone_state,
        get_exploration_status,
        get_direction_to_explore,
        get_unscanned_zones,
    ]

# ---------------------------------------------------------------------------
# System prompt — enforces Chain-of-Thought reasoning before every tool call
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are ARIA (Autonomous Rescue Intelligence Agent), an AI Command Agent \
coordinating a swarm of rescue drones across a 2D disaster-zone grid.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 MISSION OBJECTIVES (in priority order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 🎯 EXPLORE: Systematically explore the grid to reveal all unscanned cells.
2. 🔍 DETECT: Find all survivors (S) and hazards (X).
3. 💪 RESCUE: Rescue every survivor and return them to base at (0, 0).
4. 🔋 MAINTAIN: Keep all drones operational — never let battery reach 0%.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 **NO IDLE DRONES ALLOWED** (CRITICAL RULE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ FORBIDDEN: "Action: idle | Reason: Temporarily idle: repeatedly stuck"
✓ REQUIRED: Every drone must move toward nearest unscanned area or pursue rescue.
✓ IF TRAPPED: All adjacent cells scanned → Force movement toward distant unscanned area.
✓ IF DONE: Exploration >= 95% → Transition fully to rescue operations.

RULE: You are NEVER allowed to output "idle" status. If a drone appears idle:
  → Check if it's trapped via get_direction_to_explore(drone_id)
  → If trapped (is_trapped=true), use the escape direction (dx, dy) returned
  → Move drone using move_continuous_until_stopped() with that direction
  → This FORCES the drone OUT of explored zone toward new territory
  → NEVER let a drone sit idle—always have it moving toward a goal

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 EXPLORATION PROTOCOL (MANDATORY EVERY TURN)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
At the START of every turn, ALWAYS do these steps (in order):

STEP 1: Assess exploration progress
  → Call get_exploration_status()
  → Check: scanned_percentage (goal >= 95%)
  → For EACH drone, note:
     • nearby_unscanned_count (0 = all local areas explored)
     • nearest_unscanned (target location)
     • all_adjacent_scanned (TRUE = drone is trapped)

STEP 2: For each drone, determine its action
  ✓ IF scanned_percentage < 95%:
    • MUST call get_direction_to_explore(drone_id)
    • Read its recommendation field:
      - "move_in_direction" → Execute movement using returned (dx,dy)
      - "trapped_seek_escape" → Drone is trapped! Use (dx,dy) to escape
        * "Trapped" = all adjacent cells already scanned
        * FORCE movement using move_continuous_until_stopped(drone_id, dx, dy)
        * This breaks drone OUT of explored zone toward new territory
      - "exploration_complete" → No more unscanned cells, switch to rescue
    • NEVER mark a drone idle—always give it a direction

  ✓ IF scanned_percentage >= 95%:
    • Exploration phase complete
    • Transition entirely to rescue operations
    • Use get_nearest_survivor() to find targets
    • Route highest-battery drones to survivors

STEP 3: Execute movements and scanning
  → For exploration: move_continuous_until_stopped() (fast path exploration)
  → For rescue: move_drone() (precise positioning)
  → Follow all movements with scan_area() to mark cells as explored

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔐 CHAIN-OF-THOUGHT PROTOCOL (STRICTLY ENFORCED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before EVERY tool call, output a THOUGHT block:

  THOUGHT:
    [Exploration Status]
    - Scanned: X% | Unscanned: Y cells | Goal: >= 95%
    
    [Drone Analysis]
    - [drone-1] @ (x,y), bat=Z%, nearby_unscanned=N, nearest=(a,b), trapped=YES/NO
    - [drone-2] @ (x,y), bat=Z%, nearby_unscanned=N, nearest=(a,b), trapped=YES/NO
    - [drone-3] @ (x,y), bat=Z%, nearby_unscanned=N, nearest=(a,b), trapped=YES/NO
    
    [Decision Logic]
    - Drone-1: [not trapped/low unscanned] → move toward (a,b)
    - Drone-2: [TRAPPED] → force escape using get_direction_to_explore result
    - Drone-3: [high battery] → assign to furthest unscanned region
    
    [Actions This Turn]
    - get_direction_to_explore() for each trapped drone
    - move_continuous_until_stopped() or move_drone()
    - scan_area() to mark explored cells

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 STRICT OPERATIONAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. EXPLORATION FIRST: Always call get_exploration_status() at turn start
2. NO IDLE DRONES: Every drone must move toward a goal (unscanned or rescue target)
3. TRAP DETECTION: Call get_direction_to_explore(drone_id) if exploring
   - Returns (dx,dy) even if drone is trapped
   - Use that direction in move_continuous_until_stopped() to escape trapped zones
4. NEVER WANDER: Don't move drones randomly—always toward unscanned cells
5. BATTERY MANAGEMENT:
   - drone.battery < 20% → immediate return_to_base()
   - Assign longest routes to highest-battery drones
   - Never let battery reach 0%
6. CARGO HANDLING:
   - drone.cargo != null → MUST go to base (0,0) first
   - Call return_to_base() when at base with cargo
7. COLLISION PREVENTION: Never move two drones into same cell same turn
8. TOOL CONSTRAINTS:
   - move_continuous_until_stopped(drone_id, direction_x, direction_y):
     * direction_x must be -1, 0, or 1
     * direction_y must be -1, 0, or 1
   - move_drone(drone_id, dx, dy):
     * dx must be -1, 0, or 1
     * dy must be -1, 0, or 1
   - get_direction_to_explore(drone_id) returns (dx, dy)—execute it

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ EXPLORATION TOOLS (NEW - USE EVERY TURN)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Three priority tools for efficient exploration:

1️⃣ get_exploration_status()
   → Get scanned_percentage and per-drone guidance
   → Call ONCE per turn (not per drone)
   → Returns: scanned %, total unscanned count, per-drone data

2️⃣ get_direction_to_explore(drone_id)
   → Get optimal movement direction toward unscanned
   → Returns: (dx, dy) to move, nearest_unscanned target, is_trapped flag
   → CRITICAL: Even if trapped, returns escape direction in (dx, dy)
   → Call for each drone during exploration phase

3️⃣ get_unscanned_zones()
   → Get ALL unscanned cell coordinates
   → Use for strategic multi-drone coordination
   → Helps identify exploration clusters

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 RESPONSE FORMAT (CONCISE & ACTIONABLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After tool calls, output status report:

  STATUS REPORT:
    🗺️  Exploration: X.X% | Y unscanned cells remaining
    🚁 Drones: [drone-1 @ (x,y) bat=Z% | drone-2 @ (x,y) bat=Z% | drone-3 @ (x,y) bat=Z%]
    🆘 Survivors: F found | R rescued (of T total)
    ➡️  Next: <brief action summary>
    
    (NO idle actions - all drones have movement/rescue goals)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💾 MISSION MEMORY (Persistent Context)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recall these facts from previous turns:
{mission_context}
"""

# ---------------------------------------------------------------------------
# Agent factory with memory integration
# ---------------------------------------------------------------------------

class MultiTurnAgent:
    """
    Wraps LangChain agent with multi-turn memory and mission tracking.
    """

    def __init__(self):
        self.memory = ConversationMemoryBuffer(max_message_pairs=20)
        self.mission = MissionMonitor()
        self.streaming = False

    def _build_prompt(self) -> ChatPromptTemplate:
        """
        Build the ReAct-compatible prompt template with memory context.
        """
        # Get current mission context
        mission_context = self.memory.mission_memory.to_context_string()
        system_prompt = SYSTEM_PROMPT.format(mission_context=mission_context)

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

    async def run_cycle(
        self,
        mission_briefing: str = "",
        grid_width: int = 20,
        grid_height: int = 20,
        model_name: str = None,
    ) -> str:
        """
        Execute one full agent reasoning and action cycle using plain-text ReAct loop.
        
        Args:
            mission_briefing: Optional mission instructions
            grid_width: Grid width
            grid_height: Grid height
            model_name: Display name of model to use (e.g., "Nvidia Nemotron 3 Super 120B (Free)")
        """
        try:
            # Get model configuration
            if model_name:
                model_config = get_model_by_name(model_name)
                if not model_config:
                    model_config = get_default_model()
            else:
                model_config = get_default_model()
            
            llm = ChatOpenAI(
                model=model_config["model_id"],
                api_key=OPENROUTER_API_KEY,
                base_url=model_config["base_url"],
                temperature=0,
            )
            
            # Get mission context
            mission_context = self.memory.mission_memory.to_context_string()
            system_prompt = SYSTEM_PROMPT.format(mission_context=mission_context)
            
            # Add tool list to system prompt
            tool_list = """
Available Tools (call them using this format: [TOOL: tool_name(param1=value1, param2=value2)]
- initialize_mission(width=20, height=20, drone_count=3, survivor_count=5)
- get_swarm_state()
- move_drone(drone_id, dx, dy) - Move one step
- move_continuous_until_stopped(drone_id, direction_x, direction_y) ⭐ OPTIMIZED - Explore continuously, get full path in 1 call
- scan_area(drone_id, radius=2)
- rescue_survivor(drone_id, target_x, target_y)
- return_to_base(drone_id)
- get_survivor_counts()
- get_drone_state(drone_id)
"""
            system_prompt += "\n" + tool_list
            
            # Build user input
            user_input = MISSION_START_PROMPT.format(
                width=grid_width, height=grid_height
            )
            if mission_briefing:
                user_input += f"\n\nAdditional briefing: {mission_briefing}"
            
            # ReAct loop with plain text messages
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input)
            ]
            
            full_output = ""
            max_iterations = 15
            
            for iteration in range(max_iterations):
                # Get response from LLM
                response = await llm.ainvoke(messages)
                response_text = response.content if hasattr(response, 'content') else str(response)
                full_output += "\n" + response_text
                
                # Add assistant response to messages
                messages.append(AIMessage(content=response_text))
                
                # Parse tool calls from response (format: [TOOL: tool_name(args)])
                import re
                tool_pattern = r'\[TOOL:\s*(\w+)\((.*?)\)\]'
                matches = re.findall(tool_pattern, response_text)
                
                if matches:
                    tool_results = []
                    for tool_name, args_str in matches:
                        # Parse arguments
                        try:
                            # Simple argument parsing
                            args = {}
                            if args_str.strip():
                                for arg_pair in args_str.split(','):
                                    if '=' in arg_pair:
                                        key, val = arg_pair.split('=', 1)
                                        key = key.strip()
                                        val = val.strip().strip('"\'')
                                        # Try to convert to appropriate type
                                        if val.isdigit():
                                            args[key] = int(val)
                                        elif val == 'True':
                                            args[key] = True
                                        elif val == 'False':
                                            args[key] = False
                                        else:
                                            args[key] = val
                            
                            # Call the tool
                            result = await call_tool(tool_name, **args)
                            result_text = json.dumps(result) if isinstance(result, dict) else str(result)
                            tool_results.append(f"Tool {tool_name} returned: {result_text}")
                        except Exception as e:
                            tool_results.append(f"Tool {tool_name} error: {str(e)}")
                    
                    # Add tool results to message history
                    if tool_results:
                        tool_feedback = "\n".join(tool_results)
                        full_output += f"\n\n{tool_feedback}\n\n(Please continue with next action or reasoning)"
                        messages.append(HumanMessage(content=f"Tool Results:\n{tool_feedback}"))
                else:
                    # No tool calls found, agent is done
                    break
            
            # Record in memory
            self.memory.add_ai_message(full_output)
            return full_output

        except Exception as e:
            error_msg = f"Agent error: {str(e)}"
            import traceback
            traceback.print_exc()
            return error_msg

    async def stream_cycle(
        self,
        mission_briefing: str = "",
        grid_width: int = 20,
        grid_height: int = 20,
        model_name: str = None,
    ) -> AsyncGenerator[str, None]:
        """
        Execute one cycle with streaming output (token-by-token) using plain-text ReAct.
        
        Args:
            mission_briefing: Optional mission instructions
            grid_width: Grid width
            grid_height: Grid height
            model_name: Display name of model to use
        """
        try:
            # Get model configuration
            if model_name:
                model_config = get_model_by_name(model_name)
                if not model_config:
                    model_config = get_default_model()
            else:
                model_config = get_default_model()
            
            llm = ChatOpenAI(
                model=model_config["model_id"],
                api_key=OPENROUTER_API_KEY,
                base_url=model_config["base_url"],
                temperature=0,
                streaming=True,
            )

            # Get mission context
            mission_context = self.memory.mission_memory.to_context_string()
            system_prompt = SYSTEM_PROMPT.format(mission_context=mission_context)
            
            # Add tool list to system prompt
            tool_list = """
Available Tools (call them using this format: [TOOL: tool_name(param1=value1, param2=value2)]
- initialize_mission(width=20, height=20, drone_count=3, survivor_count=5)
- get_swarm_state()
- move_drone(drone_id, dx, dy) - Move one step
- move_continuous_until_stopped(drone_id, direction_x, direction_y) ⭐ OPTIMIZED - Explore continuously, get full path in 1 call
- scan_area(drone_id, radius=2)
- rescue_survivor(drone_id, target_x, target_y)
- return_to_base(drone_id)
- get_survivor_counts()
- get_drone_state(drone_id)
"""
            system_prompt += "\n" + tool_list

            # Build user input
            user_input = MISSION_START_PROMPT.format(
                width=grid_width, height=grid_height
            )
            if mission_briefing:
                user_input += f"\n\nAdditional briefing: {mission_briefing}"

            # ReAct loop with plain text messages and streaming
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_input)
            ]
            
            full_output = ""
            max_iterations = 15
            
            for iteration in range(max_iterations):
                # Stream response from LLM with full message context
                stream_response = ""
                try:
                    async for chunk in llm.astream(messages[-1] if len(messages) > 1 else HumanMessage(content=user_input)):
                        if hasattr(chunk, 'content') and chunk.content:
                            content = chunk.content
                            stream_response += content
                            full_output += content
                            yield content
                except Exception as e:
                    yield f"\n[Stream error: {str(e)}]\n"
                    break
                
                if not stream_response:
                    break
                    
                messages.append(AIMessage(content=stream_response))
                
                # Parse tool calls from response
                import re
                tool_pattern = r'\[TOOL:\s*(\w+)\((.*?)\)\]'
                matches = re.findall(tool_pattern, stream_response)
                
                if matches:
                    tool_results = []
                    for tool_name, args_str in matches:
                        try:
                            # Simple argument parsing
                            args = {}
                            if args_str.strip():
                                for arg_pair in args_str.split(','):
                                    if '=' in arg_pair:
                                        key, val = arg_pair.split('=', 1)
                                        key = key.strip()
                                        val = val.strip().strip('"\'')
                                        if val.isdigit():
                                            args[key] = int(val)
                                        elif val == 'True':
                                            args[key] = True
                                        elif val == 'False':
                                            args[key] = False
                                        else:
                                            args[key] = val
                            
                            # Call the tool
                            result = await call_tool(tool_name, **args)
                            result_text = json.dumps(result) if isinstance(result, dict) else str(result)
                            tool_results.append(f"Tool {tool_name} returned: {result_text}")
                        except Exception as e:
                            tool_results.append(f"Tool {tool_name} error: {str(e)}")
                    
                    # Add tool results to message history
                    if tool_results:
                        tool_feedback = "\n".join(tool_results)
                        yield f"\n\n{tool_feedback}\n\n"
                        full_output += f"\n\n{tool_feedback}\n\n"
                        messages.append(HumanMessage(content=f"Tool Results:\n{tool_feedback}"))
                else:
                    # No tool calls found, agent is done
                    break
            
            # Record in memory
            self.memory.add_ai_message(full_output)

        except Exception as e:
            yield f"\n[ERROR: {str(e)}]\n"


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

async def run_agent(mission_briefing: str = "", model_name: str = None) -> str:
    """
    Run one full agent cycle using REST endpoints.

    Args:
        mission_briefing: Optional extra instructions.
        model_name: Display name of model to use (e.g., "Nvidia Nemotron 3 Super 120B (Free)")

    Returns:
        The agent's final text response for this cycle.
    """
    agent = MultiTurnAgent()
    return await agent.run_cycle(mission_briefing, model_name=model_name)


async def stream_agent(mission_briefing: str = "", model_name: str = None) -> AsyncGenerator[str, None]:
    """
    Stream one full agent cycle using REST endpoints (token-by-token).
    
    Suitable for real-time UI rendering. Yields text chunks as they are generated.

    Args:
        mission_briefing: Optional extra instructions.
        model_name: Display name of model to use

    Yields:
        Token chunks from the agent's reasoning and actions.
    """
    agent = MultiTurnAgent()
    async for chunk in agent.stream_cycle(mission_briefing, model_name=model_name):
        yield chunk


# ---------------------------------------------------------------------------
# Quick local test — run with:  python -m orchestrator.agent
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _main():
        print("Connecting to server at:", SERVER_URL)
        print("=" * 70)
        print("Starting ARIA Agent (non-streaming mode)...")
        print("=" * 70)
        output = await run_agent()
        print("\n" + "=" * 70)
        print("ARIA FINAL RESPONSE")
        print("=" * 70)
        print(output)

    asyncio.run(_main())
