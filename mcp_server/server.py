"""
server.py — FastMCP Server with Async Support & State Management
Member 2 (MCP/API) workspace.

Exposes drone actions as MCP tools via FastMCP.
Features:
  - Async tool functions (non-blocking event loop)
  - asyncio.Lock for thread-safe concurrent access
  - Comprehensive input validation
  - Structured error handling
  - Mission reset/initialization

Run with:
    uvicorn mcp_server.server:app --reload --port 8000
"""

import asyncio
import logging
import random
from typing import Optional, Dict, Any
from enum import Enum

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from environment.grid import Grid, CellType, place_survivors, place_hazards, place_obstacles
from environment.drone import DroneSwarm

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simulation State Manager (Singleton with Async Lock)
# ---------------------------------------------------------------------------

class SimulationState(Enum):
    """Mission lifecycle states."""
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"


class SimulationEngine:
    """
    Thread-safe simulation engine with async lock for concurrent access.
    Manages grid state, drone swarm, and mission lifecycle.
    
    Usage:
        engine = SimulationEngine()
        await engine.initialize_mission(width=20, height=20)
        result = await engine.move_drone("drone-1", 1, 0)
    """
    
    _instance: Optional['SimulationEngine'] = None
    _lock: Optional[asyncio.Lock] = None
    
    def __new__(cls) -> 'SimulationEngine':
        """Singleton pattern for shared global state."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize engine (only once due to singleton)."""
        if not self._initialized:
            self._lock = asyncio.Lock()
            self.grid: Optional[Grid] = None
            self.swarm: Optional[DroneSwarm] = None
            self.state = SimulationState.NOT_STARTED
            self.move_count = 0
            self.mission_id = ""
            self._initialized = True
            logger.info("SimulationEngine initialized (singleton)")
    
    async def _ensure_initialized(self) -> None:
        """Ensure grid and swarm are initialized."""
        if self.grid is None or self.swarm is None:
            raise RuntimeError(
                "Simulation not initialized. Call initialize_mission() first."
            )
    
    async def initialize_mission(
        self,
        width: int = 20,
        height: int = 20,
        drone_count: int = 3,
        survivor_count: int = 5,
        hazard_count: int = 8,
        obstacle_count: int = 15,
    ) -> Dict[str, Any]:
        """
        Initialize a new mission with grid and drones.
        
        Args:
            width: Grid width
            height: Grid height
            drone_count: Number of drones to deploy
            survivor_count: Number of survivors to place
            hazard_count: Number of hazards
            obstacle_count: Number of obstacles
            
        Returns:
            Initialization result with grid info and drone list
        """
        async with self._lock:
            logger.info(f"Initializing mission: {width}x{height} grid, {drone_count} drones")

            try:
                from orchestrator.path_tracker import clear_paths
                clear_paths()
            except Exception:
                pass
            
            # Create fresh grid
            self.grid = Grid(width=width, height=height)
            self.swarm = DroneSwarm(grid=self.grid)
            self.state = SimulationState.ACTIVE
            self.move_count = 0
            self.mission_id = f"mission_{int(__import__('time').time())}"
            
            # Deploy drones at randomized empty coordinates
            drone_ids = []
            occupied = set()
            for i in range(drone_count):
                drone_id = f"drone-{i + 1}"
                while True:
                    x = random.randint(0, width - 1)
                    y = random.randint(0, height - 1)
                    if (x, y) not in occupied:
                        occupied.add((x, y))
                        self.swarm.add_drone(drone_id, x=x, y=y)
                        drone_ids.append(drone_id)
                        break
            
            # Place environment elements
            place_obstacles(self.grid, count=obstacle_count)
            place_hazards(self.grid, count=hazard_count)
            survivors = place_survivors(self.grid, count=survivor_count)
            
            result = {
                "success": True,
                "mission_id": self.mission_id,
                "grid": {"width": width, "height": height, "total_cells": width * height},
                "drones": drone_ids,
                "environment": {
                    "survivors": len(survivors),
                    "hazards": hazard_count,
                    "obstacles": obstacle_count,
                },
                "message": f"Mission initialized with {len(drone_ids)} drones",
            }
            
            logger.info(f"Mission initialized: {result['message']}")
            return result
    
    async def reset_mission(self) -> Dict[str, Any]:
        """Reset mission to initial state."""
        async with self._lock:
            logger.info("Resetting mission")
            try:
                from orchestrator.path_tracker import clear_paths
                clear_paths()
            except Exception:
                pass
            self.grid = None
            self.swarm = None
            self.state = SimulationState.NOT_STARTED
            self.move_count = 0
            return {"success": True, "message": "Mission reset"}
    
    async def get_swarm_state(self) -> Dict[str, Any]:
        """
        Get full swarm and grid state.
        
        Returns:
            Dict with drones, grid, survivors_rescued, etc.
        """
        async with self._lock:
            await self._ensure_initialized()
            
            state = self.swarm.get_state()
            state.update({
                "mission_id": self.mission_id,
                "state": self.state.value,
                "move_count": self.move_count,
                "survivors_at_base": self.swarm.survivors_at_base,
            })
            return state
    
    async def move_drone(
        self,
        drone_id: str,
        dx: int,
        dy: int,
    ) -> Dict[str, Any]:
        """
        Move a drone by (dx, dy).
        
        Args:
            drone_id: Drone identifier
            dx: X delta (-1, 0, or 1)
            dy: Y delta (-1, 0, or 1)
            
        Returns:
            Result with success status and new drone state
            
        Raises:
            ValueError: If validation fails
        """
        async with self._lock:
            await self._ensure_initialized()
            
            # Validate inputs
            if not isinstance(dx, int) or not isinstance(dy, int):
                raise ValueError("dx and dy must be integers")
            
            if abs(dx) > 1 or abs(dy) > 1:
                raise ValueError(f"Invalid delta: ({dx}, {dy}). Must be in [-1, 1]")
            
            if dx == 0 and dy == 0:
                raise ValueError("Move must change at least one coordinate")
            
            if drone_id not in self.swarm.drones:
                raise ValueError(f"Drone '{drone_id}' not found")
            
            drone = self.swarm.drones[drone_id]
            
            # Check battery
            if drone.battery < 5:
                return {
                    "success": False,
                    "error": f"Drone {drone_id} battery too low ({drone.battery}%) to move",
                }
            
            # Perform move
            result = self.swarm.move_drone(drone_id, dx, dy)
            
            if result["success"]:
                self.move_count += 1
                logger.info(f"Moved {drone_id} by ({dx},{dy}) → ({drone.x},{drone.y})")
            else:
                logger.warning(f"Move failed for {drone_id}: {result.get('error', 'unknown')}")
            
            return result
    
    async def scan_area(
        self,
        drone_id: Optional[str] = None,
        radius: int = 2,
    ) -> Dict[str, Any]:
        """
        Scan cells within radius of drone.
        
        Args:
            drone_id: Drone identifier
            radius: Scan radius (default 2)
            
        Returns:
            List of detections
            
        Raises:
            ValueError: If drone not found
        """
        async with self._lock:
            await self._ensure_initialized()
            
            if drone_id is not None and drone_id not in self.swarm.drones:
                raise ValueError(f"Drone '{drone_id}' not found")
            
            if radius < 1 or radius > 5:
                raise ValueError(f"Invalid radius: {radius}. Must be in [1, 5]")
            
            result = self.swarm.scan_area(drone_id, radius)
            logger.info(f"Scanned area around {drone_id} (radius {radius})")
            return result
    
    async def rescue_survivor(
        self,
        drone_id: str,
        target_x: int,
        target_y: int,
    ) -> Dict[str, Any]:
        """
        Rescue survivor at (target_x, target_y).
        
        Args:
            drone_id: Drone identifier
            target_x: Survivor X coordinate
            target_y: Survivor Y coordinate
            
        Returns:
            Result with rescue status
            
        Raises:
            ValueError: If validation fails
        """
        async with self._lock:
            await self._ensure_initialized()
            
            if drone_id not in self.swarm.drones:
                raise ValueError(f"Drone '{drone_id}' not found")
            
            # Validate coordinates
            if not self.grid.in_bounds(target_x, target_y):
                raise ValueError(
                    f"Survivor location ({target_x}, {target_y}) out of bounds"
                )
            
            result = self.swarm.rescue_survivor(drone_id, target_x, target_y)
            
            if result["success"]:
                logger.info(f"{drone_id} rescued survivor at ({target_x}, {target_y})")
            else:
                logger.warning(f"Rescue failed: {result.get('error', 'unknown')}")
            
            return result
    
    async def return_to_base(self, drone_id: str) -> Dict[str, Any]:
        """
        Return drone with cargo to base.
        
        Args:
            drone_id: Drone identifier
            
        Returns:
            Result with delivery status
            
        Raises:
            ValueError: If drone not found
        """
        async with self._lock:
            await self._ensure_initialized()
            
            if drone_id not in self.swarm.drones:
                raise ValueError(f"Drone '{drone_id}' not found")
            
            result = self.swarm.return_to_base(drone_id, base_x=0, base_y=0)
            
            if result["success"]:
                survivors_count = len(self.swarm.survivors_at_base)
                logger.info(f"{drone_id} delivered survivor. Total rescued: {survivors_count}")
            else:
                logger.warning(f"Return to base failed: {result.get('error', 'unknown')}")
            
            return result
    
    async def get_survivor_counts(self) -> Dict[str, Any]:
        """Get survivor counts across all states."""
        async with self._lock:
            await self._ensure_initialized()
            counts = self.swarm.get_survivor_count()
            logger.info(f"Survivor counts: {counts}")
            return counts
    
    async def move_until_detect(
        self,
        drone_id: str,
        direction_x: int,
        direction_y: int,
        scan_radius: int = 2,
        max_steps: int = 10,
    ) -> Dict[str, Any]:
        """
        Move a drone in a direction until it detects something.
        Optimizes API calls by combining movement and scanning.
        
        Args:
            drone_id: Drone identifier
            direction_x: Direction X (-1, 0, or 1)
            direction_y: Direction Y (-1, 0, or 1)
            scan_radius: Scan radius after each move
            max_steps: Maximum number of steps
            
        Returns:
            Result with moves, detections, and stop reason
        """
        async with self._lock:
            await self._ensure_initialized()
            
            if drone_id not in self.swarm.drones:
                raise ValueError(f"Drone '{drone_id}' not found")
            
            result = self.swarm.move_until_detect(drone_id, direction_x, direction_y, scan_radius, max_steps)
            logger.info(f"Move until detect {drone_id}: {result.get('moves_count')} steps, stopped_reason={result.get('stopped_reason')}")
            return result
    
    async def move_continuous_until_stopped(
        self,
        drone_id: str,
        direction_x: int,
        direction_y: int,
    ) -> Dict[str, Any]:
        """
        OPTIMIZED: Move drone continuously until it can't move anymore.
        Returns full path in single API call to minimize latency.
        
        Args:
            drone_id: Drone identifier
            direction_x: Direction X (-1, 0, or 1)
            direction_y: Direction Y (-1, 0, or 1)
        
        Returns:
            Dict with full path, moves count, and stop reason
        """
        async with self._lock:
            await self._ensure_initialized()
            
            if drone_id not in self.swarm.drones:
                raise ValueError(f"Drone '{drone_id}' not found")
            
            result = self.swarm.move_continuous_until_stopped(drone_id, direction_x, direction_y)
            logger.info(f"Continuous move {drone_id}: {result.get('moves_count')} steps, stopped={result.get('stopped_reason')}")
            return result
    

        """Find the nearest unrescued survivor."""
        async with self._lock:
            await self._ensure_initialized()
            result = self.swarm.get_nearest_survivor()
            logger.info(f"Nearest survivor query: {result}")
            return result
    
    async def estimate_battery_to_target(
        self,
        drone_id: str,
        target_x: int,
        target_y: int,
    ) -> Dict[str, Any]:
        """Estimate battery cost to reach a target."""
        async with self._lock:
            await self._ensure_initialized()
            
            if drone_id not in self.swarm.drones:
                raise ValueError(f"Drone '{drone_id}' not found")
            
            result = self.swarm.estimate_battery_to_target(drone_id, target_x, target_y)
            logger.info(f"Battery estimate for {drone_id} to ({target_x}, {target_y}): {result.get('estimated_costs', {}).get('total')}%")
            return result
    
    async def get_hazard_map(self) -> Dict[str, Any]:
        """Get all hazard locations."""
        async with self._lock:
            await self._ensure_initialized()
            result = self.swarm.get_hazard_map()
            logger.info(f"Hazard map query: {result.get('hazard_count')} hazards found")
            return result
    
    async def get_obstacle_map(self) -> Dict[str, Any]:
        """Get all obstacle locations."""
        async with self._lock:
            await self._ensure_initialized()
            result = self.swarm.get_obstacle_map()
            logger.info(f"Obstacle map query: {result.get('obstacle_count')} obstacles found")
            return result


