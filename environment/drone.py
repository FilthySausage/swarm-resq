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
    MOVING_CONTINUOUS = "moving_continuous"  # New: continuous movement until stopped
    SCANNING = "scanning"
    RESCUING = "rescuing"
    RETURNING = "returning"
    STOPPED = "stopped"  # New: indicates movement has stopped


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

    def move_until_detect(self, drone_id: str, direction_x: int, direction_y: int, scan_radius: int = 2, max_steps: int = 10) -> dict:
        """
        Move a drone in a direction until it detects a survivor, hazard, or obstacle.
        Optimizes API calls by combining movement and scanning.
        
        Args:
            drone_id: Drone identifier
            direction_x: Direction X (-1, 0, or 1)
            direction_y: Direction Y (-1, 0, or 1)
            scan_radius: Scan radius after each move (default 2)
            max_steps: Maximum number of steps before stopping (default 10)
            
        Returns:
            Dict with:
            - success: Whether detection occurred
            - drone: Final drone state
            - moves_count: Number of moves executed
            - path: List of positions traversed
            - detections: List of detected objects {x, y, type}
            - final_position: Final drone coordinates
            - stopped_reason: Why movement stopped (detected, boundary, max_steps, battery, obstacle)
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        if direction_x == 0 and direction_y == 0:
            return {"success": False, "error": "Invalid direction: must move at least one coordinate."}
        
        path = [{"x": drone.x, "y": drone.y, "step": 0}]  # Starting position
        all_detections = []
        steps_taken = 0
        stopped_reason = "max_steps"
        drone.status = DroneStatus.MOVING_CONTINUOUS  # Mark continuous movement start
        
        while steps_taken < max_steps:
            # Check battery before moving
            if drone.battery < 5:
                stopped_reason = "battery"
                break
            
            # Try to move
            new_x, new_y = drone.x + direction_x, drone.y + direction_y
            
            # Check bounds
            if not self.grid.in_bounds(new_x, new_y):
                stopped_reason = "boundary"
                break
            
            # Check for obstacle
            target_cell = self.grid.get_cell(new_x, new_y)
            if target_cell.cell_type == CellType.OBSTACLE:
                stopped_reason = "obstacle"
                break
            
            # Perform the move
            self.grid.cells[drone.y][drone.x].drone_id = None
            self.grid.set_cell_type(drone.x, drone.y, CellType.EMPTY)
            
            drone.x, drone.y = new_x, new_y
            drone.battery = max(0, drone.battery - 1)
            
            self.grid.cells[new_y][new_x].drone_id = drone_id
            self.grid.set_cell_type(new_x, new_y, CellType.DRONE)
            
            path.append({"x": drone.x, "y": drone.y, "step": steps_taken + 1})
            steps_taken += 1
            
            # Scan after movement
            detections = []
            for dy in range(-scan_radius, scan_radius + 1):
                for dx in range(-scan_radius, scan_radius + 1):
                    cx, cy = drone.x + dx, drone.y + dy
                    cell = self.grid.get_cell(cx, cy)
                    if cell and cell.cell_type not in (CellType.EMPTY, CellType.DRONE):
                        detection = {"x": cx, "y": cy, "type": cell.cell_type.value}
                        detections.append(detection)
                        all_detections.append(detection)
            
            # Stop if detected something
            if detections:
                stopped_reason = "detected"
                break
        
        drone.status = DroneStatus.STOPPED  # Mark movement complete
        
        return {
            "success": True,
            "drone": drone.to_dict(),
            "moves_count": steps_taken,
            "path": path,  # Full path with all intermediate positions
            "detections": all_detections,
            "final_position": {"x": drone.x, "y": drone.y},
            "stopped_reason": stopped_reason,
        }

    def move_continuous_until_stopped(self, drone_id: str, direction_x: int, direction_y: int) -> dict:
        """
        OPTIMIZED: Move drone continuously in a direction until movement can't continue.
        Returns full traversed path as a single response to minimize API calls.
        
        This is the primary method for efficient exploration - drone moves continuously
        without interruption until hitting a boundary, obstacle, or battery limit.
        
        Args:
            drone_id: Drone identifier
            direction_x: Direction X (-1, 0, or 1)
            direction_y: Direction Y (-1, 0, or 1)
        
        Returns:
            Dict with:
            - path: Complete list of all positions in order
            - moves_count: Total steps taken
            - stopped_reason: Why movement stopped (boundary, obstacle, battery)
            - final_position: Last position before stopping
            - battery_used: Total battery consumed
            - drone: Final drone state
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        if direction_x == 0 and direction_y == 0:
            return {"success": False, "error": "Invalid direction"}
        
        path = [{"x": drone.x, "y": drone.y, "step": 0}]
        initial_battery = drone.battery
        steps_taken = 0
        dropped_reason = None
        
        drone.status = DroneStatus.MOVING_CONTINUOUS
        
        # Move continuously without stopping until we can't move anymore
        while True:
            # Stop conditions
            if drone.battery < 5:
                dropped_reason = "battery"
                break
            
            new_x, new_y = drone.x + direction_x, drone.y + direction_y
            
            if not self.grid.in_bounds(new_x, new_y):
                dropped_reason = "boundary"
                break
            
            target_cell = self.grid.get_cell(new_x, new_y)
            if target_cell.cell_type == CellType.OBSTACLE:
                dropped_reason = "obstacle"
                break
            
            # Execute move
            self.grid.cells[drone.y][drone.x].drone_id = None
            self.grid.set_cell_type(drone.x, drone.y, CellType.EMPTY)
            
            drone.x, drone.y = new_x, new_y
            drone.battery = max(0, drone.battery - 1)
            
            self.grid.cells[new_y][new_x].drone_id = drone_id
            self.grid.set_cell_type(new_x, new_y, CellType.DRONE)
            
            path.append({"x": drone.x, "y": drone.y, "step": steps_taken + 1})
            steps_taken += 1
        
        drone.status = DroneStatus.STOPPED
        
        return {
            "success": True,
            "path": path,
            "moves_count": steps_taken,
            "stopped_reason": dropped_reason,
            "final_position": {"x": drone.x, "y": drone.y},
            "battery_used": initial_battery - drone.battery,
            "battery_remaining": drone.battery,
            "drone": drone.to_dict(),
        }
        """
        Move a drone in a direction until it detects a survivor, hazard, or obstacle.
        Optimizes API calls by combining movement and scanning.
        
        Args:
            drone_id: Drone identifier
            direction_x: Direction X (-1, 0, or 1)
            direction_y: Direction Y (-1, 0, or 1)
            scan_radius: Scan radius after each move (default 2)
            max_steps: Maximum number of steps before stopping (default 10)
            
        Returns:
            Dict with:
            - success: Whether detection occurred
            - drone: Final drone state
            - moves_count: Number of moves executed
            - detections: List of detected objects {x, y, type}
            - final_position: Final drone coordinates
            - stopped_reason: Why movement stopped (detected, boundary, max_steps, battery, obstacle)
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        if direction_x == 0 and direction_y == 0:
            return {"success": False, "error": "Invalid direction: must move at least one coordinate."}
        
        moves = []
        all_detections = []
        steps_taken = 0
        stopped_reason = "max_steps"
        
        while steps_taken < max_steps:
            # Check battery before moving
            if drone.battery < 5:
                stopped_reason = "battery"
                break
            
            # Try to move
            new_x, new_y = drone.x + direction_x, drone.y + direction_y
            
            # Check bounds
            if not self.grid.in_bounds(new_x, new_y):
                stopped_reason = "boundary"
                break
            
            # Check for obstacle
            target_cell = self.grid.get_cell(new_x, new_y)
            if target_cell.cell_type == CellType.OBSTACLE:
                stopped_reason = "obstacle"
                break
            
            # Perform the move
            self.grid.cells[drone.y][drone.x].drone_id = None
            self.grid.set_cell_type(drone.x, drone.y, CellType.EMPTY)
            
            drone.x, drone.y = new_x, new_y
            drone.status = DroneStatus.MOVING
            drone.battery = max(0, drone.battery - 1)
            
            self.grid.cells[new_y][new_x].drone_id = drone_id
            self.grid.set_cell_type(new_x, new_y, CellType.DRONE)
            
            moves.append({"step": steps_taken + 1, "x": drone.x, "y": drone.y})
            steps_taken += 1
            
            # Scan after movement
            drone.status = DroneStatus.SCANNING
            detections = []
            for dy in range(-scan_radius, scan_radius + 1):
                for dx in range(-scan_radius, scan_radius + 1):
                    cx, cy = drone.x + dx, drone.y + dy
                    cell = self.grid.get_cell(cx, cy)
                    if cell and cell.cell_type not in (CellType.EMPTY, CellType.DRONE):
                        detection = {"x": cx, "y": cy, "type": cell.cell_type.value}
                        detections.append(detection)
                        all_detections.append(detection)
            
            # Stop if detected something
            if detections:
                stopped_reason = "detected"
                break
        
        drone.status = DroneStatus.IDLE
        
        return {
            "success": True,
            "drone": drone.to_dict(),
            "moves_count": steps_taken,
            "moves_executed": moves,
            "detections": all_detections,
            "final_position": {"x": drone.x, "y": drone.y},
            "stopped_reason": stopped_reason,
        }

    def get_nearest_survivor(self) -> dict:
        """
        Find the nearest unrescued survivor from all drones (Manhattan distance).
        
        Returns:
            Dict with survivor location and distance
        """
        survivors = []
        for y in range(self.grid.height):
            for x in range(self.grid.width):
                cell = self.grid.get_cell(x, y)
                if cell and cell.cell_type == CellType.SURVIVOR:
                    survivors.append((x, y))
        
        if not survivors:
            return {"success": False, "error": "No survivors found on grid."}
        
        # Find nearest survivor from all drones
        nearest = None
        nearest_distance = float('inf')
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
        """
        Estimate battery cost to reach a target from a drone (Manhattan distance).
        Includes margin for scanning and emergency return.
        
        Args:
            drone_id: Drone identifier
            target_x: Target X coordinate
            target_y: Target Y coordinate
            
        Returns:
            Dict with battery estimates
        """
        drone = self.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        distance = abs(drone.x - target_x) + abs(drone.y - target_y)
        
        # Battery costs
        movement_cost = distance
        scanning_cost = distance // 2  # Assume scanning every other move
        rescue_cost = 2  # Rescue operation
        return_to_base_cost = abs(target_x) + abs(target_y) + 1  # Return to (0,0)
        
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
        """
        Get all hazard locations on the grid.
        
        Returns:
            Dict with list of hazard coordinates
        """
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
        """
        Get all obstacle locations on the grid.
        
        Returns:
            Dict with list of obstacle coordinates
        """
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


# Rescue logic implemented in rescue_survivor(), return_to_base()
