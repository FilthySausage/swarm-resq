"""
mission_controller.py — Turn-by-turn mission orchestration

Behavior:
- Ask AI once per turn for immediate assignments only.
- Execute a short movement slice and stream UI step updates.
- Wait briefly, then ask AI again using latest state.
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

from orchestrator.model_loader import get_default_model, get_model_by_name, load_models
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
        self.model_candidates: list[Dict[str, Any]] = self._build_model_candidates(model_config)
        self.turn_count = 0
        self.max_turns = 60
        self.turn_delay_seconds = 2.0
        self.max_steps_per_drone_turn = 2

        self.initial_plan_json: Optional[str] = None
        self.current_plan_json: Optional[str] = None
        self.last_turn_error: Optional[str] = None

        self.discovered_survivors: list[dict[str, int]] = []
        self.total_survivors_target: Optional[int] = None
        self.explored_cells: set[tuple[int, int]] = set()
        self.total_cells: int = 0
        self.obstacle_cells: set[tuple[int, int]] = set()
        self.hazard_cells: set[tuple[int, int]] = set()
        self.blocked_cells: set[tuple[int, int]] = set()

    def _build_model_candidates(self, primary_config: Dict[str, Any]) -> list[Dict[str, Any]]:
        # Future-proofing: could append fallback models here. Just use primary for now.
        return [primary_config]

    def _make_llm(self, config: Dict[str, Any]) -> ChatOpenAI:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        # If openrouter model and no key, maybe warn, but allow passing dummy to ChatOpenAI
        if config.get("requires_key", False) and not api_key:
            raise EnvironmentError(f"OPENROUTER_API_KEY not set in .env file, but required by {config.get('name')}")
        
        args = {
            "model": config["model_id"],
            "api_key": api_key if api_key else "dummy_key_for_local_models",
            "base_url": config["base_url"],
            "temperature": 0,
            "max_tokens": config.get("max_tokens", 350),
        }
        if "timeout" in config:
            args["timeout"] = config["timeout"]
        if "extra_body" in config:
            args["model_kwargs"] = config["extra_body"]
            
        return ChatOpenAI(**args)

    async def initialize_llm(self) -> None:
        self.llm = self._make_llm(self.model_config)

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

    def _mark_scanned_area(self, x: int, y: int, width: int, height: int, radius: int = 2) -> None:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > radius:
                    continue
                cx = x + dx
                cy = y + dy
                if 0 <= cx < width and 0 <= cy < height:
                    self.explored_cells.add((cx, cy))

    def _update_explored_from_state(self, state: Dict[str, Any]) -> None:
        grid = state.get("grid", {})
        width = int(grid.get("width", 0))
        height = int(grid.get("height", 0))
        if width <= 0 or height <= 0:
            return
        self.total_cells = width * height
        for drone in state.get("drones", []):
            x = int(drone.get("x", 0))
            y = int(drone.get("y", 0))
            self._mark_scanned_area(x, y, width, height, radius=2)

    def _update_explored_from_events(self, step_events: list[dict[str, Any]], state: Dict[str, Any]) -> None:
        grid = state.get("grid", {})
        width = int(grid.get("width", 0))
        height = int(grid.get("height", 0))
        if width <= 0 or height <= 0:
            return
        self.total_cells = width * height
        for event in step_events:
            event_type = str(event.get("type", ""))
            if event_type == "movement_step":
                x = int(event.get("x", 0))
                y = int(event.get("y", 0))
                self._mark_scanned_area(x, y, width, height, radius=2)
            elif event_type == "obstacle_detected":
                self.obstacle_cells.add((int(event.get("x", -1)), int(event.get("y", -1))))
            elif event_type == "hazard_detected":
                self.hazard_cells.add((int(event.get("x", -1)), int(event.get("y", -1))))
            elif event_type == "blocked_attempt":
                self.blocked_cells.add((int(event.get("x", -1)), int(event.get("y", -1))))

    def build_fallback_turn_plan_json(self, state: Dict[str, Any], reason: str = "fallback") -> str:
        """Build a deterministic, minimal per-turn plan when AI output is unavailable/invalid."""
        directions = ["north", "east", "south", "west"]
        assignments = []
        low_battery_drones = []
        active_search_drones = []

        drones = state.get("drones", [])
        for idx, drone in enumerate(drones):
            drone_id = drone.get("drone_id", f"drone-{idx + 1}")
            battery = int(drone.get("battery", 0))

            if 0 < battery <= 20:
                low_battery_drones.append(drone_id)
                assignments.append(
                    {
                        "drone_id": drone_id,
                        "action": "return_to_base",
                        "direction": None,
                        "reason": "Low battery safety return",
                    }
                )
            else:
                active_search_drones.append(drone_id)
                direction = directions[(self.turn_count + idx) % len(directions)]
                assignments.append(
                    {
                        "drone_id": drone_id,
                        "action": "search_continuous",
                        "direction": direction,
                        "reason": "Fallback immediate exploration step",
                    }
                )

        payload = {
            "thought": f"Fallback turn plan generated ({reason})",
            "search_strategy": "turn_step_fallback",
            "drone_assignments": assignments,
            "battery_management": {
                "low_battery_drones": low_battery_drones,
                "active_search_drones": active_search_drones,
                "recall_threshold": 20,
            },
        }
        return json.dumps(payload)

    async def _ask_ai(self, system_prompt: str, user_message: str) -> str:
        if self.llm is None:
            raise RuntimeError("LLM is not initialized")

        try:
            response = await self.llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            )
            self.last_turn_error = None
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            self.last_turn_error = f"{type(exc).__name__}: {exc}"
            raise

    async def request_turn_plan(self, state: Dict[str, Any], briefing: str = "") -> Optional[str]:
        self._update_explored_from_state(state)
        state_text = self.format_state_for_ai(state)
        grid = state.get("grid", {})
        width = int(grid.get("width", 0))
        height = int(grid.get("height", 0))
        total_cells = width * height if width > 0 and height > 0 else self.total_cells
        unexplored = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if (x, y) not in self.explored_cells
        ] if width > 0 and height > 0 else []
        explored_coords = sorted(self.explored_cells)
        unexplored_sample = unexplored[:12]
        obstacle_sample = sorted(self.obstacle_cells)[:20]
        hazard_sample = sorted(self.hazard_cells)[:20]
        blocked_sample = sorted(self.blocked_cells)[:20]
        turn_message = TURN_DECISION_USER_TEMPLATE.format(
            turn_no=self.turn_count,
            briefing=briefing or "Systematic survivor coordinate discovery",
            known_survivors=self.discovered_survivors,
            explored_count=len(self.explored_cells),
            total_cells=total_cells,
            explored_coords=explored_coords,
            unexplored_sample=unexplored_sample,
            obstacle_sample=obstacle_sample,
            hazard_sample=hazard_sample,
            blocked_sample=blocked_sample,
            state_text=state_text,
        )

        last_error = None
        for model_config in self.model_candidates:
            try:
                self.model_config = model_config
                self.llm = self._make_llm(model_config)
                response = await self._ask_ai(TURN_DECISION_SYSTEM_PROMPT, turn_message)
                if response and response.strip():
                    return response
            except Exception as exc:
                last_error = f"{model_config.get('name', model_config.get('model_id'))}: {type(exc).__name__}: {exc}"
                self.last_turn_error = last_error

        self.last_turn_error = last_error
        return None

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
        yield f"Model ID: {self.model_config['model_id']}\n"
        yield f"Model base URL: {self.model_config['base_url']}\n"
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
                yield "WARN: AI plan unavailable; skipping this turn (fallback disabled).\n"
                if self.last_turn_error:
                    yield f"DEBUG AI ERROR: {self.last_turn_error}\n"
                yield f"DEBUG STATE: drones={len(state.get('drones', []))}, survivors={len(state.get('survivors', []))}\n"
                await asyncio.sleep(self.turn_delay_seconds)
                continue

            yield "AI decision received for this turn. Executing movements...\n"

            execution = await self._execute_plan_json(turn_plan_json)
            if not execution.get("success"):
                yield "WARN: AI plan invalid/execution failed; skipping this turn (fallback disabled).\n"
                if execution.get("error"):
                    yield f"DEBUG EXECUTION ERROR: {execution.get('error')}\n"
                await asyncio.sleep(self.turn_delay_seconds)
                continue

            self._update_explored_from_events(execution.get("step_events", []), state)

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

            yield f"Waiting {self.turn_delay_seconds:.1f}s before next AI turn...\n"
            await asyncio.sleep(self.turn_delay_seconds)

        yield "\n" + "=" * 70 + "\n"
        yield "MISSION SUMMARY\n"
        yield "=" * 70 + "\n"
        yield f"Turns: {self.turn_count}\n"
        yield f"Found: {len(self.discovered_survivors)} / {self.total_survivors_target}\n"
        if self.discovered_survivors:
            for idx, coord in enumerate(self.discovered_survivors, 1):
                yield f"  {idx}. ({coord['x']}, {coord['y']})\n"