# ---------------------------------------------------------------------------
# Global Simulation Engine Instance
# ---------------------------------------------------------------------------
engine = SimulationEngine()

# ---------------------------------------------------------------------------
# FastMCP app with Async Tool Handlers
# ---------------------------------------------------------------------------
mcp = FastMCP("swarm-resq")

#Debug
@mcp.tool()
async def ping():
    """Test MCP connection"""
    return "pong"

# Tool: Initialize Mission
@mcp.tool()
async def initialize_mission(
    width: int = 20,
    height: int = 20,
    drone_count: int = 3,
    survivor_count: int = 5,
) -> dict:
    """
    Initialize a new rescue mission.
    
    Args:
        width: Grid width (default 20)
        height: Grid height (default 20)
        drone_count: Number of drones (default 3, max 5)
        survivor_count: Number of survivors (default 5)
    
    Returns:
        Mission initialization result with grid info and drone IDs
    """
    try:
        if drone_count < 1 or drone_count > 5:
            raise ValueError(f"drone_count must be in [1, 5], got {drone_count}")
        if width < 10 or height < 10:
            raise ValueError(f"Grid must be at least 10x10, got {width}x{height}")
        
        result = await engine.initialize_mission(
            width=width,
            height=height,
            drone_count=drone_count,
            survivor_count=survivor_count,
        )
        return result
    except Exception as e:
        logger.error(f"initialize_mission failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Get Swarm State
@mcp.tool()
async def get_swarm_state() -> dict:
    """
    Get the full swarm state and grid.
    
    Returns:
        Dict with all drone states, grid layout, survivors_at_base, etc.
    """
    try:
        state = await engine.get_swarm_state()
        return state
    except Exception as e:
        logger.error(f"get_swarm_state failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Move Drone
@mcp.tool()
async def move_drone(drone_id: str, dx: int, dy: int) -> dict:
    """
    Move a drone by (dx, dy) with battery consumption.
    
    Args:
        drone_id: Drone identifier (e.g. 'drone-1')
        dx: Horizontal delta in [-1, 0, 1]
        dy: Vertical delta in [-1, 0, 1]
    
    Returns:
        Result dict with success status and updated drone state
        
    Examples:
        move_drone("drone-1", dx=1, dy=0)    # Move east
        move_drone("drone-2", dx=-1, dy=-1)  # Move southwest
    """
    try:
        result = await engine.move_drone(drone_id, dx, dy)
        return result
    except ValueError as e:
        logger.warning(f"move_drone validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"move_drone failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Scan Area
@mcp.tool()
async def scan_area(drone_id: Optional[str] = None, radius: int = 2) -> dict:
    """
    Scan the area around a drone for survivors, hazards, obstacles.
    
    Args:
        drone_id: Drone identifier
        radius: Scan radius in cells (default 2, range [1, 5])
    
    Returns:
        Dict with detections list containing {x, y, type} objects
        
    Types: 'S' (survivor), 'X' (hazard), '#' (obstacle), '.' (empty)
    """
    try:
        result = await engine.scan_area(drone_id, radius)
        return result
    except ValueError as e:
        logger.warning(f"scan_area validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"scan_area failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Rescue Survivor
@mcp.tool()
async def rescue_survivor(drone_id: str, target_x: int, target_y: int) -> dict:
    """
    Pick up a survivor at (target_x, target_y).
    Drone must be at or adjacent to the survivor.
    
    Args:
        drone_id: Drone identifier
        target_x: Survivor X coordinate
        target_y: Survivor Y coordinate
    
    Returns:
        Result dict with success status and updated drone state
        
    Notes:
        - Drone must have no cargo
        - Costs 2% battery
        - After rescue, use return_to_base() to complete mission
    """
    try:
        result = await engine.rescue_survivor(drone_id, target_x, target_y)
        return result
    except ValueError as e:
        logger.warning(f"rescue_survivor validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"rescue_survivor failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Return to Base
@mcp.tool()
async def return_to_base(drone_id: str) -> dict:
    """
    Return a drone with cargo to base at (0, 0) to complete rescue.
    Drone must be carrying cargo and physically at base location.
    
    Args:
        drone_id: Drone identifier
    
    Returns:
        Result dict with delivery confirmation and survivor count
        
    Notes:
        - Only works when drone is at (0, 0)
        - Completes rescue mission for that survivor
        - Drone battery recharged after delivery
    """
    try:
        result = await engine.return_to_base(drone_id)
        return result
    except ValueError as e:
        logger.warning(f"return_to_base validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"return_to_base failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Get Survivor Counts
@mcp.tool()
async def get_survivor_counts() -> dict:
    """
    Get counts of survivors in all states.
    
    Returns:
        Dict with:
        - on_grid: Survivors still on grid
        - in_cargo: Survivors in drone cargo
        - rescued: Survivors at base
        - total_found: Total discovered so far
    """
    try:
        counts = await engine.get_survivor_counts()
        return counts
    except Exception as e:
        logger.error(f"get_survivor_counts failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Move Until Detect
@mcp.tool()
async def move_until_detect(drone_id: str, direction_x: int, direction_y: int, scan_radius: int = 2, max_steps: int = 10) -> dict:
    """
    Move a drone in a direction until it detects a survivor, hazard, or obstacle.
    Optimizes API calls by combining multiple movements and scans into one call.
    
    Args:
        drone_id: Drone identifier (e.g., 'drone-1')
        direction_x: Direction X (-1, 0, or 1)
        direction_y: Direction Y (-1, 0, or 1)
        scan_radius: Scan radius after each move (default 2, range [1, 5])
        max_steps: Maximum steps to move (default 10)
    
    Returns:
        Dict with:
        - moves_count: Number of moves executed
        - detections: List of detected objects {x, y, type}
        - stopped_reason: Why movement stopped (detected, boundary, obstacle, battery, max_steps)
        - final_position: Final drone coordinates
        
    Example:
        move_until_detect("drone-1", 1, 0, scan_radius=2, max_steps=10)  # Move east until detection
    """
    try:
        result = await engine.move_until_detect(drone_id, direction_x, direction_y, scan_radius, max_steps)
        return result
    except ValueError as e:
        logger.warning(f"move_until_detect validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"move_until_detect failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Move Continuous Until Stopped (OPTIMIZED)
@mcp.tool()
async def move_continuous_until_stopped(drone_id: str, direction_x: int, direction_y: int) -> dict:
    """
    OPTIMIZED: Move drone continuously in one direction until it cannot move anymore.
    Returns entire path in single API call - dramatically reduces latency and API calls.
    
    This is the PRIMARY method for efficient exploration in Swarm-ResQ.
    Instead of multiple move_drone calls, use this for continuous movement with full path.
    
    Args:
        drone_id: Drone identifier (e.g., 'drone-1')
        direction_x: Direction X (-1, 0, or 1)
        direction_y: Direction Y (-1, 0, or 1)
    
    Returns:
        Dict with:
        - path: Complete list of traversed positions [{x, y, step}, ...]
        - moves_count: Total steps taken
        - stopped_reason: Why movement stopped (boundary, obstacle, battery)
        - final_position: Last position
        - battery_used: Battery consumed
        - drone: Final drone state
    
    Example:
        # Move drone-1 east until hitting boundary/obstacle
        result = move_continuous_until_stopped("drone-1", 1, 0)
        print(f"Moved {result['moves_count']} steps, stopped by {result['stopped_reason']}")
        print(f"Full path: {result['path']}")
    
    Benefits:
        - 1 API call instead of 10-20
        - Complete path history included
        - Same battery cost per move
        - 20x faster than sequential moves
    """
    try:
        result = await engine.move_continuous_until_stopped(drone_id, direction_x, direction_y)
        
        # Track path for UI visualization
        if result.get("success"):
            from orchestrator.path_tracker import store_movement_path
            store_movement_path(drone_id, result)
        
        return result
    except ValueError as e:
        logger.warning(f"move_continuous_until_stopped validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"move_continuous_until_stopped failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Get Nearest Survivor
@mcp.tool()
async def get_nearest_survivor() -> dict:
    """
    Find the nearest unrescued survivor from all drones.
    Uses Manhattan distance to calculate proximity.
    
    Returns:
        Dict with:
        - location: {x, y} coordinates of nearest survivor
        - distance: Manhattan distance from nearest drone
        - nearest_drone: Which drone is closest
        
    Useful for: Planning which drone should go rescue next
    """
    try:
        result = await engine.get_nearest_survivor()
        return result
    except Exception as e:
        logger.error(f"get_nearest_survivor failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Estimate Battery to Target
@mcp.tool()
async def estimate_battery_to_target(drone_id: str, target_x: int, target_y: int) -> dict:
    """
    Estimate if a drone has enough battery to reach a target and return to base.
    Includes estimates for movement, scanning, rescue, and return.
    
    Args:
        drone_id: Drone identifier
        target_x: Target X coordinate
        target_y: Target Y coordinate
    
    Returns:
        Dict with:
        - current_battery: Drone's remaining battery
        - estimated_costs: Breakdown of movement, scanning, rescue, return costs
        - can_afford: Boolean if drone can complete mission
        - battery_shortfall: How much battery is needed (if insufficient)
        
    Useful for: Planning which drones can afford missions
    """
    try:
        result = await engine.estimate_battery_to_target(drone_id, target_x, target_y)
        return result
    except ValueError as e:
        logger.warning(f"estimate_battery_to_target validation error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"estimate_battery_to_target failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Get Hazard Map
@mcp.tool()
async def get_hazard_map() -> dict:
    """
    Get all known hazard locations on the grid.
    Hazards are dangerous areas that block movement and discovery.
    
    Returns:
        Dict with:
        - hazards: List of {x, y} coordinates
        - hazard_count: Total number of hazards
        
    Useful for: Planning drone routes around hazard zones
    """
    try:
        result = await engine.get_hazard_map()
        return result
    except Exception as e:
        logger.error(f"get_hazard_map failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Get Obstacle Map
@mcp.tool()
async def get_obstacle_map() -> dict:
    """
    Get all known obstacle locations on the grid.
    Obstacles block drone movement completely.
    
    Returns:
        Dict with:
        - obstacles: List of {x, y} coordinates
        - obstacle_count: Total number of obstacles
        
    Useful for: Planning optimal drone paths
    """
    try:
        result = await engine.get_obstacle_map()
        return result
    except Exception as e:
        logger.error(f"get_obstacle_map failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Get Drone State
@mcp.tool()
async def get_drone_state(drone_id: str) -> dict:
    """
    Get state of a single drone.
    
    Args:
        drone_id: Drone identifier
    
    Returns:
        Dict with drone position, battery, cargo, status
    """
    try:
        state = await engine.get_swarm_state()
        for drone in state.get("drones", []):
            if drone["drone_id"] == drone_id:
                return {"success": True, "drone": drone}
        return {"success": False, "error": f"Drone '{drone_id}' not found"}
    except Exception as e:
        logger.error(f"get_drone_state failed: {e}")
        return {"success": False, "error": str(e)}


# Tool: Reset Mission
@mcp.tool()
async def reset_mission() -> dict:
    """
    Reset the mission to initial state. Clears all drones and grid.
    Use initialize_mission() to start a new mission.
    
    Returns:
        Success confirmation
    """
    try:
        result = await engine.reset_mission()
        return result
    except Exception as e:
        logger.error(f"reset_mission failed: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# FastAPI/MCP Integration
# ---------------------------------------------------------------------------

# Create FastAPI application with CORS support
app = FastAPI(
    title="Swarm-ResQ Drone Rescue API",
    description="MCP server for autonomous drone rescue coordination",
    version="1.0.0",
)

# Add CORS middleware for Streamlit and cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP ASGI app at /mcp endpoint
mcp_asgi_app = mcp.streamable_http_app()
app.mount("/mcp", mcp_asgi_app)


# Startup hook: Initialize default mission on server start
@app.on_event("startup")
async def startup_event():
    tools = await mcp.list_tools()
    print("MCP tools registered:", tools)

    """Initialize default mission when server starts."""
    logger.info("=== Swarm-ResQ MCP Server Starting ===")
    result = await initialize_mission(width=20, height=20, drone_count=3)
    if result["success"]:
        logger.info(f"Default mission initialized: {result['message']}")
    else:
        logger.error(f"Failed to initialize default mission: {result['error']}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers."""
    state = await engine.get_swarm_state()
    return {
        "status": "healthy",
        "mission_active": engine.state == SimulationState.ACTIVE,
        "drones": len(state.get("drones", [])),
    }


# Status endpoint
@app.get("/status")
async def get_status():
    """Get mission status."""
    try:
        state = await engine.get_swarm_state()
        return {
            "mission_id": state.get("mission_id", ""),
            "state": state.get("state", ""),
            "drones": state.get("drones", []),
            "move_count": state.get("move_count", 0),
        }
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return {"error": str(e)}


# =========================================================================
# REST Tool Endpoints (Alternative to MCP HTTP streaming)
# =========================================================================

@app.post("/tools/initialize_mission")
async def rest_initialize_mission(
    width: int = 20,
    height: int = 20,
    drone_count: int = 3,
    survivor_count: int = 5,
):
    """Initialize a new rescue mission via REST."""
    return await initialize_mission(width, height, drone_count, survivor_count)


@app.get("/tools/get_swarm_state")
async def rest_get_swarm_state():
    """Get the full swarm state via REST."""
    return await get_swarm_state()


@app.post("/tools/move_drone")
async def rest_move_drone(drone_id: str, dx: int, dy: int):
    """Move a drone via REST."""
    return await move_drone(drone_id, dx, dy)


@app.post("/tools/scan_area")
async def rest_scan_area(drone_id: Optional[str] = None, radius: int = 2):
    """Scan an area via REST."""
    return await scan_area(drone_id, radius)


@app.post("/tools/rescue_survivor")
async def rest_rescue_survivor(drone_id: str, target_x: int, target_y: int):
    """Rescue a survivor via REST."""
    return await rescue_survivor(drone_id, target_x, target_y)


@app.post("/tools/return_to_base")
async def rest_return_to_base(drone_id: str):
    """Return drone to base via REST."""
    return await return_to_base(drone_id)


@app.get("/tools/get_survivor_counts")
async def rest_get_survivor_counts():
    """Get survivor counts via REST."""
    return await get_survivor_counts()


@app.post("/tools/move_until_detect")
async def rest_move_until_detect(drone_id: str, direction_x: int, direction_y: int, scan_radius: int = 2, max_steps: int = 10):
    """Move a drone until detection via REST."""
    return await move_until_detect(drone_id, direction_x, direction_y, scan_radius, max_steps)


@app.post("/tools/move_continuous_until_stopped")
async def rest_move_continuous_until_stopped(drone_id: str, direction_x: int, direction_y: int):
    """OPTIMIZED: Move drone continuously until stopped via REST. Returns full path."""
    return await move_continuous_until_stopped(drone_id, direction_x, direction_y)


@app.get("/tools/get_nearest_survivor")
async def rest_get_nearest_survivor():
    """Get nearest survivor via REST."""
    return await get_nearest_survivor()


@app.post("/tools/estimate_battery_to_target")
async def rest_estimate_battery_to_target(drone_id: str, target_x: int, target_y: int):
    """Estimate battery to target via REST."""
    return await estimate_battery_to_target(drone_id, target_x, target_y)


@app.get("/tools/get_hazard_map")
async def rest_get_hazard_map():
    """Get hazard map via REST."""
    return await get_hazard_map()


@app.get("/tools/get_obstacle_map")
async def rest_get_obstacle_map():
    """Get obstacle map via REST."""
    return await get_obstacle_map()


@app.get("/tools/get_drone_state")
async def rest_get_drone_state(drone_id: str):
    """Get single drone state via REST."""
    return await get_drone_state(drone_id)


@app.post("/tools/reset_mission")
async def rest_reset_mission():
    """Reset mission via REST."""
    return await reset_mission()


# Tool: Get Movement Paths (for UI visualization)
@mcp.tool()
async def get_movement_paths() -> dict:
    """
    Get all stored drone movement paths from recent move_continuous_until_stopped() calls.
    Useful for UI visualization of drone exploration patterns.
    
    Returns:
        Dict with drone_id -> path_data mapping
        Each path_data contains:
        - path: List of {x, y, step} coordinates
        - moves_count: Total steps
        - stopped_reason: Why drone stopped
        - battery_used: Battery consumed
        - battery_remaining: Remaining battery
    """
    try:
        from orchestrator.path_tracker import get_all_paths
        paths = get_all_paths()
        return {"success": True, "paths": paths}
    except Exception as e:
        logger.error(f"get_movement_paths failed: {e}")
        return {"success": False, "error": str(e)}


@app.get("/tools/get_movement_paths")
async def rest_get_movement_paths():
    """Get movement paths via REST."""
    return await get_movement_paths()
