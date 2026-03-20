"""
memory.py — Conversation Memory Management
Manages multi-turn context for the ARIA agent.

Implements a LangChain-compatible memory system that persists:
- Explored grid coordinates
- Survivor locations and rescue status
- Drone command history
- Mission timeline
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage


class MissionMemory:
    """
    Manages mission-specific context across turns.
    Stores explored cells, survivors, hazards, and historical decisions.
    """

    def __init__(self, max_history_turns: int = 50):
        self.max_history_turns = max_history_turns
        self.explored_cells: set[tuple[int, int]] = set()
        self.survivors: Dict[str, Dict[str, Any]] = {}  # id -> {x, y, rescued}
        self.hazards: Dict[str, Dict[str, Any]] = {}    # id -> {x, y}
        self.obstacles: set[tuple[int, int]] = set()
        self.command_history: List[Dict[str, Any]] = []
        self.mission_start_time: Optional[datetime] = None

    def record_explored_cell(self, x: int, y: int, cell_type: str) -> None:
        """Record that a cell has been explored."""
        self.explored_cells.add((x, y))
        if cell_type == "S":
            if (x, y) not in self.survivors:
                survivor_id = f"survivor_{len(self.survivors)}"
                self.survivors[survivor_id] = {"x": x, "y": y, "rescued": False}
        elif cell_type == "X":
            if (x, y) not in self.hazards:
                hazard_id = f"hazard_{len(self.hazards)}"
                self.hazards[hazard_id] = {"x": x, "y": y}
        elif cell_type == "#":
            self.obstacles.add((x, y))

    def mark_survivor_rescued(self, survivor_id: str) -> None:
        """Mark a survivor as successfully rescued."""
        if survivor_id in self.survivors:
            self.survivors[survivor_id]["rescued"] = True

    def record_command(self, drone_id: str, command: str, args: Dict, result: Dict) -> None:
        """Record a drone command and its outcome."""
        self.command_history.append({
            "timestamp": datetime.now(),
            "drone_id": drone_id,
            "command": command,
            "args": args,
            "result": result,
        })
        # Keep memory bounded
        if len(self.command_history) > self.max_history_turns:
            self.command_history.pop(0)

    def get_mission_summary(self) -> str:
        """Generate a concise summary of mission progress."""
        explored_pct = len(self.explored_cells) / max(1, len(self.explored_cells))
        survivors_total = len(self.survivors)
        survivors_rescued = sum(1 for s in self.survivors.values() if s["rescued"])
        hazards_found = len(self.hazards)

        return (
            f"| Explored: {explored_pct:.0%} | "
            f"Survivors: {survivors_rescued}/{survivors_total} rescued | "
            f"Hazards: {hazards_found} detected"
        )

    def to_context_string(self) -> str:
        """Convert memory to a string suitable for LLM context."""
        lines = []
        lines.append("━━━ MISSION MEMORY ━━━")
        lines.append(f"Explored cells: {len(self.explored_cells)}")
        lines.append(f"Known survivors: {len(self.survivors)}")
        for sid, survivor in self.survivors.items():
            status = "RESCUED" if survivor["rescued"] else "AWAITING RESCUE"
            lines.append(f"  {sid}: ({survivor['x']}, {survivor['y']}) — {status}")
        lines.append(f"Known hazards: {len(self.hazards)}")
        for hid, hazard in self.hazards.items():
            lines.append(f"  {hid}: ({hazard['x']}, {hazard['y']})")
        lines.append(f"Known obstacles: {len(self.obstacles)}")
        lines.append(f"Recent commands (last 5):")
        for cmd in self.command_history[-5:]:
            lines.append(
                f"  {cmd['drone_id']} → {cmd['command']}: "
                f"{cmd['result'].get('success', False)}"
            )
        return "\n".join(lines)


class ConversationMemoryBuffer:
    """
    LangChain-compatible conversation memory using BufferMemory pattern.
    Stores human (user commands) and AI (agent reasoning) messages.
    """

    def __init__(self, max_message_pairs: int = 20):
        self.max_message_pairs = max_message_pairs
        self.messages: List[BaseMessage] = []
        self.mission_memory = MissionMemory()

    def add_user_message(self, content: str) -> None:
        """Add a user/human message (e.g., mission briefing update)."""
        self.messages.append(HumanMessage(content=content))
        self._trim_buffer()

    def add_ai_message(self, content: str) -> None:
        """Add an AI message (agent output)."""
        self.messages.append(AIMessage(content=content))
        self._trim_buffer()

    def _trim_buffer(self) -> None:
        """Keep buffer size bounded to prevent memory bloat."""
        while len(self.messages) > self.max_message_pairs * 2:
            self.messages.pop(0)

    def get_conversation_history(self) -> str:
        """Return conversation as a formatted string."""
        if not self.messages:
            return "[No prior conversation history]"
        
        history = []
        for msg in self.messages:
            if isinstance(msg, HumanMessage):
                history.append(f"USER: {msg.content}")
            elif isinstance(msg, AIMessage):
                history.append(f"ARIA: {msg.content[:200]}...")  # Truncate long responses
        return "\n".join(history)

    def get_full_context(self) -> str:
        """Return mission memory + conversation history for LLM context."""
        return (
            self.mission_memory.to_context_string()
            + "\n\n"
            + "━━━ CONVERSATION HISTORY ━━━\n"
            + self.get_conversation_history()
        )
