"""
drone.py — Drone State & Movement Logic
Member 3 (Simulation) workspace.

Defines the Drone dataclass and the DroneSwarm manager that
tracks all active drones and their positions on the grid.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from environment.grid import Grid, CellType


class DroneStatus(Enum):
    IDLE = "idle"
    MOVING = "moving"
    SCANNING = "scanning"
    RESCUING = "rescuing"
    RETURNING = "returning"


@dataclass
class Drone:
    drone_id: str
    x: int
    y: int
    status: DroneStatus = DroneStatus.IDLE
    battery: int = 100          # percentage
    cargo: Optional[str] = None  # survivor ID if carrying one

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

    def add_drone(self, drone_id: str, x: int, y: int) -> Drone:
        drone = Drone(drone_id=drone_id, x=x, y=y)
        self.drones[drone_id] = drone
        self.grid.cells[y][x].drone_id = drone_id
        self.grid.set_cell_type(x, y, CellType.DRONE)
        return drone

    def move_drone(self, drone_id: str, dx: int, dy: int) -> dict:
        """
        Move a drone by (dx, dy). Returns a result dict.
        dx, dy should each be -1, 0, or 1.
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}

        new_x, new_y = drone.x + dx, drone.y + dy

        if not self.grid.in_bounds(new_x, new_y):
            return {"success": False, "error": "Move out of bounds."}

        target_cell = self.grid.get_cell(new_x, new_y)
        if target_cell.cell_type == CellType.OBSTACLE:
            return {"success": False, "error": "Cell is an obstacle."}

        # Clear old cell
        self.grid.cells[drone.y][drone.x].drone_id = None
        self.grid.set_cell_type(drone.x, drone.y, CellType.EMPTY)

        # Update drone position
        drone.x, drone.y = new_x, new_y
        drone.status = DroneStatus.MOVING
        drone.battery = max(0, drone.battery - 1)

        # Update new cell
        self.grid.cells[new_y][new_x].drone_id = drone_id
        self.grid.set_cell_type(new_x, new_y, CellType.DRONE)

        return {"success": True, "drone": drone.to_dict()}

    def scan_area(self, drone_id: str, radius: int = 2) -> dict:
        """
        Scan cells within `radius` of the drone.
        Returns a list of detected cells.
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}

        drone.status = DroneStatus.SCANNING
        found = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                cx, cy = drone.x + dx, drone.y + dy
                cell = self.grid.get_cell(cx, cy)
                if cell and cell.cell_type not in (CellType.EMPTY, CellType.DRONE):
                    found.append({"x": cx, "y": cy, "type": cell.cell_type.value})

        return {"success": True, "drone_id": drone_id, "detections": found}

    def get_state(self) -> dict:
        return {
            "drones": [d.to_dict() for d in self.drones.values()],
            "grid": self.grid.to_dict(),
        }


# ---------------------------------------------------------------------------
# TODO (Member 3): Add rescue logic:
#   - rescue_survivor(drone_id, target_x, target_y)
#   - return_to_base(drone_id, base_x, base_y)
# ---------------------------------------------------------------------------
