"""
collision_avoidance.py — Multi-Drone Collision Avoidance System

Implements:
1. Real-time collision detection for drone proximity
2. Dynamic path separation to avoid overlaps
3. Visited path tracking to mark explored areas
4. Safe movement planning with alternative direction suggestions

Features:
- Proximity-based conflict detection
- Safe direction analysis for nearby drones
- Visited cell tracking for exploration efficiency
- Integration with DroneSwarm movement logic
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional
from enum import Enum


class Direction(Enum):
    """Cardinal and diagonal directions for drone movement."""
    NORTH = (0, 1)
    SOUTH = (0, -1)
    EAST = (1, 0)
    WEST = (-1, 0)
    NORTHEAST = (1, 1)
    NORTHWEST = (-1, 1)
    SOUTHEAST = (1, -1)
    SOUTHWEST = (-1, -1)
    IDLE = (0, 0)


@dataclass
class DronePosition:
    """Tracks current position and trajectory of a drone."""
    drone_id: str
    current_x: int
    current_y: int
    previous_x: Optional[int] = None
    previous_y: Optional[int] = None
    status: str = "idle"  # idle, moving, scanning, rescuing, etc.
    
    def get_position(self) -> Tuple[int, int]:
        """Return current position as tuple."""
        return (self.current_x, self.current_y)
    
    def get_trajectory(self) -> Optional[Tuple[int, int]]:
        """Return movement direction based on previous position."""
        if self.previous_x is None or self.previous_y is None:
            return None
        return (self.current_x - self.previous_x, self.current_y - self.previous_y)


@dataclass
class CollisionAvoidanceManager:
    """
    Manages collision avoidance for multi-drone swarm.
    
    Attributes:
        grid_width: Grid width in cells
        grid_height: Grid height in cells
        proximity_threshold: Distance at which drones are considered "near"
        visited_cells: Set of (x, y) tuples representing visited paths
        drone_trajectories: Dict of drone_id -> DronePosition
    """
    grid_width: int
    grid_height: int
    proximity_threshold: int = 5
    visited_cells: Set[Tuple[int, int]] = field(default_factory=set)
    drone_trajectories: Dict[str, DronePosition] = field(default_factory=dict)
    
    def register_drone(self, drone_id: str, x: int, y: int) -> None:
        """Register a drone's initial position."""
        self.drone_trajectories[drone_id] = DronePosition(
            drone_id=drone_id,
            current_x=x,
            current_y=y
        )
        self.visited_cells.add((x, y))
    
    def unregister_drone(self, drone_id: str) -> None:
        """Remove a drone from tracking."""
        self.drone_trajectories.pop(drone_id, None)
    
    def update_drone_position(self, drone_id: str, new_x: int, new_y: int) -> None:
        """Update drone position and track visited path."""
        if drone_id not in self.drone_trajectories:
            self.register_drone(drone_id, new_x, new_y)
            return
        
        trajectory = self.drone_trajectories[drone_id]
        trajectory.previous_x = trajectory.current_x
        trajectory.previous_y = trajectory.current_y
        trajectory.current_x = new_x
        trajectory.current_y = new_y
        
        # Mark cell as visited
        self.visited_cells.add((new_x, new_y))
    
    def get_nearby_drones(self, drone_id: str) -> List[str]:
        """
        Get list of drones within proximity_threshold distance.
        Uses Manhattan distance for efficiency.
        """
        if drone_id not in self.drone_trajectories:
            return []
        
        drone_pos = self.drone_trajectories[drone_id]
        nearby = []
        
        for other_id, other_pos in self.drone_trajectories.items():
            if other_id == drone_id:
                continue
            
            manhattan_dist = (
                abs(drone_pos.current_x - other_pos.current_x) +
                abs(drone_pos.current_y - other_pos.current_y)
            )
            
            if manhattan_dist <= self.proximity_threshold:
                nearby.append(other_id)
        
        return nearby
    
    def get_occupied_cells(self, exclude_drone_id: Optional[str] = None) -> Set[Tuple[int, int]]:
        """
        Get all cells currently occupied by drones.
        
        Args:
            exclude_drone_id: If provided, exclude this drone from occupied cells
        
        Returns:
            Set of (x, y) tuples for occupied cells
        """
        occupied = set()
        for drone_id, pos in self.drone_trajectories.items():
            if exclude_drone_id and drone_id == exclude_drone_id:
                continue
            occupied.add((pos.current_x, pos.current_y))
        return occupied
    
    def is_cell_occupied(self, x: int, y: int, exclude_drone_id: Optional[str] = None) -> bool:
        """Check if a cell is occupied by another drone."""
        for drone_id, pos in self.drone_trajectories.items():
            if exclude_drone_id and drone_id == exclude_drone_id:
                continue
            if pos.current_x == x and pos.current_y == y:
                return True
        return False
    
    def is_cell_visited(self, x: int, y: int) -> bool:
        """Check if a cell has been visited before."""
        return (x, y) in self.visited_cells
    
    def has_drone_collision(self, drone_id: str, target_x: int, target_y: int) -> bool:
        """Check if target position would collide with another drone."""
        return self.is_cell_occupied(target_x, target_y, exclude_drone_id=drone_id)
    
    def get_safe_directions(
        self,
        drone_id: str,
        grid_width: Optional[int] = None,
        grid_height: Optional[int] = None
    ) -> List[Tuple[int, int]]:
        """
        Get list of safe directions (as dx, dy tuples) for a drone.
        Prioritizes unvisited cells, then unexplored directions away from nearby drones.
        
        Args:
            drone_id: Drone identifier
            grid_width: Grid width (uses self.grid_width if None)
            grid_height: Grid height (uses self.grid_height if None)
        
        Returns:
            List of (dx, dy) tuples, sorted by safety score (highest first)
        """
        if drone_id not in self.drone_trajectories:
            return []
        
        grid_w = grid_width or self.grid_width
        grid_h = grid_height or self.grid_height
        
        drone_pos = self.drone_trajectories[drone_id]
        x, y = drone_pos.current_x, drone_pos.current_y
        nearby_drones = self.get_nearby_drones(drone_id)
        
        # All possible directions (cardinal + diagonal)
        possible_moves = [
            (0, 1), (0, -1), (1, 0), (-1, 0),  # Cardinal
            (1, 1), (-1, -1), (1, -1), (-1, 1)  # Diagonal
        ]
        
        safe_directions = []
        
        for dx, dy in possible_moves:
            new_x, new_y = x + dx, y + dy
            
            # Check bounds
            if not (0 <= new_x < grid_w and 0 <= new_y < grid_h):
                continue
            
            # Check collision with other drones
            if self.is_cell_occupied(new_x, new_y, exclude_drone_id=drone_id):
                continue
            
            # Calculate safety score
            safety_score = self._calculate_safety_score(
                drone_id, new_x, new_y, nearby_drones
            )
            
            safe_directions.append(((dx, dy), safety_score))
        
        # Sort by safety score (descending)
        safe_directions.sort(key=lambda x: x[1], reverse=True)
        return [direction for direction, _ in safe_directions]
    
    def _calculate_safety_score(
        self,
        drone_id: str,
        target_x: int,
        target_y: int,
        nearby_drones: List[str]
    ) -> float:
        """
        Calculate safety score for a target position.
        Higher score = safer.
        
        Score components:
        - Unvisited cells: +10 (exploration priority)
        - Distance from nearby drones: +distance (separation)
        - Opposite direction from nearby drones: +5 (conflict avoidance)
        """
        score = 0.0
        
        # Reward unvisited cells
        if not self.is_cell_visited(target_x, target_y):
            score += 10.0
        
        # Reward distance from nearby drones (Manhattan distance)
        if nearby_drones:
            min_distance = float('inf')
            for other_id in nearby_drones:
                if other_id not in self.drone_trajectories:
                    continue
                other_pos = self.drone_trajectories[other_id]
                distance = (
                    abs(target_x - other_pos.current_x) +
                    abs(target_y - other_pos.current_y)
                )
                min_distance = min(min_distance, distance)
            
            score += min_distance
        
        # Prefer opposite directions from nearby drones
        if nearby_drones:
            drone_pos = self.drone_trajectories[drone_id]
            for other_id in nearby_drones:
                if other_id not in self.drone_trajectories:
                    continue
                other_pos = self.drone_trajectories[other_id]
                
                # Vector from this drone to target
                self_vector = (target_x - drone_pos.current_x, target_y - drone_pos.current_y)
                # Vector from this drone to nearby drone
                other_vector = (
                    other_pos.current_x - drone_pos.current_x,
                    other_pos.current_y - drone_pos.current_y
                )
                
                # If vectors point in opposite directions, reward it
                dot_product = self_vector[0] * other_vector[0] + self_vector[1] * other_vector[1]
                if dot_product < 0:  # Opposite directions
                    score += 5.0
        
        return score
    
    def get_separation_plan(self, drone_id: str) -> Optional[Tuple[int, int]]:
        """
        Get a recommended direction for a drone to separate from nearby drones.
        Returns (dx, dy) tuple or None if no separation needed.
        """
        nearby = self.get_nearby_drones(drone_id)
        if not nearby:
            return None
        
        # Get safe directions, which already accounts for separation
        safe_dirs = self.get_safe_directions(drone_id)
        return safe_dirs[0] if safe_dirs else None
    
    def mark_visited_path(self, path: List[Tuple[int, int]]) -> None:
        """Mark multiple cells as visited (e.g., from a continuous movement path)."""
        for x, y in path:
            self.visited_cells.add((x, y))
    
    def get_visited_cells(self) -> Set[Tuple[int, int]]:
        """Get all visited cells."""
        return self.visited_cells.copy()
    
    def get_unvisited_percentage(self) -> float:
        """Get percentage of grid that hasn't been visited."""
        total_cells = self.grid_width * self.grid_height
        visited_count = len(self.visited_cells)
        return ((total_cells - visited_count) / total_cells) * 100 if total_cells > 0 else 0
    
    def get_drone_status_report(self) -> Dict[str, Dict]:
        """
        Get comprehensive status report for all tracked drones.
        
        Returns:
            Dict of drone_id -> {position, nearby_drones, safe_directions, trajectory}
        """
        report = {}
        for drone_id, pos in self.drone_trajectories.items():
            nearby = self.get_nearby_drones(drone_id)
            safe_dirs = self.get_safe_directions(drone_id)
            trajectory = pos.get_trajectory()
            
            report[drone_id] = {
                "position": pos.get_position(),
                "status": pos.status,
                "nearby_drones": nearby,
                "nearby_count": len(nearby),
                "safe_directions_count": len(safe_dirs),
                "trajectory": trajectory,
                "collision_risk": len(nearby) > 0
            }
        
        return report
    
    def reset_visited_paths(self) -> None:
        """Clear all visited path data (e.g., for mission reset)."""
        self.visited_cells.clear()
    
    def reset_all(self) -> None:
        """Reset all collision avoidance state."""
        self.visited_cells.clear()
        self.drone_trajectories.clear()
