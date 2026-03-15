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
        self.survivors_at_base: list[str] = []  # Track rescued survivors

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
            "survivors_rescued": self.survivors_at_base,
        }

    def rescue_survivor(self, drone_id: str, target_x: int, target_y: int) -> dict:
        """
        Attempt to pick up a survivor at (target_x, target_y).
        Drone must be at or adjacent to the survivor.
        Returns a dict with success status and result details.
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}

        if drone.cargo is not None:
            return {"success": False, "error": f"Drone {drone_id} already carrying cargo."}

        # Check if target is within pickup range (adjacent or same cell)
        dx = abs(drone.x - target_x)
        dy = abs(drone.y - target_y)
        if dx + dy > 1:  # Manhattan distance > 1
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

        # Rescue: assign survivor ID to cargo, mark cell as empty
        survivor_id = f"survivor_{target_x}_{target_y}"
        drone.cargo = survivor_id
        drone.status = DroneStatus.RESCUING
        self.grid.set_cell_type(target_x, target_y, CellType.EMPTY)
        drone.battery = max(0, drone.battery - 2)  # Rescue costs extra battery

        return {
            "success": True,
            "message": f"Drone {drone_id} rescued {survivor_id}.",
            "drone": drone.to_dict(),
        }

    def return_to_base(self, drone_id: str, base_x: int = 0, base_y: int = 0) -> dict:
        """
        Attempt to return a drone with cargo to base at (base_x, base_y).
        Drone must be at the base location to deliver.
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}

        if drone.cargo is None:
            return {
                "success": False,
                "error": f"Drone {drone_id} is not carrying cargo.",
            }

        # Check if at base
        if drone.x != base_x or drone.y != base_y:
            return {
                "success": False,
                "error": (
                    f"Drone {drone_id} at ({drone.x}, {drone.y}), "
                    f"base is at ({base_x}, {base_y}). Move to base first."
                ),
            }

        # Deliver: record survivor, clear cargo
        survivor_id = drone.cargo
        self.survivors_at_base.append(survivor_id)
        drone.cargo = None
        drone.status = DroneStatus.IDLE
        drone.battery = max(0, drone.battery - 1)  # Return to base costs battery

        return {
            "success": True,
            "message": f"Drone {drone_id} delivered {survivor_id} to base!",
            "drone": drone.to_dict(),
            "survivors_at_base": len(self.survivors_at_base),
        }

    def get_survivor_count(self) -> dict:
        """Get counts of survivors: found, rescued, and still awaiting rescue."""
        # Count survivors still on grid
        survivors_on_grid = 0
        for row in self.grid.cells:
            for cell in row:
                if cell.cell_type == CellType.SURVIVOR:
                    survivors_on_grid += 1

        # Count in-cargo drones
        survivors_in_cargo = sum(1 for d in self.drones.values() if d.cargo)

        return {
            "on_grid": survivors_on_grid,
            "in_cargo": survivors_in_cargo,
            "rescued": len(self.survivors_at_base),
            "total_found": survivors_on_grid + survivors_in_cargo + len(self.survivors_at_base),
        }


# Rescue logic implemented in rescue_survivor(), return_to_base()
