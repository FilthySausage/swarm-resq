"""
mission.py — Mission Status Tracking & Completion Logic
Manages mission state, completion conditions, and status reporting.

Handles:
- Mission completion detection
- Performance metrics (time, survivors rescued, etc.)
- Status snapshots
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MissionStatus(Enum):
    """Mission lifecycle states."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED_SUCCESS = "completed_success"
    COMPLETED_FAILURE = "completed_failure"
    ABORTED = "aborted"


@dataclass
class MissionMetrics:
    """Performance metrics captured at mission end."""
    start_time: datetime
    end_time: Optional[datetime] = None
    total_survivors: int = 0
    survivors_rescued: int = 0
    drones_deployed: int = 0
    drones_operational: int = 0
    grid_explored_pct: float = 0.0
    total_moves: int = 0

    @property
    def elapsed_seconds(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration_seconds": self.elapsed_seconds,
            "survivors_rescued": self.survivors_rescued,
            "total_survivors": self.total_survivors,
            "rescue_rate": (
                f"{(self.survivors_rescued / max(1, self.total_survivors)) * 100:.1f}%"
            ),
            "drones_operational": self.drones_operational,
            "drones_deployed": self.drones_deployed,
            "grid_explored": f"{self.grid_explored_pct:.1f}%",
            "total_moves": self.total_moves,
        }


class MissionMonitor:
    """
    Tracks mission state and determines when objectives are complete.
    Intended to be called at the end of each agent turn.
    """

    def __init__(self):
        self.status = MissionStatus.NOT_STARTED
        self.metrics = MissionMetrics(start_time=datetime.now())
        self.completion_reason: Optional[str] = None

    def start_mission(self, grid_width: int, grid_height: int, survivor_count: int) -> None:
        """Initialize mission with known parameters."""
        self.status = MissionStatus.IN_PROGRESS
        self.metrics.start_time = datetime.now()
        self.metrics.total_survivors = survivor_count
        self.grid_size = grid_width * grid_height

    def check_completion(
        self,
        survivors_rescued: int,
        survivors_total: int,
        grid_explored_cells: int,
        grid_total_cells: int,
        drones_operational: int,
        drones_deployed: int,
    ) -> bool:
        """
        Check if mission should terminate.
        
        Mission is complete when ANY of these conditions are met:
        1. All survivors rescued
        2. Grid fully explored with no survivors remaining
        3. All drones inactive (battery depleted or crashed)
        
        Args:
            survivors_rescued: Number of survivors successfully returned to base
            survivors_total: Total survivors initially placed
            grid_explored_cells: Number of explored cells
            grid_total_cells: Total cells in grid
            drones_operational: Number of drones still operational
            drones_deployed: Total drones in swarm
            
        Returns:
            True if mission is complete, False otherwise
        """
        explored_pct = (grid_explored_cells / max(1, grid_total_cells)) * 100
        self.metrics.grid_explored_pct = explored_pct
        self.metrics.survivors_rescued = survivors_rescued
        self.metrics.drones_operational = drones_operational

        # Condition 1: All survivors rescued
        if survivors_rescued >= survivors_total and survivors_total > 0:
            self.status = MissionStatus.COMPLETED_SUCCESS
            self.completion_reason = (
                f"All {survivors_rescued} survivors rescued successfully!"
            )
            self.metrics.end_time = datetime.now()
            return True

        # Condition 2: Grid fully explored with no survivors left (no rescue possible)
        if explored_pct >= 95.0 and survivors_rescued == 0 and survivors_total > 0:
            self.status = MissionStatus.COMPLETED_FAILURE
            self.completion_reason = (
                f"Grid {explored_pct:.1f}% explored. No survivors found or rescued."
            )
            self.metrics.end_time = datetime.now()
            return True

        # Condition 3: All drones inactive
        if drones_operational == 0 and drones_deployed > 0:
            self.status = MissionStatus.COMPLETED_FAILURE
            self.completion_reason = (
                f"All {drones_deployed} drones inactive. "
                f"{survivors_rescued}/{survivors_total} survivors rescued."
            )
            self.metrics.end_time = datetime.now()
            return True

        return False

    def abort_mission(self, reason: str) -> None:
        """Manually abort the mission."""
        self.status = MissionStatus.ABORTED
        self.completion_reason = reason
        self.metrics.end_time = datetime.now()

    def get_status_report(self) -> str:
        """Generate a human-readable status report."""
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "MISSION STATUS REPORT",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Status: {self.status.value.upper()}",
        ]

        if self.completion_reason:
            lines.append(f"Reason: {self.completion_reason}")

        lines.append("")
        lines.append("METRICS:")
        for key, value in self.metrics.to_dict().items():
            lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    def is_complete(self) -> bool:
        """Check if mission is in a terminal state."""
        return self.status in (
            MissionStatus.COMPLETED_SUCCESS,
            MissionStatus.COMPLETED_FAILURE,
            MissionStatus.ABORTED,
        )
