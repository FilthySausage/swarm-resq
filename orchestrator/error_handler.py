"""
error_handler.py — Error Handling & Edge Case Management
Robust error handling for agent failures, timeouts, and edge cases.

Handles:
- LLM API rate limits and timeouts
- Invalid action formats
- Battery emergencies
- Unreachable survivors
- Malformed MCP responses
"""

import asyncio
import logging
from typing import Optional, Any, Dict
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error classification for mission impact assessment."""
    CRITICAL = "critical"      # Mission-threatening
    HIGH = "high"              # Drone loss imminent
    MEDIUM = "medium"          # Objective delayed
    LOW = "low"                # Minor issue


class AgentError(Exception):
    """Base exception for agent-related errors."""
    pass


class TimeoutError(AgentError):
    """LLM API timeout or agent execution timeout."""
    pass


class InvalidActionError(AgentError):
    """Agent returned malformed or invalid action."""
    pass


class RateLimitError(AgentError):
    """Google Gemini API rate limit reached."""
    pass


class MCPConnectionError(AgentError):
    """Cannot communicate with MCP server."""
    pass


class ErrorHandler:
    """
    Centralized error handling with retry logic and graceful degradation.
    """

    def __init__(self, max_retries: int = 3, timeout_seconds: float = 30.0):
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.error_history: list[Dict[str, Any]] = []

    def log_error(
        self,
        error: Exception,
        context: str = "",
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    ) -> None:
        """
        Log an error with context and severity for analysis.
        """
        entry = {
            "timestamp": asyncio.get_event_loop().time(),
            "error_type": type(error).__name__,
            "message": str(error),
            "context": context,
            "severity": severity.value,
        }
        self.error_history.append(entry)
        logger.error(
            f"[{severity.value.upper()}] {context}: {type(error).__name__} — {error}"
        )

    async def retry_with_backoff(
        self,
        coro,
        operation_name: str = "operation",
    ):
        """
        Execute an async operation with exponential backoff retry logic.
        
        Args:
            coro: Async function to execute
            operation_name: Human-readable operation description
            
        Returns:
            Result from successful operation execution
            
        Raises:
            AgentError: After max retries exhausted
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Execute with timeout
                result = await asyncio.wait_for(coro(), timeout=self.timeout_seconds)
                if attempt > 0:
                    logger.info(f"✓ {operation_name} succeeded on retry {attempt}")
                return result
                
            except asyncio.TimeoutError as e:
                last_error = e
                self.log_error(
                    TimeoutError(f"{operation_name} timed out after {self.timeout_seconds}s"),
                    context=f"Attempt {attempt + 1}/{self.max_retries}",
                    severity=ErrorSeverity.HIGH,
                )
                
            except Exception as e:
                last_error = e
                self.log_error(
                    e,
                    context=f"{operation_name} (Attempt {attempt + 1}/{self.max_retries})",
                    severity=ErrorSeverity.MEDIUM,
                )
            
            # Exponential backoff before retry
            if attempt < self.max_retries - 1:
                backoff_delay = 2 ** attempt  # 1s, 2s, 4s...
                logger.info(f"  Retrying {operation_name} in {backoff_delay}s...")
                await asyncio.sleep(backoff_delay)
        
        # All retries exhausted
        raise AgentError(
            f"Failed to complete {operation_name} after {self.max_retries} attempts: {last_error}"
        )

    def validate_agent_output(self, output: str) -> tuple[bool, str]:
        """
        Validate that agent output contains expected reasoning blocks.
        
        Returns:
            (is_valid, error_message)
        """
        if not output:
            return False, "Agent produced no output"
        
        if len(output.strip()) < 20:
            return False, "Agent output too short (possible parse error)"
        
        # Check for malformed tool calls
        if "Error" in output and "tool" not in output:
            return False, "Agent encountered an error without tool call"
        
        return True, ""

    def handle_battery_critical(self, drone_id: str, battery_pct: int) -> Dict[str, Any]:
        """
        Handle a drone with critically low battery.
        """
        self.log_error(
            AgentError(f"Drone {drone_id} critically low (battery: {battery_pct}%)"),
            context="Battery emergency",
            severity=ErrorSeverity.CRITICAL,
        )
        return {
            "action": "immediate_return_to_base",
            "drone_id": drone_id,
            "reason": f"Battery at {battery_pct}%, must return to base immediately",
        }

    def handle_unreachable_survivor(self, survivor_id: str) -> Dict[str, Any]:
        """
        Handle a survivor blocked by hazards/obstacles.
        """
        self.log_error(
            AgentError(f"Survivor {survivor_id} unreachable — blocked by hazards"),
            context="Unreachable survivor",
            severity=ErrorSeverity.HIGH,
        )
        return {
            "action": "skip_survivor",
            "survivor_id": survivor_id,
            "reason": "Blocked by hazards, skipping this rescue",
        }

    def handle_collision_avoided(self, drone_ids: list[str], position: tuple[int, int]) -> Dict[str, Any]:
        """
        Log a collision avoidance event.
        """
        logger.warning(
            f"Collision avoided: {len(drone_ids)} drones attempted same cell {position}"
        )
        return {
            "action": "redistribute_drones",
            "drones": drone_ids,
            "position": position,
        }

    def get_error_summary(self) -> str:
        """
        Generate a summary of all errors encountered during mission.
        
        Returns:
            Formatted error report
        """
        if not self.error_history:
            return "✓ No errors encountered during mission"
        
        critical = sum(1 for e in self.error_history if e["severity"] == "critical")
        high = sum(1 for e in self.error_history if e["severity"] == "high")
        medium = sum(1 for e in self.error_history if e["severity"] == "medium")
        
        summary = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "ERROR SUMMARY",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Critical: {critical}  |  High: {high}  |  Medium: {medium}",
            "",
            "Recent errors (last 5):",
        ]
        
        for entry in self.error_history[-5:]:
            summary.append(
                f"  [{entry['severity'].upper()}] {entry['error_type']}: {entry['message'][:50]}..."
            )
        
        return "\n".join(summary)


# ---------------------------------------------------------------------------
# Validator functions
# ---------------------------------------------------------------------------

def validate_move_command(dx: int, dy: int) -> tuple[bool, str]:
    """
    Validate that a move command has valid delta values.
    
    Returns:
        (is_valid, error_message)
    """
    if not isinstance(dx, int) or not isinstance(dy, int):
        return False, "dx and dy must be integers"
    
    if abs(dx) > 1 or abs(dy) > 1:
        return False, f"Invalid move delta: ({dx}, {dy}). Must be in range [-1, 1]"
    
    if dx == 0 and dy == 0:
        return False, "Move command must change at least one coordinate"
    
    return True, ""


def validate_coordinate(x: int, y: int, width: int, height: int) -> tuple[bool, str]:
    """
    Validate that a coordinate is within grid bounds.
    
    Returns:
        (is_valid, error_message)
    """
    if not (isinstance(x, int) and isinstance(y, int)):
        return False, "Coordinates must be integers"
    
    if not (0 <= x < width and 0 <= y < height):
        return False, f"Coordinate ({x}, {y}) out of bounds [0..{width-1}, 0..{height-1}]"
    
    return True, ""
