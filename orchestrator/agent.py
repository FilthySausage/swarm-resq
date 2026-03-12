"""
agent.py — LangChain AI Command Agent
Member 1 (Agent/AI) workspace.

Connects to the MCP server, loads drone tools via the
langchain-mcp-adapters bridge, and runs the ReAct agent loop.
"""

import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from orchestrator.prompts import SYSTEM_PROMPT, MISSION_START_PROMPT

# ---------------------------------------------------------------------------
# MCP Server connection config
# Update the URL if the server runs on a different host/port.
# ---------------------------------------------------------------------------
MCP_SERVER_URL = "http://localhost:8000/mcp"

MCP_CONFIG = {
    "swarm-resq": {
        "url": MCP_SERVER_URL,
        "transport": "streamable_http",
    }
}


async def run_agent(mission_briefing: str = "") -> str:
    """
    Connect to the MCP server, load tools, and run one agent cycle.

    Args:
        mission_briefing: An optional extra instruction to append to the
                          mission start prompt.

    Returns:
        The agent's final response string.
    """
    async with MultiServerMCPClient(MCP_CONFIG) as client:
        tools = client.get_tools()

        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=20,
            handle_parsing_errors=True,
        )

        user_input = MISSION_START_PROMPT.format(width=20, height=20)
        if mission_briefing:
            user_input += f"\n\nAdditional briefing: {mission_briefing}"

        result = await executor.ainvoke({"input": user_input})
        return result.get("output", "")


# ---------------------------------------------------------------------------
# Quick local test — run with: python -m orchestrator.agent
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    output = asyncio.run(run_agent())
    print("\n--- ARIA RESPONSE ---")
    print(output)


# ---------------------------------------------------------------------------
# TODO (Member 1):
#   - Add a streaming version for the Streamlit UI (use astream_events)
#   - Add memory/chat history for multi-turn mission conversations
#   - Implement a mission-complete detection loop
# ---------------------------------------------------------------------------
