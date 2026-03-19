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
    ]

# ---------------------------------------------------------------------------
# System prompt — enforces Chain-of-Thought reasoning before every tool call
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are ARIA (Autonomous Rescue Intelligence Agent), an AI Command Agent \
coordinating a swarm of rescue drones across a 2D disaster-zone grid.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSION OBJECTIVES (in priority order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Systematically explore the grid to reveal all cells.
2. Detect survivors (S) and hazards (X).
3. Rescue every survivor and return them to base at (0, 0).
4. Keep all drones operational — never let battery reach 0%.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT CHAIN-OF-THOUGHT PROTOCOL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before EVERY tool call you MUST output a reasoning block in this exact format:

  THOUGHT:
    - Current state summary: <brief>
    - Constraint check: <battery levels, cargo status, hazard proximity>
    - Decision: <what you will do and WHY>
    - Example: "Drone-2 has 18% battery and is at (4,7). It is below the 20%
      threshold, so I am ordering it to return to base before assigning any
      rescue task."

Only AFTER the THOUGHT block should you invoke a tool.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPERATIONAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Always call get_swarm_state() at the start of each turn to ground yourself.
- For EXPLORATION: Use move_continuous_until_stopped() to sweep grid sections (returns full path in 1 call)
  * This prevents step-by-step API overhead (1 continuous move = 10-20 individual moves)
  * Example: move_continuous_until_stopped("Drone-1", 1, 0) explores east until obstacle/battery/detection
- For RESCUE: Use move_drone() for precise positioning after survivor detected (1 step at a time)
- Scan an area before routing a drone into an unexplored region.
- Assign drones with the HIGHEST battery to the longest routes.
- A drone carrying cargo (cargo != null) must travel to base (0,0) FIRST.
- If any drone's battery < 20 %, immediately issue a return-to-base order.
- Never move two drones to the same cell in the same turn.
- direction_x and direction_y for move_continuous_until_stopped() must each be exactly -1, 0, or 1.
- dx and dy values for move_drone must each be exactly -1, 0, or 1.
- When a survivor is detected, use rescue_survivor() when adjacent.
- When a drone reaches base with cargo, use return_to_base() to complete.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API OPTIMIZATION STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use move_continuous_until_stopped() for exploration phases:
✓ Minimize API overhead: 1 API call per drone search = 3 drones = 3 calls/turn
  vs 10+ API calls per turn with step-by-step movement
✓ Returns full path array + stop reason in single response
✓ Stop reasons tell you what the drone found:
  - "boundary" = hit grid edge, scan next direction
  - "obstacle" = can't continue, try different direction
  - "detected_survivor" = found a survivor, move adjacent and rescue
  - "detected_hazard" = found hazard, avoid this direction
  - "battery" = running low, return to base
✓ Use returned path coordinates to understand coverage

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After all tool calls for a turn, output a concise status report:
  STATUS REPORT:
    • Explored: X%  |  Survivors found: N  |  Rescued: M
    • Drone statuses: <id> @ (x,y) bat=Z% [cargo/status]
    • Next planned actions: <brief>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MISSION MEMORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
