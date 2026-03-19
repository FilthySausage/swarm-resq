"""
path_tracker.py — Track drone movement paths for UI visualization.

Paths are intentionally in-memory only so each server run starts clean.
"""

from typing import Dict, Any, Optional

# In-memory storage for path data
_path_cache: Dict[str, Dict[str, Any]] = {}


def store_movement_path(drone_id: str, path_data: Dict[str, Any]) -> None:
    """
    Store a drone's movement path data.
    
    Args:
        drone_id: Drone identifier
        path_data: Movement response with 'path', 'moves_count', 'stopped_reason', etc.
    """
    _path_cache[drone_id] = {
        "path": path_data.get("path", []),
        "moves_count": path_data.get("moves_count", 0),
        "stopped_reason": path_data.get("stopped_reason", "unknown"),
        "battery_used": path_data.get("battery_used", 0),
        "battery_remaining": path_data.get("battery_remaining", 0),
    }


def get_all_paths() -> Dict[str, Dict[str, Any]]:
    """Get all stored drone paths."""
    return _path_cache.copy()


def get_drone_path(drone_id: str) -> Optional[Dict[str, Any]]:
    """Get path data for a specific drone."""
    return _path_cache.get(drone_id)


def clear_paths() -> None:
    """Clear all stored path data (e.g., when mission resets)."""
    _path_cache.clear()
