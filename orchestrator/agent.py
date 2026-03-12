"""
agent.py — LangChain AI Command Agent (Gemini free-tier)
Member 1 (Agent/AI) workspace.

Connects to the FastMCP server, loads drone tools via the
langchain-mcp-adapters bridge, and drives a Gemini ReAct agent loop.

Prerequisites:
    - Copy .env.example → .env and set GOOGLE_API_KEY.
    - pip install -r requirements.txt

Run standalone test:
    python -m orchestrator.agent
"""

import asyncio
import os

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient

from orchestrator.prompts import MISSION_START_PROMPT

# ---------------------------------------------------------------------------
# Load environment variables from .env (ignored by git)
# ---------------------------------------------------------------------------
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise EnvironmentError(
        "GOOGLE_API_KEY is not set. "
        "Copy .env.example to .env and add your key from "
        "https://aistudio.google.com/app/apikey"
    )

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")

MCP_CONFIG = {
    "swarm-resq": {
        "url": MCP_SERVER_URL,
        "transport": "streamable_http",
    }
}

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
- Always call scan_area() before routing a drone into an unexplored region.
- Assign drones with the HIGHEST battery to the longest routes.
- A drone carrying cargo (cargo != null) must travel to base (0,0) FIRST.
- If any drone's battery < 20 %, immediately issue a return-to-base order.
- Never move two drones to the same cell in the same turn.
- dx and dy values for move_drone must each be exactly -1, 0, or 1.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
After all tool calls for a turn, output a concise status report:
  STATUS REPORT:
    • Explored: X%  |  Survivors found: N  |  Rescued: M
    • Drone statuses: <id> @ (x,y) bat=Z% [status]
    • Next planned actions: <brief>
"""

# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def _build_prompt() -> ChatPromptTemplate:
    """
    Build the ReAct-compatible prompt template.
    The {agent_scratchpad} placeholder is required by create_react_agent.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )


async def run_agent(mission_briefing: str = "") -> str:
    """
    Connect to the MCP server, discover tools, and run one full agent cycle.

    Args:
        mission_briefing: Optional extra instructions appended to the
                          mission start prompt (e.g. from the Streamlit UI).

    Returns:
        The agent's final text response for this cycle.
    """
    async with MultiServerMCPClient(MCP_CONFIG) as client:
        tools = client.get_tools()

        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0,          # deterministic decisions
            convert_system_message_to_human=True,  # Gemini requirement
        )

        agent = create_react_agent(
            llm=llm,
            tools=tools,
            prompt=_build_prompt(),
        )

        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=30,
            handle_parsing_errors=True,
            return_intermediate_steps=False,
        )

        user_input = MISSION_START_PROMPT.format(width=20, height=20)
        if mission_briefing:
            user_input += f"\n\nAdditional briefing from Command: {mission_briefing}"

        result = await executor.ainvoke({"input": user_input})
        return result.get("output", "")


async def stream_agent(mission_briefing: str = ""):
    """
    Streaming variant — yields token chunks for the Streamlit UI.
    Usage:
        async for chunk in stream_agent():
            print(chunk, end="", flush=True)
    """
    async with MultiServerMCPClient(MCP_CONFIG) as client:
        tools = client.get_tools()

        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0,
            convert_system_message_to_human=True,
            streaming=True,
        )

        agent = create_react_agent(
            llm=llm,
            tools=tools,
            prompt=_build_prompt(),
        )

        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            max_iterations=30,
            handle_parsing_errors=True,
        )

        user_input = MISSION_START_PROMPT.format(width=20, height=20)
        if mission_briefing:
            user_input += f"\n\nAdditional briefing from Command: {mission_briefing}"

        async for event in executor.astream_events(
            {"input": user_input}, version="v2"
        ):
            kind = event.get("event")
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if hasattr(chunk, "content") and chunk.content:
                    yield chunk.content


# ---------------------------------------------------------------------------
# Quick local test — run with:  python -m orchestrator.agent
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _main():
        print("Connecting to MCP server at:", MCP_SERVER_URL)
        output = await run_agent()
        print("\n━━━ ARIA FINAL RESPONSE ━━━")
        print(output)

    asyncio.run(_main())


# ---------------------------------------------------------------------------
# TODO (Member 1):
#   - Wire stream_agent() into ui/app.py for live token rendering
#   - Add LangChain ConversationBufferMemory for multi-turn missions
#   - Implement a mission-complete condition (all survivors rescued)
# ---------------------------------------------------------------------------
