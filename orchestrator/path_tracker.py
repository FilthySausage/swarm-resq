"""
path_tracker.py — Track drone movement paths for UI visualization

Stores the last movement path data from move_continuous_until_stopped() calls
so the UI can visualize them without needing to query a separate endpoint.

This allows the agent's continuous movement API calls to automatically populate
the UI's drone_paths session state when the UI periodically updates.
"""

import json
from typing import Dict, Any, Optional
from pathlib import Path

# In-memory storage for path data
_path_cache: Dict[str, Dict[str, Any]] = {}

# Cache file for persistence across sessions
CACHE_FILE = Path(__file__).parent.parent / ".agent_path_cache.json"


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
    _persist_cache()


def get_all_paths() -> Dict[str, Dict[str, Any]]:
    """Get all stored drone paths."""
    return _path_cache.copy()


def get_drone_path(drone_id: str) -> Optional[Dict[str, Any]]:
    """Get path data for a specific drone."""
    return _path_cache.get(drone_id)


def clear_paths() -> None:
    """Clear all stored path data (e.g., when mission resets)."""
    _path_cache.clear()
    _clear_cache_file()


def _persist_cache() -> None:
    """Save cache to file for persistence across server restarts."""
    try:
        CACHE_FILE.write_text(json.dumps(_path_cache, indent=2))
    except Exception:
        pass  # Silently fail on persistence errors


def _load_cache() -> None:
    """Load cache from file at startup."""
    try:
        if CACHE_FILE.exists():
            _path_cache.update(json.loads(CACHE_FILE.read_text()))
    except Exception:
        pass  # Silently fail on load errors


def _clear_cache_file() -> None:
    """Remove cache file."""
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
    except Exception:
        pass


# Load cache at module import
_load_cache()
