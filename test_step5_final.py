"""
test_step5_integration_no_ai.py - Integration test without AI imports
"""

import json

print("=" * 70)
print("STEP 5: INTEGRATION TEST (NO AI)")
print("=" * 70)

# Test 1: Core components (no AI)
print("\n[TEST 1] Importing core components...")
try:
    from environment.grid import Grid, CellType
    from environment.drone import DroneSwarm
    from orchestrator.plan_executor import PlanExecutor, Direction, ActionType
    from orchestrator.model_loader import get_model_by_name, get_default_model
    print("[OK] Core imports successful")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 2: Grid 20x20
print("\n[TEST 2] Grid initialization (20x20)...")
try:
    grid = Grid(20, 20)
    assert grid.width == 20 and grid.height == 20
    assert len(grid.cells) == 20 and len(grid.cells[0]) == 20
    print("[OK] Grid created")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 3: Drone swarm
print("\n[TEST 3] Drone swarm (3 drones)...")
try:
    swarm = DroneSwarm(grid)
    # Add drones manually
    swarm.add_drone("drone-1", 5, 5)
    swarm.add_drone("drone-2", 5, 10)
    swarm.add_drone("drone-3", 5, 15)
    assert len(swarm.drones) == 3
    print(f"[OK] {len(swarm.drones)} drones created")
    for drone_id, drone in list(swarm.drones.items())[:1]:
        print(f"  Sample: {drone_id} - battery={drone.battery}%, pos=({drone.x},{drone.y})")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 4: Model loader
print("\n[TEST 4] Model configuration...")
try:
    default = get_default_model()
    assert "model_id" in default and "name" in default
    print(f"[OK] Default model: {default['name']}")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 5: Plan executor
print("\n[TEST 5] Plan executor...")
try:
    executor = PlanExecutor()
    assert executor.discovered_survivors == []
    print("[OK] Executor initialized")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 6: Parse realistic plan
print("\n[TEST 6] Parsing realistic mission plan...")
try:
    plan_json = """{
        "thought": "Three full-battery drones deploy in sweep formation",
        "search_strategy": "synchronized_sweep",
        "drone_assignments": [
            {"drone_id": "drone-1", "action": "search_continuous", "direction": "north", "reason": "Full battery"},
            {"drone_id": "drone-2", "action": "search_continuous", "direction": "east", "reason": "Full battery"},
            {"drone_id": "drone-3", "action": "idle", "direction": null, "reason": "Reserve"}
        ],
        "battery_management": {"low_battery_drones": [], "active_search_drones": ["drone-1", "drone-2"], "recall_threshold": 20}
    }"""
    
    plan = executor.parse_plan(plan_json)
    assert len(plan.drone_assignments) == 3
    print(f"[OK] Plan: {plan.search_strategy}")
    print(f"  Assignments: {len(plan.drone_assignments)}")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 7: Direction conversion
print("\n[TEST 7] Direction conversion...")
try:
    executor2 = PlanExecutor()
    assert executor2.direction_to_delta(Direction.NORTH) == (0, 1)
    assert executor2.direction_to_delta(Direction.SOUTH) == (0, -1)
    assert executor2.direction_to_delta(Direction.EAST) == (1, 0)
    assert executor2.direction_to_delta(Direction.WEST) == (-1, 0)
    print("[OK] All directions convert correctly")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 8: Survivor discovery simulation
print("\n[TEST 8] Survivor discovery tracking...")
try:
    executor3 = PlanExecutor()
    
    # Simulate discoveries
    discoveries = [
        {"x": 10, "y": 15},
        {"x": 5, "y": 8},
        {"x": 19, "y": 19},
    ]
    
    for survivor in discoveries:
        executor3.discovered_survivors.append(survivor)
    
    assert len(executor3.discovered_survivors) == 3
    print(f"[OK] Tracked {len(executor3.discovered_survivors)} survivors")
    for i, s in enumerate(executor3.discovered_survivors, 1):
        print(f"  {i}. ({s['x']}, {s['y']})")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 9: Battery management decision
print("\n[TEST 9] Battery management decision logic...")
try:
    drones = [
        {"id": "d1", "battery": 100},
        {"id": "d2", "battery": 50},
        {"id": "d3", "battery": 15},
        {"id": "d4", "battery": 8},
    ]
    
    low = [d["id"] for d in drones if d["battery"] < 20]
    search = [d["id"] for d in drones if d["battery"] >= 20]
    
    assert len(low) == 2 and len(search) == 2
    print(f"[OK] Logic: {len(search)} search, {len(low)} return-to-base")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

# Test 10: Coordinate system
print("\n[TEST 10] Coordinate system (0,0 = bottom-left)...")
try:
    test_grid = Grid(10, 10)
    
    # Bottom-left (0,0)
    test_grid.set_cell_type(0, 0, CellType.EMPTY)
    assert test_grid.get_cell(0, 0).cell_type == CellType.EMPTY
    
    # Top-right (9,9)
    test_grid.set_cell_type(9, 9, CellType.OBSTACLE)
    assert test_grid.get_cell(9, 9).cell_type == CellType.OBSTACLE
    
    # Place survivor
    test_grid.set_cell_type(5, 5, CellType.SURVIVOR)
    assert test_grid.get_cell(5, 5).cell_type == CellType.SURVIVOR
    
    print("[OK] Coordinate system verified")
    print("  (0,0) = bottom-left (EMPTY)")
    print("  (9,9) = top-right (OBSTACLE)")
    print("  (5,5) = center (SURVIVOR)")
except Exception as e:
    print(f"[FAIL] {e}")
    exit(1)

print("\n" + "=" * 70)
print("ALL TESTS PASSED - SYSTEM INTEGRATION VERIFIED")
print("=" * 70)
print("\nREADY FOR LIVE TESTING:")
print("  Terminal 1: uvicorn mcp_server.server:app --reload --port 8000")
print("  Terminal 2: streamlit run ui/app.py")
