"""
agent.py — LangChain AI Command Agent (Gemini)
Orchestrates rescue drones via MCP REST tools using native LangChain tool-calling.

Run standalone:
    python -m orchestrator.agent
"""

import asyncio
import json
import os
import time
from typing import AsyncGenerator

import httpx
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from orchestrator.memory import ConversationMemoryBuffer
from orchestrator.mission import MissionMonitor
from orchestrator.prompts import MISSION_START_PROMPT

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise EnvironmentError(
        "OPENROUTER_API_KEY is not set. Add it to .env. Get a free key at https://openrouter.ai/keys"
    )

# Free model on OpenRouter — change to any model slug from https://openrouter.ai/models?q=free
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-r1-0528:free")

SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8001")
TOOLS_BASE_URL = f"{SERVER_URL}/tools"

# ---------------------------------------------------------------------------
# REST tool caller (sync — called from within running event loop via bind_tools)
# ---------------------------------------------------------------------------

GET_TOOLS = {"get_swarm_state", "get_survivor_counts", "get_drone_state"}

def call_tool_sync(tool_name: str, **params) -> dict:
    """Synchronous MCP REST tool call. Safe to use inside LangChain tool functions."""
    try:
        url = f"{TOOLS_BASE_URL}/{tool_name}"
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, params=params) if tool_name in GET_TOOLS else client.post(url, params=params)
            return r.json() if r.status_code == 200 else {"success": False, "error": r.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# LangChain tools (native bind_tools pattern)
# ---------------------------------------------------------------------------

def build_tools() -> list:
    """Build LangChain tool definitions that call MCP REST endpoints."""

    @tool
    def get_swarm_state() -> str:
        """Get the full swarm state: all drone positions, battery levels, cargo, and grid layout."""
        return json.dumps(call_tool_sync("get_swarm_state"))

    @tool
    def move_drone(drone_id: str, dx: int, dy: int) -> str:
        """Move a drone one step. dx and dy must each be -1, 0, or 1. Costs 1% battery."""
        return json.dumps(call_tool_sync("move_drone", drone_id=drone_id, dx=dx, dy=dy))

    @tool
    def scan_area(drone_id: str, radius: int = 2) -> str:
        """Scan cells within radius of a drone. Returns list of detected survivors (S), hazards (X), obstacles (#)."""
        return json.dumps(call_tool_sync("scan_area", drone_id=drone_id, radius=radius))

    @tool
    def rescue_survivor(drone_id: str, target_x: int, target_y: int) -> str:
        """Pick up a survivor at (target_x, target_y). Drone must be adjacent (Manhattan distance <= 1)."""
        return json.dumps(call_tool_sync("rescue_survivor", drone_id=drone_id, target_x=target_x, target_y=target_y))

    @tool
    def return_to_base(drone_id: str) -> str:
        """Deliver cargo to base. Drone must be physically at (0, 0). Recharges battery after delivery."""
        return json.dumps(call_tool_sync("return_to_base", drone_id=drone_id))

    @tool
    def get_survivor_counts() -> str:
        """Get survivor counts: on_grid (still to find), in_cargo (being carried), rescued (at base)."""
        return json.dumps(call_tool_sync("get_survivor_counts"))

    @tool
    def get_drone_state(drone_id: str) -> str:
        """Get position, battery, status, and cargo for a single drone."""
        return json.dumps(call_tool_sync("get_drone_state", drone_id=drone_id))

    return [get_swarm_state, move_drone, scan_area, rescue_survivor, return_to_base, get_survivor_counts, get_drone_state]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are ARIA (Autonomous Rescue Intelligence Agent), coordinating a rescue drone swarm on a 2D disaster-zone grid.

MISSION OBJECTIVES (priority order):
1. Systematically explore the grid to find all survivors.
2. Rescue every survivor and return them to base at (0, 0).
3. Keep all drones operational — return to base before battery hits 0%.
4. Continue until ALL survivors are rescued or all drones depleted.

CHAIN-OF-THOUGHT PROTOCOL:
Before every tool call, output a THOUGHT block:
  THOUGHT:
    - State: <brief current situation>
    - Constraint: <battery levels, cargo, hazards>
    - Decision: <what and why>

OPERATIONAL RULES:
- Start each turn with get_swarm_state() to ground yourself.
- dx and dy for move_drone must each be exactly -1, 0, or 1.
- Drone with cargo must go to (0,0) and call return_to_base() to complete rescue.
- Battery < 20% -> immediately return to base, no exceptions.
- Never move two drones to the same cell in the same turn.
- Use scan_area() before entering unexplored regions.
- Assign highest-battery drones to longest routes.

After all tool calls, output:
  STATUS REPORT:
    - Survivors: rescued/total (use get_survivor_counts)
    - Drones: <id> @ (x,y) bat=Z% [cargo/status]
    - Next actions: <brief>
    - Mission status: ONGOING (if survivors remain) or COMPLETE (if all rescued)

Mission memory from prior turns:
{mission_context}
"""


# ---------------------------------------------------------------------------
# Multi-turn agent
# ---------------------------------------------------------------------------

class MultiTurnAgent:
    """LangChain agent with native tool-calling, multi-turn memory, and streaming."""

    def __init__(self):
        self.memory = ConversationMemoryBuffer(max_message_pairs=20)
        self.mission = MissionMonitor()
        self._tools = build_tools()
        self._tool_map = {t.name: t for t in self._tools}

    def _make_llm(self, streaming: bool = False):
        return ChatOpenAI(
            model=OPENROUTER_MODEL,
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0,
            streaming=streaming,
        )

    def _build_messages(self, user_input: str) -> list:
        mission_context = self.memory.mission_memory.to_context_string()
        system = SYSTEM_PROMPT.format(mission_context=mission_context)
        return [SystemMessage(content=system), HumanMessage(content=user_input)]

    async def _invoke_with_retry(self, llm, messages: list, max_retries: int = 5):
        """Invoke LLM with exponential backoff on rate limit errors."""
        for attempt in range(max_retries):
            try:
                return await llm.ainvoke(messages)
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait = 2 ** attempt * 15  # 15s, 30s, 60s...
                    print(f"Rate limited. Waiting {wait}s before retry {attempt + 1}/{max_retries}...")
                    await asyncio.sleep(wait)
                else:
                    raise
        raise RuntimeError("Max retries exceeded due to rate limiting.")

    async def _stream_with_retry(self, llm, messages: list, max_retries: int = 5):
        """Kept for compatibility — yields nothing, stream_cycle uses ainvoke."""
        return
        yield  # make it an async generator

    def _execute_tool_calls(self, tool_calls: list) -> list[ToolMessage]:
        """Execute all tool calls and return ToolMessage results."""
        results = []
        for tc in tool_calls:
            name = tc["name"]
            args = tc["args"]
            call_id = tc.get("id", name)
            
            # Validate args not empty
            if not args or args == {}:
                result = json.dumps({"success": False, "error": f"Empty arguments for {name}"})
                results.append(ToolMessage(content=result, tool_call_id=call_id))
                continue
            
            t = self._tool_map.get(name)
            if t:
                try:
                    result = t.invoke(args)
                except Exception as e:
                    result = json.dumps({"success": False, "error": str(e)})
            else:
                result = json.dumps({"success": False, "error": f"Unknown tool: {name}"})
            results.append(ToolMessage(content=result, tool_call_id=call_id))
        return results

    async def run_cycle(self, mission_briefing: str = "") -> str:
        """Run one full agent cycle (non-streaming)."""
        llm = self._make_llm(streaming=False).bind_tools(self._tools)
        user_input = MISSION_START_PROMPT.format(width=20, height=20)
        if mission_briefing:
            user_input += f"\n\nAdditional briefing: {mission_briefing}"

        messages = self._build_messages(user_input)
        full_output = ""
        max_iterations = 20

        for _ in range(max_iterations):
            response = await self._invoke_with_retry(llm, messages)
            messages.append(response)

            text = response.content if isinstance(response.content, str) else ""
            full_output += text + "\n"

            if not response.tool_calls:
                break

            tool_msgs = self._execute_tool_calls(response.tool_calls)
            messages.extend(tool_msgs)
            for tm in tool_msgs:
                full_output += f"\n[Tool result: {tm.content[:200]}]\n"

        self.memory.add_ai_message(full_output)
        return full_output

    async def stream_cycle(self, mission_briefing: str = "") -> AsyncGenerator[str, None]:
        """Stream one full agent cycle token-by-token."""
        # Use non-streaming LLM to avoid tool call chunk truncation issues
        llm = self._make_llm(streaming=False).bind_tools(self._tools)
        user_input = MISSION_START_PROMPT.format(width=20, height=20)
        if mission_briefing:
            user_input += f"\n\nAdditional briefing: {mission_briefing}"

        messages = self._build_messages(user_input)
        full_output = ""
        max_iterations = 20

        for _ in range(max_iterations):
            response = await self._invoke_with_retry(llm, messages)
            messages.append(response)

            # Yield text content
            text = response.content if isinstance(response.content, str) else ""
            if text:
                full_output += text
                yield text

            if not response.tool_calls:
                break

            # Execute tools and yield results
            yield "\n"
            tool_msgs = self._execute_tool_calls(response.tool_calls)
            messages.extend(tool_msgs)
            for tm in tool_msgs:
                summary = f"\n[{tm.tool_call_id} -> {tm.content[:300]}]\n"
                full_output += summary
                yield summary

        self.memory.add_ai_message(full_output)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_agent(mission_briefing: str = "") -> str:
    """Run one full agent cycle (non-streaming). Returns complete output."""
    agent = MultiTurnAgent()
    return await agent.run_cycle(mission_briefing)


async def stream_agent(mission_briefing: str = "") -> AsyncGenerator[str, None]:
    """Stream one full agent cycle token-by-token. Yields text chunks."""
    agent = MultiTurnAgent()
    async for chunk in agent.stream_cycle(mission_briefing):
        yield chunk


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _main():
        print("Server:", SERVER_URL)
        print("=" * 60)
        output = await run_agent()
        print(output)

    asyncio.run(_main())
