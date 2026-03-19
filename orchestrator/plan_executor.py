"""
plan_executor.py — Execute AI's JSON Plans Autonomously
Parses JSON plans from AI and executes drone movements via MCP server.
"""

import json
import asyncio
import httpx
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field, validator
from enum import Enum

# MCP Server Configuration
import os
from dotenv import load_dotenv
load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
TOOLS_BASE_URL = f"{SERVER_URL}/tools"


class ActionType(str, Enum):
    """Valid drone actions"""
    SEARCH_CONTINUOUS = "search_continuous"
    RETURN_TO_BASE = "return_to_base"
    IDLE = "idle"


class Direction(str, Enum):
    """Valid movement directions"""
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class DroneAssignment(BaseModel):
    """Single drone assignment"""
    drone_id: str
    action: ActionType
    direction: Optional[Direction] = None
    reason: str
    
    @validator('direction')
    def validate_direction(cls, v, values):
        """Ensure direction is provided for search actions"""
        if values.get('action') == ActionType.SEARCH_CONTINUOUS and v is None:
            raise ValueError("search_continuous action requires a direction")
        return v


class BatteryManagement(BaseModel):
    """Battery management info"""
    low_battery_drones: List[str] = Field(default_factory=list)
    active_search_drones: List[str] = Field(default_factory=list)
    recall_threshold: int = 20


class MissionPlan(BaseModel):
    """Complete mission plan from AI"""
    thought: str
    search_strategy: str
    drone_assignments: List[DroneAssignment]
    battery_management: BatteryManagement


