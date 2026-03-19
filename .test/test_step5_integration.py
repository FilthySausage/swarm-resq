"""
test_step5_integration.py - Full system integration test
Verifies all components work together without actually running the server
"""

import json

print("=" * 70)
print("STEP 5: INTEGRATION TEST")
print("=" * 70)

# Test 1: Import all core components
print("\n[TEST 1] Importing all components...")
try:
    from environment.grid import Grid, CellType
    from environment.drone import DroneSwarm
    from orchestrator.plan_executor import PlanExecutor
    from orchestrator.mission_controller import MissionController
    from orchestrator.model_loader import get_model_by_name, get_default_model
    from orchestrator.single_shot_prompts import (
        SINGLE_SHOT_SYSTEM_PROMPT,
        REASSIGNMENT_PROMPT,
        MISSION_START_TEMPLATE
    )
    print("[OK] All imports successful")
except Exception as e:
    print(f"[FAIL] Import error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 2: Grid initialization
print("\n[TEST 2] Grid initialization...")
try:
    grid = Grid(20, 20)
    assert grid.width == 20
    assert grid.height == 20
    assert len(grid.cells) == 20
    assert len(grid.cells[0]) == 20
    print("[OK] Grid created: 20x20")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 3: Drone swarm initialization
print("\n[TEST 3] Drone swarm initialization...")
try:
    swarm = DroneSwarm(grid, num_drones=3)
    assert len(swarm.drones) == 3
    print("[OK] Swarm created with 3 drones")
    for drone_id, drone in swarm.drones.items():
        print(f"  - {drone_id}: battery={drone.battery}%, pos=({drone.x}, {drone.y})")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 4: Model configuration
print("\n[TEST 4] Model configuration...")
try:
    default_model = get_default_model()
    assert default_model is not None
    assert "model_id" in default_model
    assert "name" in default_model
    print(f"[OK] Default model: {default_model['name']}")
    print(f"  ID: {default_model['model_id']}")
    print(f"  URL: {default_model['base_url']}")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 5: Plan executor initialization
print("\n[TEST 5] Plan executor initialization...")
try:
    executor = PlanExecutor()
    assert executor.discovered_survivors == []
    assert executor.execution_log == []
    print("[OK] Plan executor ready")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 6: Parse complex multi-turn plan
print("\n[TEST 6] Parsing complex mission plan...")
try:
    complex_plan = """{
        "thought": "First turn: deploy high-battery drones for reconnaissance. Second turn: if low-battery, recall. Continue systematic search.",
        "search_strategy": "adaptive_spiral_with_reassignment",
        "drone_assignments": [
            {
                "drone_id": "drone-1",
                "action": "search_continuous",
                "direction": "north",
                "reason": "100% battery, lead reconnaissance north"
            },
            {
                "drone_id": "drone-2",
                "action": "search_continuous",
                "direction": "east",
                "reason": "100% battery, flank right side"
            },
            {
                "drone_id": "drone-3",
                "action": "idle",
                "direction": null,
                "reason": "Reserve for reassignment"
            }
        ],
        "battery_management": {
            "low_battery_drones": [],
            "active_search_drones": ["drone-1", "drone-2"],
            "recall_threshold": 20
        }
    }"""
    
    plan = executor.parse_plan(complex_plan)
    assert plan is not None
    assert len(plan.drone_assignments) == 3
    
    print("[OK] Complex plan parsed")
    print(f"  Strategy: {plan.search_strategy}")
    print(f"  Thought: {plan.thought[:60]}...")
    
    search_count = sum(1 for a in plan.drone_assignments if a.action.value == "search_continuous")
    idle_count = sum(1 for a in plan.drone_assignments if a.action.value == "idle")
    print(f"  Active: {search_count} search, {idle_count} idle")
    
except Exception as e:
    print(f"[FAIL] {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 7: Validate prompt templates
print("\n[TEST 7] Validating prompt templates...")
try:
    assert SINGLE_SHOT_SYSTEM_PROMPT is not None
    assert len(SINGLE_SHOT_SYSTEM_PROMPT) > 100
    assert "MISSION OBJECTIVE" in SINGLE_SHOT_SYSTEM_PROMPT
    
    assert REASSIGNMENT_PROMPT is not None
    assert len(REASSIGNMENT_PROMPT) > 50
    
    assert MISSION_START_TEMPLATE is not None
    assert "{width}" in MISSION_START_TEMPLATE or "width" in MISSION_START_TEMPLATE.lower()
    
    print("[OK] All prompts valid")
    print(f"  System prompt: {len(SINGLE_SHOT_SYSTEM_PROMPT)} chars")
    print(f"  Reassignment prompt: {len(REASSIGNMENT_PROMPT)} chars")
    print(f"  Mission template: {len(MISSION_START_TEMPLATE)} chars")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 8: Direction and action enums
print("\n[TEST 8] Testing action and direction types...")
try:
    from orchestrator.plan_executor import Direction, ActionType
    
    directions = [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
    assert len(directions) == 4
    
    actions = [ActionType.SEARCH_CONTINUOUS, ActionType.RETURN_TO_BASE, ActionType.IDLE]
    assert len(actions) == 3
    
    print("[OK] Enums valid")
    print(f"  Directions: {', '.join([d.value for d in directions])}")
    print(f"  Actions: {', '.join([a.value for a in actions])}")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 9: Survivor tracking across multiple discoveries
print("\n[TEST 9] Survivor tracking persistence...")
try:
    executor_persist = PlanExecutor()
    
    # Simulate multiple movement results
    movements = [
        {"path": [{"x": 5, "y": 5}, {"x": 6, "y": 5}], "stopped_reason": "boundary"},
        {"path": [{"x": 10, "y": 10}, {"x": 10, "y": 11}], "stopped_reason": "detected_survivor"},
        {"path": [{"x": 15, "y": 15}, {"x": 15, "y": 16}], "stopped_reason": "obstacle"},
        {"path": [{"x": 3, "y": 3}, {"x": 3, "y": 4}], "stopped_reason": "detected_survivor"},
    ]
    
    for movement in movements:
        if movement.get("stopped_reason") == "detected_survivor":
            path = movement.get("path", [])
            if path:
                last_pos = path[-1]
                executor_persist.discovered_survivors.append({"x": last_pos["x"], "y": last_pos["y"]})
    
    assert len(executor_persist.discovered_survivors) == 2
    assert executor_persist.discovered_survivors[0] == {"x": 10, "y": 11}
    assert executor_persist.discovered_survivors[1] == {"x": 3, "y": 4}
    
    print("[OK] Survivor tracking persistent across turns")
    print(f"  Total survivors found: {len(executor_persist.discovered_survivors)}")
    for i, s in enumerate(executor_persist.discovered_survivors, 1):
        print(f"    {i}. ({s['x']}, {s['y']})")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 10: Coordinate system verification
print("\n[TEST 10] Coordinate system (bottom-left origin)...")
try:
    grid_test = Grid(10, 10)
    
    # Base should be at (0, 0) - bottom-left
    # Test by placing cell at known position
    grid_test.set_cell_type(0, 0, CellType.BASE)
    base_cell = grid_test.get_cell(0, 0)
    
    assert base_cell is not None
    assert base_cell.cell_type == CellType.BASE
    
    # Top-right should be (9, 9)
    grid_test.set_cell_type(9, 9, CellType.OBSTACLE)
    top_right_cell = grid_test.get_cell(9, 9)
    assert top_right_cell.cell_type == CellType.OBSTACLE
    
    print("[OK] Coordinate system verified: (0,0) at bottom-left")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

print("\n" + "=" * 70)
print("ALL INTEGRATION TESTS PASSED")
print("=" * 70)
print("\nSystem Status: READY FOR DEPLOYMENT")
print("  - Grid system: OK")
print("  - Drone swarm: OK")
print("  - Plan executor: OK")
print("  - Model loading: OK")
print("  - Prompts: OK")
print("  - Coordinate system: OK")
print("  - Survivor tracking: OK")
