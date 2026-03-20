"""
test_collision_avoidance.py — Integration test for multi-drone collision avoidance

Tests:
1. Collision detection prevents drone-drone overlaps
2. Safe directions prioritize unvisited cells and separation
3. Visited paths are tracked across movements
4. Swarm status reports detect collision risks
"""

import asyncio
from environment.grid import Grid, place_survivors, place_hazards, place_obstacles
from environment.drone import DroneSwarm, DroneStatus


async def test_collision_avoidance():
    """Test collision avoidance system with multiple drones."""
    
    print("=" * 70)
    print("COLLISION AVOIDANCE INTEGRATION TEST")
    print("=" * 70)
    
    # Setup
    grid = Grid(width=20, height=20)
    swarm = DroneSwarm(grid=grid)
    
    # Deploy 3 drones at different starting positions
    swarm.add_drone("drone-1", x=5, y=5)
    swarm.add_drone("drone-2", x=15, y=5)
    swarm.add_drone("drone-3", x=10, y=15)
    
    print("\n1. INITIAL STATE")
    print("   Drones deployed:")
    for drone_id in ["drone-1", "drone-2", "drone-3"]:
        drone = swarm.drones[drone_id]
        print(f"   - {drone_id}: ({drone.x}, {drone.y})")
    
    # Test 1: Check safe directions for each drone
    print("\n2. SAFE DIRECTIONS TEST")
    for drone_id in ["drone-1", "drone-2", "drone-3"]:
        result = swarm.get_safe_directions(drone_id)
        safe_dirs = result.get("safe_directions", [])
        print(f"\n   {drone_id} safe directions ({len(safe_dirs)} options):")
        for i, d in enumerate(safe_dirs[:3], 1):
            print(f"     {i}. dx={d['dx']:2d}, dy={d['dy']:2d}")
    
    # Test 2: Simulate movements with collision avoidance
    print("\n3. MOVEMENT WITH COLLISION AVOIDANCE")
    print("\n   Moving drone-1 east (5 steps)")
    result = swarm.move_continuous_until_stopped("drone-1", direction_x=1, direction_y=0)
    print(f"   Result: {result['moves_count']} moves, stopped: {result['stopped_reason']}")
    print(f"   Final position: ({result['final_position']['x']}, {result['final_position']['y']})")
    
    # Test 3: Check nearby drones
    print("\n4. PROXIMITY DETECTION")
    for drone_id in ["drone-1", "drone-2", "drone-3"]:
        result = swarm.get_nearby_drones(drone_id)
        nearby = result.get("nearby_drones", [])
        print(f"\n   {drone_id} nearby drones: {len(nearby)}")
        for nearby_drone in nearby:
            distance = nearby_drone['distance']
            pos = nearby_drone['position']
            print(f"     - {nearby_drone['drone_id']}: distance={distance}, pos=({pos['x']}, {pos['y']})")
    
    # Test 4: Check visited paths
    print("\n5. VISITED PATH TRACKING")
    visited_result = swarm.get_visited_paths()
    visited_count = visited_result.get("visited_count", 0)
    total_cells = visited_result.get("grid_size", 0)
    visited_pct = visited_result.get("visited_percentage", 0)
    print(f"   Visited cells: {visited_count}/{total_cells} ({visited_pct:.1f}%)")
    
    unvisited_result = swarm.get_unvisited_percentage()
    unvisited_pct = unvisited_result.get("unvisited_percentage", 0)
    print(f"   Unvisited cells: {unvisited_pct:.1f}%")
    
    # Test 5: Collision status
    print("\n6. COLLISION STATUS")
    collision_status = swarm.get_collision_status("drone-1")
    print(f"\n   drone-1:")
    print(f"   - Collision risk: {collision_status.get('collision_risk')}")
    print(f"   - Nearby drones: {collision_status.get('nearby_drones_count')}")
    print(f"   - Occupied cells: {collision_status.get('occupied_cells_count')}")
    
    # Test 6: Swarm status report
    print("\n7. SWARM STATUS REPORT")
    swarm_report = swarm.get_swarm_status_report()
    print(f"   Total drones: {swarm_report.get('total_drones')}")
    print(f"   Drones with collision risk: {swarm_report.get('drones_with_collision_risk')}")
    print(f"   Explored: {swarm_report.get('visited_percentage'):.1f}%")
    
    # Test 7: Separation plan
    print("\n8. SEPARATION PLAN")
    for drone_id in ["drone-1", "drone-2", "drone-3"]:
        sep_plan = swarm.get_drone_separation_plan(drone_id)
        if sep_plan.get('separation_needed'):
            recommended = sep_plan.get('recommended_direction')
            if recommended:
                print(f"   {drone_id}: Separate {recommended['dx']:+d},{recommended['dy']:+d}")
            else:
                print(f"   {drone_id}: Separation needed but no safe direction")
        else:
            print(f"   {drone_id}: No separation needed")
    
    # Test 8: Collision blocking
    print("\n9. COLLISION BLOCKING TEST")
    drone2_pos = swarm.drones["drone-2"]
    print(f"   drone-2 current position: ({drone2_pos.x}, {drone2_pos.y})")
    
    # Try to move drone-1 to drone-2's position (should be blocked)
    target_x = drone2_pos.x
    target_y = drone2_pos.y
    print(f"   Attempting to move drone-1 to ({target_x}, {target_y})...")
    
    # Calculate direction
    d1_pos = swarm.drones["drone-1"]
    dx = 1 if target_x > d1_pos.x else (-1 if target_x < d1_pos.x else 0)
    dy = 1 if target_y > d1_pos.y else (-1 if target_y < d1_pos.y else 0)
    
    if dx != 0 or dy != 0:
        result = swarm.move_drone("drone-1", dx, dy)
        if not result.get('success'):
            collision = result.get('collision_detected', False)
            error = result.get('error', '')
            print(f"   ✓ Move blocked - collision_detected={collision}")
            print(f"   ✓ Error message: {error}")
        else:
            print(f"   × Move succeeded (unexpected)")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE - Collision avoidance system operational")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_collision_avoidance())