class PlanExecutor:
    """
    Executes AI-generated JSON plans by calling MCP server tools.
    """
    
    def __init__(self, known_survivors: Optional[List[Dict[str, int]]] = None):
        self.client = None
        self.execution_log: List[str] = []
        self.discovered_survivors: List[Dict[str, int]] = known_survivors[:] if known_survivors else []
        self._known_survivor_set = {
            (int(s["x"]), int(s["y"]))
            for s in self.discovered_survivors
            if "x" in s and "y" in s
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()
    
    def parse_plan(self, json_response: str) -> Optional[MissionPlan]:
        """
        Parse AI's JSON response into validated MissionPlan.
        
        Args:
            json_response: Raw JSON string from AI
            
        Returns:
            MissionPlan object or None if invalid
        """
        try:
            import re
            json_str = json_response.strip()
            
            # Robust JSON extraction
            m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
            if m:
                json_str = m.group(1).strip()
            else:
                # Fallback to finding the first { and last }
                start_idx = json_str.find('{')
                end_idx = json_str.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = json_str[start_idx:end_idx+1]
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Validate with Pydantic
            plan = MissionPlan(**data)
            
            self.log(f"[OK] Plan parsed successfully: {plan.search_strategy} strategy")
            self.log(f"  Thought: {plan.thought[:100]}...")
            self.log(f"  Assignments: {len(plan.drone_assignments)} drones")
            
            return plan
            
        except json.JSONDecodeError as e:
            self.log(f"[FAIL] JSON parse error: {e}")
            return None
        except Exception as e:
            self.log(f"[FAIL] Plan validation error: {e}")
            return None
    
    def log(self, message: str):
        """Add message to execution log"""
        self.execution_log.append(message)
        print(message)
    
    def direction_to_delta(self, direction: Direction) -> tuple[int, int]:
        """Convert direction to (dx, dy) delta"""
        mapping = {
            Direction.NORTH: (0, 1),
            Direction.SOUTH: (0, -1),
            Direction.EAST: (1, 0),
            Direction.WEST: (-1, 0),
        }
        return mapping[direction]

    def alternate_directions(self, direction: Direction) -> List[Direction]:
        """Return preferred fallback directions when movement is blocked."""
        if direction == Direction.NORTH:
            return [Direction.EAST, Direction.WEST, Direction.SOUTH]
        if direction == Direction.SOUTH:
            return [Direction.WEST, Direction.EAST, Direction.NORTH]
        if direction == Direction.EAST:
            return [Direction.NORTH, Direction.SOUTH, Direction.WEST]
        return [Direction.SOUTH, Direction.NORTH, Direction.EAST]
    
    async def call_mcp_tool(self, tool_name: str, **params) -> dict:
        """Call MCP server tool"""
        try:
            url = f"{TOOLS_BASE_URL}/{tool_name}"
            if tool_name in ["get_swarm_state", "get_survivor_counts", "get_drone_state"]:
                response = await self.client.get(url, params=params)
            else:
                response = await self.client.post(url, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def execute_search_continuous(
        self,
        drone_id: str,
        direction: Direction,
        max_steps: int = 500,
    ) -> Dict[str, Any]:
        """
        Execute continuous search movement.
        
        Args:
            drone_id: Drone identifier
            direction: Direction to move
            
        Returns:
            Result from MCP server
        """
        self.log(f"  -> {drone_id}: Searching {direction.value} (continuous)")

        path: List[Dict[str, int]] = []
        step_events: List[Dict[str, Any]] = []
        all_detections: List[Dict[str, Any]] = []
        total_moves = 0
        current_direction = direction
        stopped_reason = "max_steps"
        for _ in range(max_steps):
            dx, dy = self.direction_to_delta(current_direction)
            move_result = await self.call_mcp_tool(
                "move_drone",
                drone_id=drone_id,
                dx=dx,
                dy=dy,
            )

            if not move_result.get("success"):
                fallback_applied = False
                for alt in self.alternate_directions(current_direction):
                    alt_dx, alt_dy = self.direction_to_delta(alt)
                    alt_result = await self.call_mcp_tool(
                        "move_drone",
                        drone_id=drone_id,
                        dx=alt_dx,
                        dy=alt_dy,
                    )
                    if alt_result.get("success"):
                        move_result = alt_result
                        current_direction = alt
                        fallback_applied = True
                        break

                if not fallback_applied:
                    error_text = str(move_result.get("error", ""))
                    if "bounds" in error_text.lower():
                        stopped_reason = "boundary"
                    elif "obstacle" in error_text.lower():
                        stopped_reason = "obstacle"
                    else:
                        stopped_reason = "blocked"
                    break

            total_moves += 1
            drone = move_result.get("drone", {})
            step_pos = {
                "x": int(drone.get("x", 0)),
                "y": int(drone.get("y", 0)),
                "step": total_moves,
            }
            path.append(step_pos)

            step_events.append(
                {
                    "type": "movement_step",
                    "drone_id": drone_id,
                    "action": "search_continuous",
                    "direction": current_direction.value,
                    "step": total_moves,
                    "x": step_pos["x"],
                    "y": step_pos["y"],
                    "battery": int(drone.get("battery", 0)),
                }
            )

            scan_result = await self.call_mcp_tool(
                "scan_area",
                drone_id=drone_id,
                radius=2,
            )
            detections = scan_result.get("detections", []) if scan_result.get("success", True) else []
            all_detections.extend(detections)

            new_survivors: List[Dict[str, int]] = []
            for detection in detections:
                if detection.get("type") != "S":
                    continue
                key = (int(detection.get("x", -1)), int(detection.get("y", -1)))
                if key in self._known_survivor_set:
                    continue
                self._known_survivor_set.add(key)
                coord = {"x": key[0], "y": key[1]}
                self.discovered_survivors.append(coord)
                new_survivors.append(coord)
                self.log(f"    [SURVIVOR] DETECTED at ({coord['x']}, {coord['y']})")

            for coord in new_survivors:
                step_events.append(
                    {
                        "type": "survivor_detected",
                        "drone_id": drone_id,
                        "x": coord["x"],
                        "y": coord["y"],
                    }
                )

            if new_survivors:
                stopped_reason = "detected_survivor"
                break

            if int(drone.get("battery", 0)) <= 5:
                stopped_reason = "battery"
                break

        if total_moves == 0 and stopped_reason == "max_steps":
            stopped_reason = "blocked"

        if path:
            final_position = {"x": path[-1]["x"], "y": path[-1]["y"]}
            battery_remaining = step_events[-1].get("battery", 0)
        else:
            drone_state = await self.call_mcp_tool("get_drone_state", drone_id=drone_id)
            drone = drone_state.get("drone", {}) if drone_state.get("success") else {}
            final_position = {"x": int(drone.get("x", 0)), "y": int(drone.get("y", 0))}
            battery_remaining = int(drone.get("battery", 0))

        self.log(
            f"    [OK] moved {total_moves} steps, stopped by {stopped_reason}, battery: {battery_remaining}%"
        )

        return {
            "success": True,
            "path": path,
            "moves_count": total_moves,
            "stopped_reason": stopped_reason,
            "final_position": final_position,
            "battery_remaining": battery_remaining,
            "detections": all_detections,
            "step_events": step_events,
        }
    
    async def execute_return_to_base(self, drone_id: str) -> Dict[str, Any]:
        """
        Navigate drone back to base (0,0).
        
        Args:
            drone_id: Drone identifier
            
        Returns:
            Result from navigation
        """
        self.log(f"  → {drone_id}: Returning to base (0,0)")
        
        # Get current position
        state = await self.call_mcp_tool("get_drone_state", drone_id=drone_id)
        if not state.get("success"):
            self.log(f"    [FAIL] Cannot get drone state")
            return state
        
        drone = state.get("drone", {})
        current_x = drone.get("x", 0)
        current_y = drone.get("y", 0)
        
        step_events: List[Dict[str, Any]] = []

        # Already at base?
        if current_x == 0 and current_y == 0:
            self.log(f"    [OK] Already at base, recharging...")
            step_events.append(
                {
                    "type": "movement_step",
                    "drone_id": drone_id,
                    "action": "return_to_base",
                    "x": 0,
                    "y": 0,
                    "battery": int(drone.get("battery", 0)),
                    "step": 0,
                }
            )
            return {"success": True, "message": "At base", "step_events": step_events}
        
        # Navigate to base (simple pathfinding: move west then south)
        moves = 0
        
        # Move west to x=0
        while current_x > 0:
            result = await self.call_mcp_tool("move_drone", drone_id=drone_id, dx=-1, dy=0)
            if result.get("success"):
                current_x -= 1
                moves += 1
                moved_drone = result.get("drone", {})
                step_events.append(
                    {
                        "type": "movement_step",
                        "drone_id": drone_id,
                        "action": "return_to_base",
                        "x": int(moved_drone.get("x", current_x)),
                        "y": int(moved_drone.get("y", current_y)),
                        "battery": int(moved_drone.get("battery", 0)),
                        "step": moves,
                    }
                )
            else:
                break
        
        # Move south to y=0
        while current_y > 0:
            result = await self.call_mcp_tool("move_drone", drone_id=drone_id, dx=0, dy=-1)
            if result.get("success"):
                current_y -= 1
                moves += 1
                moved_drone = result.get("drone", {})
                step_events.append(
                    {
                        "type": "movement_step",
                        "drone_id": drone_id,
                        "action": "return_to_base",
                        "x": int(moved_drone.get("x", current_x)),
                        "y": int(moved_drone.get("y", current_y)),
                        "battery": int(moved_drone.get("battery", 0)),
                        "step": moves,
                    }
                )
            else:
                break
        
        if current_x == 0 and current_y == 0:
            self.log(f"    [OK] Reached base in {moves} moves, recharging to 100%")
            return {"success": True, "moves": moves, "step_events": step_events}
        else:
            self.log(f"    [FAIL] Failed to reach base, stuck at ({current_x}, {current_y})")
            return {"success": False, "error": "Could not reach base", "step_events": step_events}
    
    async def execute_plan(self, plan: MissionPlan, max_steps_per_search: int = 500) -> Dict[str, Any]:
        """
        Execute the complete mission plan.
        
        Args:
            plan: Validated MissionPlan
            
        Returns:
            Execution summary
        """
        self.log("\n" + "=" * 70)
        self.log("EXECUTING MISSION PLAN")
        self.log("=" * 70)
        self.log(f"Strategy: {plan.search_strategy}")
        self.log(f"Thought: {plan.thought}")
        self.log(f"\nDrone Assignments ({len(plan.drone_assignments)}):")
        
        results = []
        step_events: List[Dict[str, Any]] = []
        
        for assignment in plan.drone_assignments:
            self.log(f"\n[{assignment.drone_id}]")
            self.log(f"  Action: {assignment.action.value}")
            self.log(f"  Reason: {assignment.reason}")
            
            if assignment.action == ActionType.SEARCH_CONTINUOUS:
                result = await self.execute_search_continuous(
                    assignment.drone_id,
                    assignment.direction,
                    max_steps=max_steps_per_search,
                )
                results.append(result)
                step_events.extend(result.get("step_events", []))
            
            elif assignment.action == ActionType.RETURN_TO_BASE:
                result = await self.execute_return_to_base(assignment.drone_id)
                results.append(result)
                step_events.extend(result.get("step_events", []))
            
            elif assignment.action == ActionType.IDLE:
                self.log(f"  → Idle (waiting at base)")
                results.append({"success": True, "action": "idle"})
            
            # Small delay between drone commands
            await asyncio.sleep(0.1)
        
        self.log("\n" + "=" * 70)
        self.log("EXECUTION COMPLETE")
        self.log("=" * 70)
        self.log(f"Survivors discovered: {len(self.discovered_survivors)}")
        if self.discovered_survivors:
            for i, coord in enumerate(self.discovered_survivors, 1):
                self.log(f"  {i}. ({coord['x']}, {coord['y']})")
        
        return {
            "success": True,
            "results": results,
            "survivors_found": self.discovered_survivors,
            "execution_log": self.execution_log,
            "step_events": step_events,
        }
    
    async def check_battery_levels(self) -> Dict[str, Any]:
        """
        Check all drone battery levels for reassignment trigger.
        
        Returns:
            Dict with battery status and whether reassignment needed
        """
        state = await self.call_mcp_tool("get_swarm_state")
        if not state.get("success", True):
            return {"success": False, "error": "Cannot get swarm state"}
        
        drones = state.get("drones", [])
        low_battery = []
        
        for drone in drones:
            battery = drone.get("battery", 0)
            drone_id = drone.get("drone_id")
            
            if battery <= 20 and battery > 0:
                low_battery.append({
                    "drone_id": drone_id,
                    "battery": battery,
                    "position": (drone.get("x"), drone.get("y"))
                })
        
        needs_reassignment = len(low_battery) > 0
        
        return {
            "success": True,
            "needs_reassignment": needs_reassignment,
            "low_battery_drones": low_battery,
            "all_drones": drones
        }


# Convenience function for single-use execution
async def execute_json_plan(json_response: str) -> Dict[str, Any]:
    """
    Parse and execute a JSON plan in one call.
    
    Args:
        json_response: Raw JSON string from AI
        
    Returns:
        Execution summary
    """
    async with PlanExecutor() as executor:
        plan = executor.parse_plan(json_response)
        if plan is None:
            return {"success": False, "error": "Failed to parse plan"}
        
        return await executor.execute_plan(plan)
