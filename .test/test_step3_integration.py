"""
test_step3_integration.py - Test the integrated Step 3 system
Tests: Battery monitoring, survivor tracking, mission controller
"""

import asyncio
import json
from environment.grid import Grid, CellType
from environment.drone import DroneSwarm
from orchestrator.plan_executor import PlanExecutor, MissionPlan, DroneAssignment, ActionType, Direction, BatteryManagement
from orchestrator.mission_controller import MissionController


async def test_plan_executor_parsing():
    """Test JSON plan parsing and validation"""
    print("\n" + "=" * 70)
    print("TEST 1: Plan Executor - JSON Parsing")
    print("=" * 70)
    
    # Sample AI response
    json_response = """{
        "thought": "Two drones at full battery, one low. Drone A and B search east/west, Drone C returns to base.",
        "search_strategy": "horizontal_sweep_low_to_high",
        "drone_assignments": [
            {
                "drone_id": "drone-1",
                "action": "search_continuous",
                "direction": "east",
                "reason": "Full battery, search right side"
            },
            {
                "drone_id": "drone-2",
                "action": "search_continuous",
                "direction": "north",
                "reason": "Full battery, search upper side"
            },
            {
                "drone_id": "drone-3",
                "action": "return_to_base",
                "direction": null,
                "reason": "Low battery threshold reached"
            }
        ],
        "battery_management": {
            "low_battery_drones": ["drone-3"],
            "active_search_drones": ["drone-1", "drone-2"],
            "recall_threshold": 20
        }
    }"""
    
    executor = PlanExecutor()
    plan = executor.parse_plan(json_response)
    
    if plan is None:
        print("FAILED: Could not parse plan")
        return False
    
    print("PASSED: Plan parsed successfully")
    print(f"  Strategy: {plan.search_strategy}")
    print(f"  Assignments: {len(plan.drone_assignments)}")
    print(f"  Low battery drones: {plan.battery_management.low_battery_drones}")
    return True


async def test_battery_level_check():
    """Test battery level checking logic"""
    print("\n" + "=" * 70)
    print("TEST 2: Battery Level Monitoring")
    print("=" * 70)
    
    # Create sample state with mixed battery levels
    sample_state = {
        "drones": [
            {"drone_id": "drone-1", "battery": 100, "x": 5, "y": 5},
            {"drone_id": "drone-2", "battery": 50, "x": 10, "y": 10},
            {"drone_id": "drone-3", "battery": 15, "x": 15, "y": 15},  # Below 20%
            {"drone_id": "drone-4", "battery": 10, "x": 0, "y": 0},    # Below 20%
        ]
    }
    
    # Simulate battery check
    low_battery = []
    for drone in sample_state["drones"]:
        battery = drone.get("battery", 0)
        if battery < 20 and battery > 0:
            low_battery.append(drone["drone_id"])
    
    if len(low_battery) == 2 and "drone-3" in low_battery and "drone-4" in low_battery:
        print("PASSED: Battery check identified 2 low-battery drones correctly")
        return True
    else:
        print(f"FAILED: Expected 2 low-battery drones, found {len(low_battery)}")
        return False


async def test_survivor_tracking():
    """Test survivor discovery tracking"""
    print("\n" + "=" * 70)
    print("TEST 3: Survivor Tracking")
    print("=" * 70)
    
    executor = PlanExecutor()
    
    # Simulate discoveries
    survivors = [
        {"x": 5, "y": 10},
        {"x": 15, "y": 20},
        {"x": 3, "y": 7},
    ]
    
    for survivor in survivors:
        executor.discovered_survivors.append(survivor)
    
    found = executor.discovered_survivors
    
    if len(found) == 3 and found[0] == {"x": 5, "y": 10}:
        print("PASSED: Survivor tracking working correctly")
        print(f"  Discovered survivors: {found}")
        return True
    else:
        print("FAILED: Survivor tracking failed")
        return False


async def test_mission_controller_init():
    """Test mission controller initialization"""
    print("\n" + "=" * 70)
    print("TEST 4: Mission Controller Initialization")
    print("=" * 70)
    
    try:
        # Test with default model
        controller = MissionController()
        print("PASSED: Mission controller initialized with default model")
        print(f"  Model: {controller.model_config['name']}")
        print(f"  Model ID: {controller.model_config['model_id']}")
        return True
    except Exception as e:
        print(f"FAILED: {str(e)}")
        return False


async def test_direction_conversion():
    """Test direction to delta conversion"""
    print("\n" + "=" * 70)
    print("TEST 5: Direction Conversion")
    print("=" * 70)
    
    executor = PlanExecutor()
    
    test_cases = [
        (Direction.NORTH, (0, 1)),
        (Direction.SOUTH, (0, -1)),
        (Direction.EAST, (1, 0)),
        (Direction.WEST, (-1, 0)),
    ]
    
    all_passed = True
    for direction, expected in test_cases:
        result = executor.direction_to_delta(direction)
        if result == expected:
            print(f"  {direction.value.upper()}: {result} ✓")
        else:
            print(f"  {direction.value.upper()}: got {result}, expected {expected} ✗")
            all_passed = False
    
    if all_passed:
        print("PASSED: All directions converted correctly")
        return True
    else:
        print("FAILED: Some direction conversions were incorrect")
        return False


async def test_mission_plan_validation():
    """Test Pydantic model validation"""
    print("\n" + "=" * 70)
    print("TEST 6: Mission Plan Validation")
    print("=" * 70)
    
    try:
        # Valid plan
        plan = MissionPlan(
            thought="Test strategy",
            search_strategy="horizontal",
            drone_assignments=[
                DroneAssignment(
                    drone_id="drone-1",
                    action=ActionType.SEARCH_CONTINUOUS,
                    direction=Direction.EAST,
                    reason="Test"
                )
            ],
            battery_management=BatteryManagement()
        )
        print("PASSED: Valid plan created successfully")
        return True
    except Exception as e:
        print(f"FAILED: {str(e)}")
        return False


async def test_invalid_direction_validation():
    """Test that invalid plans are rejected"""
    print("\n" + "=" * 70)
    print("TEST 7: Invalid Plan Rejection")
    print("=" * 70)
    
    try:
        # Invalid: SEARCH_CONTINUOUS without direction
        plan = DroneAssignment(
            drone_id="drone-1",
            action=ActionType.SEARCH_CONTINUOUS,
            direction=None,  # Should fail
            reason="Test"
        )
        print("FAILED: Should have rejected SEARCH_CONTINUOUS without direction")
        return False
    except Exception as e:
        print(f"PASSED: Correctly rejected invalid plan: {str(e)[:60]}...")
        return True


async def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("STEP 3 INTEGRATION TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("Plan Executor Parsing", test_plan_executor_parsing),
        ("Battery Level Check", test_battery_level_check),
        ("Survivor Tracking", test_survivor_tracking),
        ("Mission Controller Init", test_mission_controller_init),
        ("Direction Conversion", test_direction_conversion),
        ("Mission Plan Validation", test_mission_plan_validation),
        ("Invalid Plan Rejection", test_invalid_direction_validation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\nTEST ERROR in {name}: {str(e)}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
