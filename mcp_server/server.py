"""
server.py — FastMCP Server
Member 2 (MCP/API) workspace.

Exposes drone actions as MCP tools that the LangChain agent
(Member 1) can discover and call via the MCP protocol.

Run with:
    uvicorn mcp_server.server:app --reload --port 8000
"""

from mcp.server.fastmcp import FastMCP
from environment.grid import Grid, CellType
from environment.drone import DroneSwarm

# ---------------------------------------------------------------------------
# Shared simulation state
# In production, replace with a proper state store (Redis, shared memory, etc.)
# ---------------------------------------------------------------------------
_grid = Grid(width=20, height=20)
_swarm = DroneSwarm(grid=_grid)

# Seed a few drones for testing
_swarm.add_drone("drone-1", x=0, y=0)
_swarm.add_drone("drone-2", x=19, y=0)
_swarm.add_drone("drone-3", x=0, y=19)

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------
mcp = FastMCP("swarm-resq")


@mcp.tool()
def move_drone(drone_id: str, dx: int, dy: int) -> dict:
    """
    Move a drone by a delta (dx, dy) on the grid.

    Args:
        drone_id: The unique identifier of the drone (e.g. 'drone-1').
        dx: Horizontal movement delta. Must be -1, 0, or 1.
        dy: Vertical movement delta. Must be -1, 0, or 1.

    Returns:
        A dict with 'success' (bool) and either the updated drone state
        or an 'error' message.
    """
    return _swarm.move_drone(drone_id, dx, dy)


@mcp.tool()
def scan_area(drone_id: str, radius: int = 2) -> dict:
    """
    Scan the area around a drone for survivors, hazards, and obstacles.

    Args:
        drone_id: The unique identifier of the drone to use for scanning.
        radius: Scan radius in grid cells (default: 2).

    Returns:
        A dict with 'success' (bool) and a list of 'detections', each
        containing the cell's (x, y) position and type.
    """
    return _swarm.scan_area(drone_id, radius)


@mcp.tool()
def get_swarm_state() -> dict:
    """
    Get the full current state of the swarm and the grid.

    Returns:
        A dict containing all drone states and the serialized grid.
    """
    return _swarm.get_state()


@mcp.tool()
def get_drone_state(drone_id: str) -> dict:
    """
    Get the current state of a single drone.

    Args:
        drone_id: The unique identifier of the drone.

    Returns:
        A dict with the drone's position, status, battery, and cargo,
        or an error if the drone is not found.
    """
    drone = _swarm.drones.get(drone_id)
    if not drone:
        return {"success": False, "error": f"Drone '{drone_id}' not found."}
    return {"success": True, "drone": drone.to_dict()}


# ---------------------------------------------------------------------------
# TODO (Member 2): Add more tools as Member 3 builds them:
#   - rescue_survivor(drone_id, target_x, target_y)
#   - return_to_base(drone_id)
#   - place_survivors(count)   <- for resetting the simulation
# ---------------------------------------------------------------------------

# Expose as ASGI app for uvicorn
app = mcp.streamable_http_app()
