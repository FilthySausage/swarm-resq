"""
single_shot_prompts.py — Prompt templates for ARIA mission control.

Runtime now uses compact turn-by-turn prompting only.
"""

# Kept for backward compatibility with older tests or imports.
SINGLE_SHOT_SYSTEM_PROMPT = """DEPRECATED: Use TURN_DECISION_SYSTEM_PROMPT for runtime turn-by-turn control."""

REASSIGNMENT_PROMPT = """BATTERY CRITICAL - REASSIGNMENT REQUIRED

One or more drones have reached the 20% battery threshold during the mission.

Current State:
{current_state}

Discovered Survivors So Far:
{found_survivors}

Unexplored Sectors:
{remaining_sectors}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REASSIGNMENT TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate NEW assignments for all drones based on updated battery levels.

Rules:
1. Drones with battery < 20%: MUST return to base
2. Drones with battery >= 20%: Continue search OR take over sectors from low-battery drones
3. Drones at base with 100% battery: Resume search

Return JSON in the same format as initial planning:

{
  "thought": "Reassignment reasoning: which drones returning, which continuing, sector coverage",
  "search_strategy": "horizontal",
  "drone_assignments": [
    {
      "drone_id": "drone-1",
      "action": "search_continuous",
      "direction": "east",
      "reason": "Battery at 65%, taking over drone-2's sector"
    },
    {
      "drone_id": "drone-2",
      "action": "return_to_base",
      "direction": null,
      "reason": "Battery critical at 18%, returning to base"
    }
  ],
  "battery_management": {
    "low_battery_drones": ["drone-2"],
    "active_search_drones": ["drone-1", "drone-3"],
    "recall_threshold": 20
  }
}

Return ONLY the JSON object.
"""

MISSION_START_TEMPLATE = """Mission initialized. Begin systematic search and survivor detection.

Grid Dimensions: {width}x{height} ({total_cells} cells)
Base Location: (0, 0) - bottom-left corner

Drones Deployed:
{drone_list}

Mission Briefing: {briefing}

Analyze the state and return your JSON search plan.
"""


TURN_DECISION_SYSTEM_PROMPT = """You are ARIA. Return ONLY JSON for the NEXT TURN.

Hard rules:
1) PRIORITY: Explore unscanned cells. Always prefer adjacent unscanned cells when available.
2) If all adjacent cells are scanned, move toward the nearest unscanned frontier.
3) Follow recommended directions from exploration state when provided.
4) Do NOT assign a drone to a scanned coordinate unless no unscanned path exists.
5) If battery <= 20, action must be return_to_base.
6) Each drone can move at most 2 coordinates this turn.
7) If drone is near a corner or boundary, move toward interior unscanned regions.
8) Avoid obstacles, hazards, blocked coordinates, and repeated back-and-forth moves.
9) Keep drones separated (avoid anti-cluster: don't send multiple drones to same frontier cell).
10) Stop exploring once all survivors are detected.
11) If one drone is repeatedly stuck, prioritize other drones first for faster survivor search.

Directions allowed:
north, south, east, west, north_east, north_west, south_east, south_west

Output schema:
{
  "thought": "<=25 words",
  "search_strategy": "turn_step",
  "drone_assignments": [
    {
      "drone_id": "drone-1",
      "action": "search_continuous",
      "direction": "north_east",
      "reason": "<=12 words"
    }
  ],
  "battery_management": {
    "low_battery_drones": [],
    "active_search_drones": [],
    "recall_threshold": 20
  }
}
"""


TURN_DECISION_USER_TEMPLATE = """TURN {turn_no}

Briefing: {briefing}
Base corner: (0, 0)
Detected survivors: {known_survivors}

Coverage:
- scanned: {explored_count}/{total_cells} ({scanned_percentage}%)
- unscanned sample: {unexplored_sample}

Avoid these coordinates:
- obstacles: {obstacle_sample}
- hazards: {hazard_sample}
- blocked attempts: {blocked_sample}

🎯 EXPLORATION GUIDANCE (PRIORITIZE):
{exploration_guidance}

Swarm:
{state_text}

Return NEXT TURN assignments only.
"""
