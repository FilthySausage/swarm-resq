"""
environment_manager.py — Local Simulation Manager for Streamlit UI
Provides a self-contained environment that doesn't require external servers.
Manages Grid, Drones, and Survivors locally with direct state access.
"""

import asyncio
import json
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
import random

from environment.grid import Grid, CellType
from environment.drone import Drone, DroneSwarm, DroneStatus


@dataclass
class Survivor:
    """Survivor entity in the grid."""
    id: str
    x: int
    y: int
    rescued: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "rescued": self.rescued,
        }


class EnvironmentManager:
    """
    Local environment manager that provides simulation and state management
    without requiring external servers.
    """

    def __init__(self, width: int = 20, height: int = 20):
        self.width = width
        self.height = height
        self.grid = Grid(width, height)
        self.swarm = DroneSwarm(self.grid)
        self.survivors: Dict[str, Survivor] = {}
        self.survivors_at_base: List[str] = []
        self.mission_initialized = False
        self.turn_count = 0

    def initialize_mission(
        self,
        width: int = 20,
        height: int = 20,
        drone_count: int = 3,
        survivor_count: int = 5,
    ) -> Dict[str, Any]:
        """Initialize a new mission with grid, drones, and survivors."""
        self.width = width
        self.height = height
        self.grid = Grid(width, height)
        self.swarm = DroneSwarm(self.grid)
        self.survivors = {}
        self.survivors_at_base = []
        self.turn_count = 0

        # Place obstacles (30% of grid)
        obstacle_count = int((width * height) * 0.15)
        for _ in range(obstacle_count):
            x, y = random.randint(1, width - 1), random.randint(1, height - 1)
            if (x, y) != (0, 0):  # Don't place obstacle at base
                self.grid.set_cell_type(x, y, CellType.OBSTACLE)

        # Place hazards (10% of grid)
        hazard_count = int((width * height) * 0.05)
        for _ in range(hazard_count):
            x, y = random.randint(0, width - 1), random.randint(0, height - 1)
            if (x, y) != (0, 0) and self.grid.get_cell(x, y).cell_type == CellType.EMPTY:
                self.grid.set_cell_type(x, y, CellType.HAZARD)

        # Place drones at base
        for i in range(drone_count):
            drone_id = f"Drone-{i+1}"
            self.swarm.add_drone(drone_id, 0, 0)

        # Place survivors randomly
        for i in range(survivor_count):
            survivor_id = f"S{i+1}"
            while True:
                x, y = random.randint(0, width - 1), random.randint(0, height - 1)
                cell = self.grid.get_cell(x, y)
                if cell and cell.cell_type == CellType.EMPTY:
                    survivor = Survivor(survivor_id, x, y)
                    self.survivors[survivor_id] = survivor
                    self.grid.set_cell_type(x, y, CellType.SURVIVOR)
                    break

        self.mission_initialized = True
        return {
            "success": True,
            "message": f"Mission initialized: {width}x{height} grid, {drone_count} drones, {survivor_count} survivors",
            "state": self.get_state(),
        }

    def get_state(self) -> Dict[str, Any]:
        """Get the complete current state of the environment."""
        # Convert grid to serializable formayt
        grid_cells = []
        for row in self.grid.cells:
            grid_row = []
            for cell in row:
                grid_row.append({
                    "type": cell.cell_type.value,
                    "drone_id": cell.drone_id,
                })
            grid_cells.append(grid_row)

        # Get drone states
        drones = [drone.to_dict() for drone in self.swarm.drones.values()]

        # Get survivor states
        survivors = [survivor.to_dict() for survivor in self.survivors.values()]

        return {
            "turn": self.turn_count,
            "grid": {
                "width": self.width,
                "height": self.height,
                "cells": grid_cells,
            },
            "drones": drones,
            "survivors": survivors,
            "survivors_at_base": self.survivors_at_base,
            "mission_active": self.mission_initialized,
        }

    def move_drone(self, drone_id: str, dx: int, dy: int) -> Dict[str, Any]:
        """Move a drone by (dx, dy)."""
        if not self.mission_initialized:
            return {"success": False, "error": "Mission not initialized"}

        drone = self.swarm.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found"}

        # Battery cost
        if drone.battery <= 0:
            return {"success": False, "error": f"Drone {drone_id} has no battery"}

        drone.battery -= 1

        # Move logic
        new_x = drone.x + dx
        new_y = drone.y + dy

        if not self.grid.in_bounds(new_x, new_y):
            return {"success": False, "error": "Move out of bounds"}

        target_cell = self.grid.get_cell(new_x, new_y)
        if target_cell.cell_type == CellType.OBSTACLE:
            return {"success": False, "error": "Cell is an obstacle"}

        # Clear old cell
        self.grid.cells[drone.y][drone.x].drone_id = None
        old_type = self.grid.get_cell(drone.x, drone.y).cell_type
        if old_type == CellType.DRONE:
            self.grid.set_cell_type(drone.x, drone.y, CellType.EMPTY)

        # Update drone position
        drone.x = new_x
        drone.y = new_y
        drone.status = DroneStatus.MOVING

        # Set new cell
        self.grid.cells[new_y][new_x].drone_id = drone_id
        if target_cell.cell_type == CellType.EMPTY:
            self.grid.set_cell_type(new_x, new_y, CellType.DRONE)

        return {
            "success": True,
            "drone_id": drone_id,
            "new_position": (new_x, new_y),
            "battery_remaining": drone.battery,
        }

    def scan_area(self, drone_id: str, radius: int = 2) -> Dict[str, Any]:
        """Scan area around drone to reveal surroundings."""
        if not self.mission_initialized:
            return {"success": False, "error": "Mission not initialized"}

        drone = self.swarm.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found"}

        scanned_cells = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                x, y = drone.x + dx, drone.y + dy
                if self.grid.in_bounds(x, y):
                    cell = self.grid.get_cell(x, y)
                    scanned_cells.append({
                        "x": x,
                        "y": y,
                        "type": cell.cell_type.value,
                    })

        drone.status = DroneStatus.SCANNING
        return {
            "success": True,
            "drone_id": drone_id,
            "scan_radius": radius,
            "scanned_cells": scanned_cells,
        }

    def rescue_survivor(self, drone_id: str, target_x: int, target_y: int) -> Dict[str, Any]:
        """Rescue a survivor at the target location."""
        if not self.mission_initialized:
            return {"success": False, "error": "Mission not initialized"}

        drone = self.swarm.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found"}

        if drone.cargo:
            return {"success": False, "error": f"Drone already carrying: {drone.cargo}"}

        # Check if drone is adjacent to survivor
        distance = abs(drone.x - target_x) + abs(drone.y - target_y)
        if distance > 1:
            return {"success": False, "error": "Drone must be adjacent to survivor"}

        # Find survivor at target location
        survivor = None
        for s in self.survivors.values():
            if s.x == target_x and s.y == target_y and not s.rescued:
                survivor = s
                break

        if not survivor:
            return {"success": False, "error": f"No survivor at ({target_x}, {target_y})"}

        # Rescue the survivor
        drone.cargo = survivor.id
        drone.status = DroneStatus.RESCUING
        self.grid.set_cell_type(target_x, target_y, CellType.EMPTY)
        survivor.rescued = True

        return {
            "success": True,
            "drone_id": drone_id,
            "survivor_id": survivor.id,
            "message": f"Rescuing {survivor.id}",
        }

    def return_to_base(self, drone_id: str) -> Dict[str, Any]:
        """Return drone to base (0, 0) with cargo."""
        if not self.mission_initialized:
            return {"success": False, "error": "Mission not initialized"}

        drone = self.swarm.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found"}

        # Check if at base
        if drone.x == 0 and drone.y == 0:
            if drone.cargo:
                self.survivors_at_base.append(drone.cargo)
                drone.cargo = None
                drone.status = DroneStatus.IDLE
                drone.battery = 100  # Recharge at base
                return {
                    "success": True,
                    "drone_id": drone_id,
                    "message": f"Survivor delivered to base, drone recharged",
                    "survivors_rescued": len(self.survivors_at_base),
                }
            else:
                return {
                    "success": True,
                    "drone_id": drone_id,
                    "message": "Drone at base, no cargo",
                }
        else:
            return {
                "success": False,
                "error": f"Drone not at base. Current position: ({drone.x}, {drone.y})",
            }

    def get_survivor_counts(self) -> Dict[str, Any]:
        """Get counts of survivors."""
        total = len(self.survivors)
        rescued = len(self.survivors_at_base)
        remaining = sum(1 for s in self.survivors.values() if not s.rescued)
        return {
            "total_survivors": total,
            "rescued": rescued,
            "remaining": remaining,
        }

    def get_drone_state(self, drone_id: str) -> Dict[str, Any]:
        """Get state of a single drone."""
        drone = self.swarm.drones.get(drone_id)
        if not drone:
            return {"success": False, "error": f"Drone {drone_id} not found"}

        return {
            "success": True,
            "drone_id": drone_id,
            "state": drone.to_dict(),
        }

    def reset_mission(self) -> Dict[str, Any]:
        """Reset the entire mission."""
        self.mission_initialized = False
        self.grid = Grid(self.width, self.height)
        self.swarm = DroneSwarm(self.grid)
        self.survivors = {}
        self.survivors_at_base = []
        self.turn_count = 0
        return {"success": True, "message": "Mission reset"}
