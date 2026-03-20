"""
drone.py — Drone State & Movement Logic

Defines the Drone dataclass and the DroneSwarm manager that tracks all active
Drones on the grid. Integrates collision avoidance for multi-drone coordination.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, List

from environment.grid import Grid, CellType
from orchestrator.collision_avoidance import CollisionAvoidanceManager


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
        
        # Initialize collision avoidance system
        self.collision_manager = CollisionAvoidanceManager(
            grid_width=grid.width,
            grid_height=grid.height,
            proximity_threshold=5
        )

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
            # Preserve survivor marker if present so survivor coordinates remain visible.
            if cell.cell_type != CellType.SURVIVOR:
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
        
        # Register drone with collision avoidance manager
        self.collision_manager.register_drone(drone_id, x, y)
        
        return drone

    def move_drone(self, drone_id: str, dx: int, dy: int) -> dict:
        """
        Move a drone by (dx, dy) using bottom-left origin coordinates.
        Includes collision avoidance check.
        Marks visited cells as scanned.
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
        
        # Check for drone collision
        if self.collision_manager.has_drone_collision(drone_id, new_x, new_y):
            return {
                "success": False,
                "error": f"Cell ({new_x}, {new_y}) occupied by another drone. Collision avoided.",
                "collision_detected": True,
            }

        self._clear_drone_from_cell(drone.x, drone.y)

        drone.x = new_x
        drone.y = new_y
        drone.status = DroneStatus.MOVING
        drone.battery = max(0, drone.battery - 1)

        self._place_drone_on_cell(drone_id, new_x, new_y)
        
        # Mark cell and surroundings as scanned (radius=1 for immediate vicinity)
        for dy_scan in [-1, 0, 1]:
            for dx_scan in [-1, 0, 1]:
                scan_x, scan_y = new_x + dx_scan, new_y + dy_scan
                if self.grid.in_bounds(scan_x, scan_y):
                    self.grid.mark_cell_scanned(scan_x, scan_y)
        
        # Update collision avoidance tracking
        self.collision_manager.update_drone_position(drone_id, new_x, new_y)
        
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

                # Mark cell as scanned
                self.grid.mark_cell_scanned(cx, cy)

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

    def _direction_to_target(self, from_x: int, from_y: int, target_x: int, target_y: int) -> str:
        """
        Calculate direction toward target using 8-directional movement.
        Uses Chebyshev distance (max of absolute differences) for 8-way movement.
        
        Args:
            from_x, from_y: Starting position
            target_x, target_y: Target position
            
        Returns:
            Direction string: north, south, east, west, north_east, north_west, south_east, south_west
        """
        dx = target_x - from_x
        dy = target_y - from_y
        
        # Normalize to -1, 0, 1
        x_dir = 0 if dx == 0 else (1 if dx > 0 else -1)
        y_dir = 0 if dy == 0 else (1 if dy > 0 else -1)
        
        # Map to direction names
        direction_map = {
            (0, 1): "north",
            (0, -1): "south",
            (1, 0): "east",
            (-1, 0): "west",
            (1, 1): "north_east",
            (-1, 1): "north_west",
            (1, -1): "south_east",
            (-1, -1): "south_west",
        }
        
        return direction_map.get((x_dir, y_dir), "north")

    def _get_adjacent_unscanned(self, drone_x: int, drone_y: int) -> list[tuple[int, int]]:
        """
        Get all adjacent unscanned cells (8-directional neighbors).
        
        Args:
            drone_x, drone_y: Drone position
            
        Returns:
            List of (x, y) for adjacent unscanned cells
        """
        adjacent_unscanned = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = drone_x + dx, drone_y + dy
                if self.grid.in_bounds(nx, ny):
                    cell = self.grid.get_cell(nx, ny)
                    if cell and not cell.scanned and cell.cell_type not in (CellType.OBSTACLE, CellType.HAZARD):
                        adjacent_unscanned.append((nx, ny))
        return adjacent_unscanned

    def _find_alternative_target(self, drone_id: str, preferred_target: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
        """
        Find alternative unscanned target if preferred target is crowded (anti-clustering).
        
        Args:
            drone_id: Current drone ID
            preferred_target: Original target (x, y) or None
            
        Returns:
            Alternative target (x, y) or None
        """
        if preferred_target is None:
            return None
        
        drone = self.drones.get(drone_id)
        if not drone:
            return None
        
        # Count drones targeting preferred target
        drones_targeting_preferred = 0
        for other_id, other_drone in self.drones.items():
            if other_id != drone_id:
                # Rough heuristic: if other drone is heading toward same target
                if other_drone.x == preferred_target[0] and other_drone.y == preferred_target[1]:
                    drones_targeting_preferred += 1
        
        # If multiple drones are nearby/converging, suggest alternative
        if drones_targeting_preferred >= 1:
            all_unscanned = self.grid.get_all_unscanned_cells()
            if len(all_unscanned) > 1:
                # Find second nearest unscanned (excluding preferred)
                nearest_alt = None
                nearest_dist = float('inf')
                for cell in all_unscanned:
                    if cell == preferred_target:
                        continue
                    dist = max(abs(cell[0] - drone.x), abs(cell[1] - drone.y))
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_alt = cell
                return nearest_alt
        
        return preferred_target

    def _handle_boundary(self, drone_x: int, drone_y: int) -> Optional[Tuple[int, int]]:
        """
        Redirect drone from boundary toward nearest unscanned region.
        
        Args:
            drone_x, drone_y: Drone position
            
        Returns:
            Recommended direction or None
        """
        # Check if drone is at or near boundary
        margin = 2
        at_boundary = (
            drone_x < margin or drone_x >= self.grid.width - margin or
            drone_y < margin or drone_y >= self.grid.height - margin
        )
        
        if not at_boundary:
            return None
        
        # Find unscanned cells in interior
        unscanned = self.grid.get_all_unscanned_cells()
        interior_unscanned = [
            (x, y) for x, y in unscanned
            if margin <= x < self.grid.width - margin and margin <= y < self.grid.height - margin
        ]
        
        if interior_unscanned:
            nearest = min(interior_unscanned, key=lambda c: max(abs(c[0] - drone_x), abs(c[1] - drone_y)))
            return nearest
        
        return None

    def get_exploration_state(self) -> dict:
        """
        Get comprehensive exploration state with intelligent movement recommendations.
        
        Implements:
        1. Adjacent unscanned cell priority (local movement rule)
        2. Nearest unscanned frontier detection (escape from scanned zones)
        3. Direction calculation toward target
        4. Anti-clustering to spread drones
        5. Boundary handling for edge cases
        
        Returns:
            Dict with unscanned cells, coverage %, and per-drone guidance including:
            - recommended_direction: Specific direction to move
            - target_cell: (x, y) of target unscanned cell
            - strategy: "adjacent_exploration", "frontier_push", or "idle"
        """
        unscanned_cells = self.grid.get_all_unscanned_cells()
        scanned_percentage = self.grid.get_scanned_percentage()
        
        drone_guidance = {}
        
        for drone_id, drone in self.drones.items():
            guidance = {
                "position": {"x": drone.x, "y": drone.y},
                "battery": drone.battery,
                "status": drone.status.value,
                "total_unscanned": len(unscanned_cells),
                "strategy": "idle",
                "target_cell": None,
                "recommended_direction": None,
                "reason": "No unscanned cells available"
            }
            
            # No unscanned cells left
            if not unscanned_cells:
                drone_guidance[drone_id] = guidance
                continue
            
            # Step 1: Check for adjacent unscanned cells (local exploration)
            adjacent_unscanned = self._get_adjacent_unscanned(drone.x, drone.y)
            
            if adjacent_unscanned:
                # Prefer adjacent unscanned exploration
                target = adjacent_unscanned[0]
                direction = self._direction_to_target(drone.x, drone.y, target[0], target[1])
                
                guidance.update({
                    "strategy": "adjacent_exploration",
                    "target_cell": target,
                    "recommended_direction": direction,
                    "reason": f"Exploring adjacent unscanned cell at {target}"
                })
                drone_guidance[drone_id] = guidance
                continue
            
            # Step 2: All adjacent cells are scanned - find frontier and escape
            nearest_unscanned = self.grid.get_nearest_unscanned_cell(drone.x, drone.y)
            
            if nearest_unscanned:
                # Apply anti-clustering: find alternative if crowded
                target = self._find_alternative_target(drone_id, nearest_unscanned)
                if target is None:
                    target = nearest_unscanned
                
                # Check boundary condition and redirect if needed
                boundary_redirect = self._handle_boundary(drone.x, drone.y)
                if boundary_redirect:
                    target = boundary_redirect
                
                direction = self._direction_to_target(drone.x, drone.y, target[0], target[1])
                distance = max(abs(target[0] - drone.x), abs(target[1] - drone.y))
                
                guidance.update({
                    "strategy": "frontier_push",
                    "target_cell": target,
                    "recommended_direction": direction,
                    "distance_to_target": distance,
                    "reason": f"Escaping scanned zone, pushing toward frontier at {target} ({distance} cells away)"
                })
            else:
                guidance.update({
                    "strategy": "exploration_complete",
                    "reason": "All reachable cells have been explored"
                })
            
            drone_guidance[drone_id] = guidance
        
        return {
            "total_unscanned_cells": len(unscanned_cells),
            "scanned_percentage": round(scanned_percentage, 2),
            "drones": drone_guidance,
            "exploration_priority": "unscanned_cells",
            "anti_clustering": True,
            "boundary_aware": True
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
        Includes collision avoidance.
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
            
            # Check for drone collision (new collision avoidance)
            if self.collision_manager.has_drone_collision(drone_id, new_x, new_y):
                stopped_reason = "drone_collision"
                break

            self._clear_drone_from_cell(drone.x, drone.y)
            drone.x, drone.y = new_x, new_y
            drone.battery = max(0, drone.battery - 1)
            self._place_drone_on_cell(drone_id, new_x, new_y)
            
            # Update collision avoidance tracking
            self.collision_manager.update_drone_position(drone_id, new_x, new_y)

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
        
        # Track visited path in collision manager
        path_coords = [(p["x"], p["y"]) for p in path]
        self.collision_manager.mark_visited_path(path_coords)
        
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
        Includes collision avoidance - stops if another drone is in the way.
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
            
            # Check for drone collision (new collision avoidance)
            if self.collision_manager.has_drone_collision(drone_id, new_x, new_y):
                stopped_reason = "drone_collision"
                break

            self._clear_drone_from_cell(drone.x, drone.y)
            drone.x, drone.y = new_x, new_y
            drone.battery = max(0, drone.battery - 1)
            self._place_drone_on_cell(drone_id, new_x, new_y)
            
            # Update collision avoidance tracking
            self.collision_manager.update_drone_position(drone_id, new_x, new_y)

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
        
        # Track visited path in collision manager
        path_coords = [(p["x"], p["y"]) for p in path]
        self.collision_manager.mark_visited_path(path_coords)
        
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

    # ================================================================
    # Collision Avoidance Methods
    # ================================================================

    def get_nearby_drones(self, drone_id: str) -> dict:
        """
        Get drones near a specified drone within proximity threshold.
        
        Returns information about nearby drones for coordination.
        """
        nearby_drones = self.collision_manager.get_nearby_drones(drone_id)
        nearby_info = []
        
        if drone_id not in self.drones:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        drone = self.drones[drone_id]
        
        for nearby_id in nearby_drones:
            other_drone = self.drones.get(nearby_id)
            if other_drone:
                distance = abs(drone.x - other_drone.x) + abs(drone.y - other_drone.y)
                nearby_info.append({
                    "drone_id": nearby_id,
                    "position": {"x": other_drone.x, "y": other_drone.y},
                    "distance": distance,
                    "status": other_drone.status.value,
                })
        
        return {
            "success": True,
            "drone_id": drone_id,
            "nearby_count": len(nearby_info),
            "nearby_drones": nearby_info,
            "proximity_threshold": self.collision_manager.proximity_threshold,
        }

    def get_safe_directions(self, drone_id: str) -> dict:
        """
        Get safe movement directions for a drone.
        Prioritizes unvisited cells and directions away from nearby drones.
        
        Returns list of (dx, dy) tuples sorted by safety.
        """
        if drone_id not in self.drones:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        safe_dirs = self.collision_manager.get_safe_directions(drone_id, self.grid.width, self.grid.height)
        
        return {
            "success": True,
            "drone_id": drone_id,
            "safe_directions": [{"dx": dx, "dy": dy} for dx, dy in safe_dirs],
            "safe_directions_count": len(safe_dirs),
        }

    def get_collision_status(self, drone_id: str) -> dict:
        """
        Get comprehensive collision and proximity information for a drone.
        """
        if drone_id not in self.drones:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        nearby = self.collision_manager.get_nearby_drones(drone_id)
        occupied = self.collision_manager.get_occupied_cells(exclude_drone_id=drone_id)
        
        return {
            "success": True,
            "drone_id": drone_id,
            "collision_risk": len(nearby) > 0,
            "nearby_drones_count": len(nearby),
            "nearby_drone_ids": nearby,
            "occupied_cells_count": len(occupied),
            "occupied_cells": [{"x": x, "y": y} for x, y in occupied],
        }

    def get_visited_paths(self) -> dict:
        """Get all cells that have been visited by any drone."""
        visited = self.collision_manager.get_visited_cells()
        return {
            "success": True,
            "visited_count": len(visited),
            "visited_cells": [{"x": x, "y": y} for x, y in visited],
            "grid_size": self.grid.width * self.grid.height,
            "visited_percentage": (len(visited) / (self.grid.width * self.grid.height)) * 100,
        }

    def get_unvisited_percentage(self) -> dict:
        """Get percentage of grid that hasn't been visited."""
        percentage = self.collision_manager.get_unvisited_percentage()
        return {
            "success": True,
            "unvisited_percentage": percentage,
            "visited_percentage": 100 - percentage,
        }

    def get_drone_separation_plan(self, drone_id: str) -> dict:
        """
        Get recommended direction for a drone to separate from nearby drones.
        Returns optimal direction or None if no separation needed.
        """
        if drone_id not in self.drones:
            return {"success": False, "error": f"Drone {drone_id} not found."}
        
        nearby = self.collision_manager.get_nearby_drones(drone_id)
        if not nearby:
            return {
                "success": True,
                "drone_id": drone_id,
                "separation_needed": False,
                "message": "No nearby drones. No separation needed.",
            }
        
        sep_plan = self.collision_manager.get_separation_plan(drone_id)
        if sep_plan:
            return {
                "success": True,
                "drone_id": drone_id,
                "separation_needed": True,
                "nearby_drones": nearby,
                "recommended_direction": {"dx": sep_plan[0], "dy": sep_plan[1]},
                "message": f"Separate from {len(nearby)} nearby drone(s)",
            }
        else:
            return {
                "success": True,
                "drone_id": drone_id,
                "separation_needed": True,
                "nearby_drones": nearby,
                "recommended_direction": None,
                "message": "Separation needed but no safe direction available",
            }

    def get_swarm_status_report(self) -> dict:
        """Get comprehensive status report for all drones and collisions."""
        report = self.collision_manager.get_drone_status_report()
        
        collision_risks = [d for d, info in report.items() if info.get("collision_risk")]
        
        return {
            "success": True,
            "total_drones": len(self.drones),
            "drones_with_collision_risk": len(collision_risks),
            "drones": report,
            "visited_percentage": 100 - self.collision_manager.get_unvisited_percentage(),
        }

    def reset_collision_tracking(self) -> dict:
        """Reset collision avoidance tracking (e.g., on mission reset)."""
        self.collision_manager.reset_visited_paths()
        return {
            "success": True,
            "message": "Collision avoidance tracking reset. Visited paths cleared.",
        }

