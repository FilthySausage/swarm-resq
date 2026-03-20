"""
Test script to verify bottom-left origin coordinate system.
Run with: python test_coordinate_system.py
"""

from environment.grid import Grid, CellType
from environment.drone import DroneSwarm

def test_coordinate_system():
    print("=" * 60)
    print("TESTING BOTTOM-LEFT ORIGIN COORDINATE SYSTEM")
    print("=" * 60)
    
    # Create a small 5x5 grid for testing
    grid = Grid(width=5, height=5)
    
    # Test 1: Place markers at corners
    print("\n[Test 1] Placing markers at corners:")
    grid.set_cell_type(0, 0, CellType.SURVIVOR)  # Bottom-left
    grid.set_cell_type(4, 0, CellType.HAZARD)    # Bottom-right
    grid.set_cell_type(0, 4, CellType.OBSTACLE)  # Top-left
    grid.set_cell_type(4, 4, CellType.DRONE)     # Top-right
    
    print(f"  (0,0) Bottom-left: {grid.get_cell(0, 0).cell_type.value} (should be 'S')")
    print(f"  (4,0) Bottom-right: {grid.get_cell(4, 0).cell_type.value} (should be 'X')")
    print(f"  (0,4) Top-left: {grid.get_cell(0, 4).cell_type.value} (should be '#')")
    print(f"  (4,4) Top-right: {grid.get_cell(4, 4).cell_type.value} (should be 'D')")
    
    # Test 2: Verify to_dict() returns correct coordinates
    print("\n[Test 2] Checking serialized coordinates:")
    grid_dict = grid.to_dict()
    
    # Find the survivor cell in serialized output
    for row in grid_dict["cells"]:
        for cell in row:
            if cell["type"] == "S":
                print(f"  Survivor found at: ({cell['x']}, {cell['y']}) (should be (0, 0))")
                assert cell['x'] == 0 and cell['y'] == 0, "Survivor coordinate mismatch!"
            if cell["type"] == "X":
                print(f"  Hazard found at: ({cell['x']}, {cell['y']}) (should be (4, 0))")
                assert cell['x'] == 4 and cell['y'] == 0, "Hazard coordinate mismatch!"
            if cell["type"] == "#":
                print(f"  Obstacle found at: ({cell['x']}, {cell['y']}) (should be (0, 4))")
                assert cell['x'] == 0 and cell['y'] == 4, "Obstacle coordinate mismatch!"
            if cell["type"] == "D":
                print(f"  Drone found at: ({cell['x']}, {cell['y']}) (should be (4, 4))")
                assert cell['x'] == 4 and cell['y'] == 4, "Drone coordinate mismatch!"
    
    # Test 3: Test drone movement directions
    print("\n[Test 3] Testing drone movement directions:")
    swarm = DroneSwarm(grid)
    swarm.add_drone("TestDrone", 2, 2)  # Center of grid
    
    print(f"  Initial position: (2, 2)")
    
    # Move north (up, +Y)
    swarm.move_drone("TestDrone", 0, 1)
    drone = swarm.drones["TestDrone"]
    print(f"  After moving NORTH (dy=+1): ({drone.x}, {drone.y}) (should be (2, 3))")
    assert drone.x == 2 and drone.y == 3, "North movement failed!"
    
    # Move east (right, +X)
    swarm.move_drone("TestDrone", 1, 0)
    print(f"  After moving EAST (dx=+1): ({drone.x}, {drone.y}) (should be (3, 3))")
    assert drone.x == 3 and drone.y == 3, "East movement failed!"
    
    # Move south (down, -Y)
    swarm.move_drone("TestDrone", 0, -1)
    print(f"  After moving SOUTH (dy=-1): ({drone.x}, {drone.y}) (should be (3, 2))")
    assert drone.x == 3 and drone.y == 2, "South movement failed!"
    
    # Move west (left, -X)
    swarm.move_drone("TestDrone", -1, 0)
    print(f"  After moving WEST (dx=-1): ({drone.x}, {drone.y}) (should be (2, 2))")
    assert drone.x == 2 and drone.y == 2, "West movement failed!"
    
    print("\n" + "=" * 60)
    print("[SUCCESS] ALL TESTS PASSED - Coordinate system is correct!")
    print("=" * 60)
    print("\nCoordinate System Summary:")
    print("  - Origin (0,0) is at BOTTOM-LEFT")
    print("  - X-axis: 0 (left) to width-1 (right)")
    print("  - Y-axis: 0 (bottom) to height-1 (top)")
    print("  - North: dy = +1 (Y increases)")
    print("  - South: dy = -1 (Y decreases)")
    print("  - East: dx = +1 (X increases)")
    print("  - West: dx = -1 (X decreases)")
    print("=" * 60)

if __name__ == "__main__":
    test_coordinate_system()
