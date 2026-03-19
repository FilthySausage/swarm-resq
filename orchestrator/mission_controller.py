"""
mission_controller.py — Single-prompt mission orchestration

Behavior:
- Ask AI once for initial assignment plan.
- Keep executing search autonomously.
- Ask AI again only when battery threshold is reached for reassignment.
- Mission objective is survivor coordinate discovery (no rescue required).
"""

import asyncio
import json
import os
from typing import Any, AsyncGenerator, Dict, Optional

import httpx
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from orchestrator.model_loader import get_default_model, get_model_by_name
from orchestrator.plan_executor import PlanExecutor
from orchestrator.single_shot_prompts import (
    TURN_DECISION_SYSTEM_PROMPT,
    TURN_DECISION_USER_TEMPLATE,
)

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
TOOLS_BASE_URL = f"{SERVER_URL}/tools"


class MissionController:
    def __init__(self, model_name: Optional[str] = None):
        if model_name:
            model_config = get_model_by_name(model_name) or get_default_model()
        else:
            model_config = get_default_model()

        self.model_config = model_config
        self.llm: Optional[ChatOpenAI] = None
        self.turn_count = 0
        self.max_turns = 60
        self.max_steps_per_drone_turn = 2

        self.initial_plan_json: Optional[str] = None
        self.current_plan_json: Optional[str] = None

        self.discovered_survivors: list[dict[str, int]] = []
        self.total_survivors_target: Optional[int] = None

    async def initialize_llm(self) -> None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY not set in .env file")

        self.llm = ChatOpenAI(
            model=self.model_config["model_id"],
            api_key=api_key,
            base_url=self.model_config["base_url"],
            temperature=0,
            max_tokens=self.model_config.get("max_tokens", 8000),
        )

    async def _get_json(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return {"success": False, "error": f"HTTP {r.status_code}"}
            return r.json()

    async def get_swarm_state(self) -> Dict[str, Any]:
        return await self._get_json(f"{TOOLS_BASE_URL}/get_swarm_state")

    async def get_survivor_counts(self) -> Dict[str, Any]:
        return await self._get_json(f"{TOOLS_BASE_URL}/get_survivor_counts")

    def format_state_for_ai(self, state: Dict[str, Any]) -> str:
        grid = state.get("grid", {})
        drones = state.get("drones", [])

        width = grid.get("width", 0)
        height = grid.get("height", 0)

        drone_lines = []
        for drone in drones:
            drone_lines.append(
                f"  - {drone.get('drone_id')}: position ({drone.get('x')},{drone.get('y')}), "
                f"battery {drone.get('battery')}%, status {drone.get('status')}"
            )

        return (
            f"Grid: {width}x{height} ({width * height} cells)\n"
            f"Base: (0, 0)\n\n"
            f"Drones:\n{chr(10).join(drone_lines)}"
        )

    async def _ask_ai(self, system_prompt: str, user_message: str) -> str:
        if self.llm is None:
            raise RuntimeError("LLM is not initialized")

        response = await self.llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        )
        return response.content if hasattr(response, "content") else str(response)

    async def request_turn_plan(self, state: Dict[str, Any], briefing: str = "") -> Optional[str]:
        state_text = self.format_state_for_ai(state)
        turn_message = TURN_DECISION_USER_TEMPLATE.format(
            turn_no=self.turn_count,
            briefing=briefing or "Systematic survivor coordinate discovery",
            known_survivors=self.discovered_survivors,
            state_text=state_text,
        )

        return await self._ask_ai(TURN_DECISION_SYSTEM_PROMPT, turn_message)

    async def _execute_plan_json(self, plan_json: str) -> Dict[str, Any]:
        async with PlanExecutor(known_survivors=self.discovered_survivors) as executor:
            plan = executor.parse_plan(plan_json)
            if plan is None:
                return {
                    "success": False,
                    "error": "Invalid JSON plan",
                    "execution_log": executor.execution_log,
                }

            known_before = {(int(s["x"]), int(s["y"])) for s in self.discovered_survivors}
            result = await executor.execute_plan(
                plan,
                max_steps_per_search=self.max_steps_per_drone_turn,
            )
            for coord in result.get("survivors_found", []):
                if coord not in self.discovered_survivors:
                    self.discovered_survivors.append(coord)

            known_after = {(int(s["x"]), int(s["y"])) for s in self.discovered_survivors}
            result["new_survivors_found"] = [
                {"x": x, "y": y} for (x, y) in sorted(known_after - known_before)
            ]

            return result

    async def _ensure_target_count(self) -> None:
        if self.total_survivors_target is not None:
            return
        counts = await self.get_survivor_counts()
        self.total_survivors_target = int(counts.get("on_grid", 0))

    def mission_complete(self) -> bool:
        if self.total_survivors_target is None:
            return False
        return len(self.discovered_survivors) >= self.total_survivors_target

    async def stream_mission(self, briefing: str = "") -> AsyncGenerator[str, None]:
        await self.initialize_llm()
        await self._ensure_target_count()

        yield "=" * 70 + "\n"
        yield "SWARM-RESQ MISSION START\n"
        yield "=" * 70 + "\n"
        yield f"Model: {self.model_config['name']}\n"
        yield f"Target survivors: {self.total_survivors_target}\n"

        while self.turn_count < self.max_turns:
            self.turn_count += 1
            yield "\n" + "=" * 70 + "\n"
            yield f"TURN {self.turn_count}\n"
            yield "=" * 70 + "\n"

            state = await self.get_swarm_state()
            if state.get("success") is False:
                yield f"ERROR: Failed to fetch swarm state: {state.get('error', 'unknown')}\n"
                return

            turn_plan_json = await self.request_turn_plan(state, briefing)
            if not turn_plan_json:
                yield "ERROR: Failed to get AI plan for current turn\n"
                return

            yield "AI decision received for this turn. Executing movements...\n"

            execution = await self._execute_plan_json(turn_plan_json)
            if not execution.get("success"):
                yield "ERROR: Plan execution failed\n"
                for line in execution.get("execution_log", []):
                    yield line + "\n"
                return

            for line in execution.get("execution_log", []):
                yield line + "\n"

            for event in execution.get("step_events", []):
                yield "__EVENT__" + json.dumps(event) + "\n"

            for coord in execution.get("new_survivors_found", []):
                yield "__EVENT__" + json.dumps({"type": "survivor_detected", "x": coord["x"], "y": coord["y"]}) + "\n"

            yield f"Discovered survivors so far: {len(self.discovered_survivors)}\n"
            if self.discovered_survivors:
                yield f"Coordinates: {self.discovered_survivors}\n"

            if self.mission_complete():
                yield "\nMISSION COMPLETE: All survivor coordinates found.\n"
                break

            await asyncio.sleep(0.3)

        yield "\n" + "=" * 70 + "\n"
        yield "MISSION SUMMARY\n"
        yield "=" * 70 + "\n"
        yield f"Turns: {self.turn_count}\n"
        yield f"Found: {len(self.discovered_survivors)} / {self.total_survivors_target}\n"
        if self.discovered_survivors:
            for idx, coord in enumerate(self.discovered_survivors, 1):
                yield f"  {idx}. ({coord['x']}, {coord['y']})\n"
