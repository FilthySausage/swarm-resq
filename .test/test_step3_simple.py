"""
test_step3_simple.py - Simpler test without full imports
"""

import sys
import json

print("=" * 70)
print("SIMPLE STEP 3 COMPONENT TEST")
print("=" * 70)

# Test 1: Import plan executor
print("\n[TEST 1] Importing PlanExecutor...")
try:
    from orchestrator.plan_executor import PlanExecutor, MissionPlan, Direction, ActionType
    print("SUCCESS: PlanExecutor imported")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 2: Test direction conversion
print("\n[TEST 2] Direction conversion...")
try:
    executor = PlanExecutor()
    result_north = executor.direction_to_delta(Direction.NORTH)
    result_south = executor.direction_to_delta(Direction.SOUTH)
    result_east = executor.direction_to_delta(Direction.EAST)
    result_west = executor.direction_to_delta(Direction.WEST)
    
    assert result_north == (0, 1), f"North failed: {result_north}"
    assert result_south == (0, -1), f"South failed: {result_south}"
    assert result_east == (1, 0), f"East failed: {result_east}"
    assert result_west == (-1, 0), f"West failed: {result_west}"
    
    print("SUCCESS: All directions correct")
    print(f"  NORTH: {result_north}")
    print(f"  SOUTH: {result_south}")
    print(f"  EAST: {result_east}")
    print(f"  WEST: {result_west}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 3: Test JSON parsing
print("\n[TEST 3] JSON plan parsing...")
try:
    json_response = """{
        "thought": "Two drones search, one returns",
        "search_strategy": "horizontal_sweep",
        "drone_assignments": [
            {
                "drone_id": "drone-1",
                "action": "search_continuous",
                "direction": "east",
                "reason": "Full battery"
            },
            {
                "drone_id": "drone-2",
                "action": "return_to_base",
                "direction": null,
                "reason": "Low battery"
            }
        ],
        "battery_management": {
            "low_battery_drones": ["drone-2"],
            "active_search_drones": ["drone-1"],
            "recall_threshold": 20
        }
    }"""
    
    plan = executor.parse_plan(json_response)
    assert plan is not None, "Plan parsing returned None"
    assert len(plan.drone_assignments) == 2, f"Expected 2 assignments, got {len(plan.drone_assignments)}"
    assert plan.search_strategy == "horizontal_sweep", "Strategy mismatch"
    
    print("SUCCESS: JSON plan parsed correctly")
    print(f"  Strategy: {plan.search_strategy}")
    print(f"  Assignments: {len(plan.drone_assignments)}")
    print(f"  Low battery threshold: {plan.battery_management.recall_threshold}")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Test survivor tracking
print("\n[TEST 4] Survivor tracking...")
try:
    executor2 = PlanExecutor()
    
    survivors = [
        {"x": 5, "y": 10},
        {"x": 15, "y": 20},
        {"x": 3, "y": 7},
    ]
    
    for survivor in survivors:
        executor2.discovered_survivors.append(survivor)
    
    assert len(executor2.discovered_survivors) == 3, "Tracking failed"
    assert executor2.discovered_survivors[0] == {"x": 5, "y": 10}, "First survivor mismatch"
    
    print("SUCCESS: Survivor tracking works")
    print(f"  Total survivors: {len(executor2.discovered_survivors)}")
    for i, s in enumerate(executor2.discovered_survivors, 1):
        print(f"    {i}. ({s['x']}, {s['y']})")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Test 5: Invalid plan should be rejected
print("\n[TEST 5] Invalid plan rejection...")
try:
    from orchestrator.plan_executor import DroneAssignment
    
    # This should fail - SEARCH_CONTINUOUS without direction
    try:
        bad_assignment = DroneAssignment(
            drone_id="drone-1",
            action=ActionType.SEARCH_CONTINUOUS,
            direction=None,
            reason="Should fail"
        )
        print("FAILED: Should have rejected invalid plan")
        sys.exit(1)
    except Exception as validation_error:
        print(f"SUCCESS: Correctly rejected invalid plan")
        print(f"  Error: {str(validation_error)[:80]}...")
        
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("ALL TESTS PASSED")
print("=" * 70)
