"""
drone.py — Drone State & Movement Logic

Defines the Drone dataclass and the DroneSwarm manager that tracks all active
Drones on the grid.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from environment.grid import Grid, CellType


class DroneStatus(Enum):
    IDLE = "idle"
    MOVING = "moving"
    MOVING_CONTINUOUS = "moving_continuous"
    SCANNING = "scanning"
    RESCUING = "rescuing"
    RETURNING = "returning"
    STOPPED = "stopped"


@dataclass
class Drone:
    drone_id: str
    x: int
    y: int
    status: DroneStatus = DroneStatus.IDLE
    battery: int = 100
    cargo: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "drone_id": self.drone_id,
            "x": self.x,
            "y": self.y,
            "status": self.status.value,
            "battery": self.battery,
            "cargo": self.cargo,
        }


class DroneSwarm:
    def __init__(self, grid: Grid):
        self.grid = grid
        self.drones: dict[str, Drone] = {}
        self.survivors_at_base: list[str] = []

    def _clear_drone_from_cell(self, x: int, y: int) -> None:
        cell = self.grid.get_cell(x, y)
        if cell:
            cell.drone_id = None
            if cell.cell_type == CellType.DRONE:
                cell.cell_type = CellType.EMPTY

    def _place_drone_on_cell(self, drone_id: str, x: int, y: int) -> None:
        cell = self.grid.get_cell(x, y)
        if cell:
            cell.drone_id = drone_id
            cell.cell_type = CellType.DRONE

    def add_drone(self, drone_id: str, x: int, y: int) -> Drone:
        if not self.grid.in_bounds(x, y):
            raise ValueError(f"Drone position ({x}, {y}) out of bounds")

        cell = self.grid.get_cell(x, y)
        if cell is None or cell.cell_type in (CellType.OBSTACLE, CellType.HAZARD):
            raise ValueError(f"Invalid spawn cell at ({x}, {y})")

        drone = Drone(drone_id=drone_id, x=x, y=y)
        self.drones[drone_id] = drone
        self._place_drone_on_cell(drone_id, x, y)
        return drone

    def move_drone(self, drone_id: str, dx: int, dy: int) -> dict:
        """
        Move a drone by (dx, dy) using bottom-left origin coordinates.
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}

        new_x, new_y = drone.x + dx, drone.y + dy
        if not self.grid.in_bounds(new_x, new_y):
            return {"success": False, "error": "Move out of bounds."}

        target_cell = self.grid.get_cell(new_x, new_y)
        if target_cell is None:
            return {"success": False, "error": "Target cell not found."}
        if target_cell.cell_type == CellType.OBSTACLE:
            return {"success": False, "error": "Cell is an obstacle."}
        if target_cell.cell_type == CellType.HAZARD:
            return {"success": False, "error": "Cell is a hazard."}

        self._clear_drone_from_cell(drone.x, drone.y)

        drone.x = new_x
        drone.y = new_y
        drone.status = DroneStatus.MOVING
        drone.battery = max(0, drone.battery - 1)

        self._place_drone_on_cell(drone_id, new_x, new_y)
        return {"success": True, "drone": drone.to_dict()}

    def scan_area(self, drone_id: Optional[str] = None, radius: int = 2) -> dict:
        """
        Scan cells within Manhattan distance `radius` of the drone.
        """
        if not drone_id:
            if not self.drones:
                return {"success": False, "error": "No drones available in the swarm."}
            drone_id = next(iter(self.drones.keys()))

        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}

        drone.status = DroneStatus.SCANNING
        found: list[dict] = []

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > radius:
                    continue
                cx, cy = drone.x + dx, drone.y + dy
                cell = self.grid.get_cell(cx, cy)
                if cell is None:
                    continue

                if cell.cell_type not in (CellType.EMPTY, CellType.DRONE):
                    found.append({"x": cx, "y": cy, "type": cell.cell_type.value})

        return {"success": True, "drone_id": drone_id, "detections": found}

    def get_state(self) -> dict:
        return {
            "drones": [d.to_dict() for d in self.drones.values()],
            "grid": self.grid.to_dict(),
            "survivors_rescued": self.survivors_at_base,
        }

    def rescue_survivor(self, drone_id: str, target_x: int, target_y: int) -> dict:
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        if drone.cargo is not None:
            return {"success": False, "error": f"Drone {drone_id} already carrying cargo."}

        dx = abs(drone.x - target_x)
        dy = abs(drone.y - target_y)
        if dx + dy > 1:
            return {
                "success": False,
                "error": f"Target ({target_x}, {target_y}) is not adjacent to drone.",
            }

        target_cell = self.grid.get_cell(target_x, target_y)
        if not target_cell or target_cell.cell_type != CellType.SURVIVOR:
            return {
                "success": False,
                "error": f"No survivor at ({target_x}, {target_y}).",
            }

        survivor_id = f"survivor_{target_x}_{target_y}"
        drone.cargo = survivor_id
        drone.status = DroneStatus.RESCUING
        target_cell.cell_type = CellType.EMPTY
        drone.battery = max(0, drone.battery - 2)

        return {
            "success": True,
            "message": f"Drone {drone_id} rescued {survivor_id}.",
            "drone": drone.to_dict(),
        }

    def return_to_base(self, drone_id: str, base_x: int = 0, base_y: int = 0) -> dict:
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        if drone.cargo is None:
            return {
                "success": False,
                "error": f"Drone {drone_id} is not carrying cargo.",
            }
        if drone.x != base_x or drone.y != base_y:
            return {
                "success": False,
                "error": (
                    f"Drone {drone_id} at ({drone.x}, {drone.y}), "
                    f"base is at ({base_x}, {base_y}). Move to base first."
                ),
            }

        survivor_id = drone.cargo
        self.survivors_at_base.append(survivor_id)
        drone.cargo = None
        drone.status = DroneStatus.IDLE
        drone.battery = max(0, drone.battery - 1)

        return {
            "success": True,
            "message": f"Drone {drone_id} delivered {survivor_id} to base!",
            "drone": drone.to_dict(),
            "survivors_at_base": len(self.survivors_at_base),
        }

    def get_survivor_count(self) -> dict:
        survivors_on_grid = 0
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                cell = self.grid.get_cell(x, y)
                if cell and cell.cell_type == CellType.SURVIVOR:
                    survivors_on_grid += 1

        survivors_in_cargo = sum(1 for d in self.drones.values() if d.cargo)

        return {
            "on_grid": survivors_on_grid,
            "in_cargo": survivors_in_cargo,
            "rescued": len(self.survivors_at_base),
            "total_found": survivors_on_grid + survivors_in_cargo + len(self.survivors_at_base),
        }

    def move_until_detect(
        self,
        drone_id: str,
        direction_x: int,
        direction_y: int,
        scan_radius: int = 2,
        max_steps: int = 10,
    ) -> dict:
        """
        Move a drone in a direction until detection/boundary/obstacle/battery limit.
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        if direction_x == 0 and direction_y == 0:
            return {"success": False, "error": "Invalid direction: must move at least one coordinate."}

        path = [{"x": drone.x, "y": drone.y, "step": 0}]
        all_detections: list[dict] = []
        steps_taken = 0
        stopped_reason = "max_steps"
        drone.status = DroneStatus.MOVING_CONTINUOUS

        while steps_taken < max_steps:
            if drone.battery < 5:
                stopped_reason = "battery"
                break

            new_x, new_y = drone.x + direction_x, drone.y + direction_y
            if not self.grid.in_bounds(new_x, new_y):
                stopped_reason = "boundary"
                break

            target_cell = self.grid.get_cell(new_x, new_y)
            if target_cell and target_cell.cell_type in (CellType.OBSTACLE, CellType.HAZARD):
                stopped_reason = "hazard" if target_cell.cell_type == CellType.HAZARD else "obstacle"
                break

            self._clear_drone_from_cell(drone.x, drone.y)
            drone.x, drone.y = new_x, new_y
            drone.battery = max(0, drone.battery - 1)
            self._place_drone_on_cell(drone_id, new_x, new_y)

            path.append({"x": drone.x, "y": drone.y, "step": steps_taken + 1})
            steps_taken += 1

            detections = self.scan_area(drone_id=drone_id, radius=scan_radius).get("detections", [])
            if detections:
                all_detections.extend(detections)
                if any(d.get("type") == CellType.SURVIVOR.value for d in detections):
                    stopped_reason = "detected_survivor"
                elif any(d.get("type") == CellType.HAZARD.value for d in detections):
                    stopped_reason = "detected_hazard"
                else:
                    stopped_reason = "detected"
                break

        drone.status = DroneStatus.STOPPED
        return {
            "success": True,
            "drone": drone.to_dict(),
            "moves_count": steps_taken,
            "path": path,
            "detections": all_detections,
            "final_position": {"x": drone.x, "y": drone.y},
            "stopped_reason": stopped_reason,
        }

    def move_continuous_until_stopped(self, drone_id: str, direction_x: int, direction_y: int) -> dict:
        """
        Move continuously until boundary/obstacle/battery/detection and return full path.
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        if direction_x == 0 and direction_y == 0:
            return {"success": False, "error": "Invalid direction"}

        path = [{"x": drone.x, "y": drone.y, "step": 0}]
        all_detections: list[dict] = []
        initial_battery = drone.battery
        steps_taken = 0
        stopped_reason = "boundary"

        drone.status = DroneStatus.MOVING_CONTINUOUS

        while True:
            if drone.battery < 5:
                stopped_reason = "battery"
                break

            new_x, new_y = drone.x + direction_x, drone.y + direction_y
            if not self.grid.in_bounds(new_x, new_y):
                stopped_reason = "boundary"
                break

            target_cell = self.grid.get_cell(new_x, new_y)
            if target_cell and target_cell.cell_type in (CellType.OBSTACLE, CellType.HAZARD):
                stopped_reason = "hazard" if target_cell.cell_type == CellType.HAZARD else "obstacle"
                break

            self._clear_drone_from_cell(drone.x, drone.y)
            drone.x, drone.y = new_x, new_y
            drone.battery = max(0, drone.battery - 1)
            self._place_drone_on_cell(drone_id, new_x, new_y)

            path.append({"x": drone.x, "y": drone.y, "step": steps_taken + 1})
            steps_taken += 1

            detections = self.scan_area(drone_id=drone_id, radius=2).get("detections", [])
            if detections:
                all_detections.extend(detections)
                if any(d.get("type") == CellType.SURVIVOR.value for d in detections):
                    stopped_reason = "detected_survivor"
                elif any(d.get("type") == CellType.HAZARD.value for d in detections):
                    stopped_reason = "detected_hazard"
                else:
                    stopped_reason = "detected"
                break

        drone.status = DroneStatus.STOPPED
        return {
            "success": True,
            "path": path,
            "moves_count": steps_taken,
            "stopped_reason": stopped_reason,
            "detections": all_detections,
            "final_position": {"x": drone.x, "y": drone.y},
            "battery_used": initial_battery - drone.battery,
            "battery_remaining": drone.battery,
            "drone": drone.to_dict(),
        }

    def get_nearest_survivor(self) -> dict:
        survivors = []
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                cell = self.grid.get_cell(x, y)
                if cell and cell.cell_type == CellType.SURVIVOR:
                    survivors.append((x, y))

        if not survivors:
            return {"success": False, "error": "No survivors found on grid."}

        nearest = None
        nearest_distance = float("inf")
        nearest_drone = None

        for sx, sy in survivors:
            for drone in self.drones.values():
                distance = abs(drone.x - sx) + abs(drone.y - sy)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest = (sx, sy)
                    nearest_drone = drone.drone_id

        return {
            "success": True,
            "location": {"x": nearest[0], "y": nearest[1]},
            "distance": nearest_distance,
            "nearest_drone": nearest_drone,
        }

    def estimate_battery_to_target(self, drone_id: str, target_x: int, target_y: int) -> dict:
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}

        distance = abs(drone.x - target_x) + abs(drone.y - target_y)
        movement_cost = distance
        scanning_cost = distance // 2
        rescue_cost = 2
        return_to_base_cost = abs(target_x) + abs(target_y) + 1

        total_estimated = movement_cost + scanning_cost + rescue_cost + return_to_base_cost
        current_battery = drone.battery
        can_afford = current_battery >= total_estimated

        return {
            "success": True,
            "drone_id": drone_id,
            "current_battery": current_battery,
            "distance_to_target": distance,
            "estimated_costs": {
                "movement": movement_cost,
                "scanning": scanning_cost,
                "rescue": rescue_cost,
                "return_to_base": return_to_base_cost,
                "total": total_estimated,
            },
            "can_afford": can_afford,
            "battery_shortfall": max(0, total_estimated - current_battery),
        }

    def get_hazard_map(self) -> dict:
        hazards = []
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                cell = self.grid.get_cell(x, y)
                if cell and cell.cell_type == CellType.HAZARD:
                    hazards.append({"x": x, "y": y})

        return {
            "success": True,
            "hazards": hazards,
            "hazard_count": len(hazards),
        }

    def get_obstacle_map(self) -> dict:
        obstacles = []
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                cell = self.grid.get_cell(x, y)
                if cell and cell.cell_type == CellType.OBSTACLE:
                    obstacles.append({"x": x, "y": y})

        return {
            "success": True,
            "obstacles": obstacles,
            "obstacle_count": len(obstacles),
        }
