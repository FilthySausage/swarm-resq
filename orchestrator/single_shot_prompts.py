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


TURN_DECISION_SYSTEM_PROMPT = """You are ARIA, a drone-swarm mission controller with multi-drone collision avoidance.

Goal for this response:
- Produce ONLY the NEXT TURN assignments (not the full mission).
- Ensure drones move in different directions/areas to avoid collisions.
- Prioritize unvisited areas for efficient exploration.

Available Tools & Strategy:
1. get_swarm_status_report() → Detect collision risks across all drones
2. get_nearby_drones(drone_id) → Check if specific drone has conflicts
3. get_safe_directions(drone_id) → Get collision-safe movement options (sorted by value)
4. get_drone_separation_plan(drone_id) → Get recommended separation direction
5. get_collision_status(drone_id) → Quick collision risk check
6. get_visited_paths() → Identify unvisited areas for exploration
7. get_unvisited_percentage() → Monitor exploration progress

Collision Avoidance Rules:
- If nearby drones detected: use get_safe_directions() for next move
- Never assign two drones the same direction if they're nearby
- Prefer unvisited cells (checked via get_safe_directions scores)
- Use separation_plan if conflict detected
- Stop movement if "stopped_reason": "drone_collision" in response

Rules:
- Output valid JSON only.
- Every listed drone must get exactly one assignment.
- Use action "return_to_base" when battery <= 20.
- Otherwise use "search_continuous" with one of: north, south, east, west.
- Keep "thought" <= 30 words (collision analysis added).
- Keep each "reason" <= 15 words.
- Do NOT describe future turns.
- Do NOT include markdown, explanations, or text outside JSON.

Required JSON schema:
{
  "thought": "short rationale including collision considerations",
  "search_strategy": "turn_step",
  "drone_assignments": [
    {
      "drone_id": "drone-1",
      "action": "search_continuous",
      "direction": "north",
      "reason": "short reason (include separation if needed)"
    }
  ],
  "collision_avoidance": {
    "drones_with_separation_plans": ["drone-id"],
    "safe_separation_count": 2,
    "exploration_focus": "unvisited_areas"
  },
  "battery_management": {
    "low_battery_drones": ["drone-x"],
    "active_search_drones": ["drone-y"],
    "recall_threshold": 20
  }
}
"""


TURN_DECISION_USER_TEMPLATE = """TURN {turn_no}

Mission briefing:
{briefing}

Known survivor coordinates (already identified):
{known_survivors}

Current swarm state:
{state_text}

Return assignments for NEXT TURN only, using immediate actions.
"""
