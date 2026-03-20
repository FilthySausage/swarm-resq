"""
grid.py — 2D Grid World
Member 3 (Simulation) workspace.

Defines the simulation environment: the grid, cell types,
survivor placement, and hazard placement.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import random


class CellType(Enum):
    EMPTY = "."
    OBSTACLE = "#"
    SURVIVOR = "S"
    HAZARD = "X"
    DRONE = "D"
    RESCUED = "R"


@dataclass
class Cell:
    cell_type: CellType = CellType.EMPTY
    drone_id: Optional[str] = None
    scanned: bool = False  # Track if cell has been explored/scanned


class Grid:
    """
    2D Grid with BOTTOM-LEFT origin coordinate system.
    
    Coordinate System:
    - Origin (0,0) is at BOTTOM-LEFT corner
    - X-axis: 0 (left) → width-1 (right)
    - Y-axis: 0 (bottom) → height-1 (top)
    
    Internal storage uses list[list[Cell]] where index [0] is top row,
    but external API uses bottom-left coordinates.
    """
    def __init__(self, width: int = 20, height: int = 20):
        self.width = width
        self.height = height
        # Internal storage: cells[0] = top row, cells[height-1] = bottom row
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(width)] for _ in range(height)
        ]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def _to_array_index(self, y: int) -> int:
        """Convert user Y coordinate (bottom-left origin) to internal array index."""
        return self.height - 1 - y

    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        """
        Get cell at (x, y) using bottom-left origin.
        
        Example: get_cell(0, 0) returns bottom-left cell
                 get_cell(0, height-1) returns top-left cell
        """
        if not self.in_bounds(x, y):
            return None
        array_y = self._to_array_index(y)
        return self.cells[array_y][x]

    def set_cell_type(self, x: int, y: int, cell_type: CellType) -> None:
        """Set cell type at (x, y) using bottom-left origin."""
        if self.in_bounds(x, y):
            array_y = self._to_array_index(y)
            self.cells[array_y][x].cell_type = cell_type

    def to_dict(self) -> dict:
        """Serialize the grid state for the MCP server / UI with bottom-left origin."""
        # Build cells array with correct Y coordinates (0 = bottom)
        cells_output = []
        for array_y in range(self.height):
            row = []
            user_y = self.height - 1 - array_y  # Convert array index to user coordinate
            for x in range(self.width):
                row.append({
                    "x": x,
                    "y": user_y,
                    "type": self.cells[array_y][x].cell_type.value,
                    "drone_id": self.cells[array_y][x].drone_id,
                    "scanned": self.cells[array_y][x].scanned,  #UI
                })
            cells_output.append(row)
        
        return {
            "width": self.width,
            "height": self.height,
            "cells": cells_output,
        }

    def __repr__(self) -> str:
        """String representation with bottom-left origin (bottom row printed last)."""
        rows = []
        # Print from top to bottom (array order), but this represents Y from high to low
        for row in self.cells:
            rows.append(" ".join(c.cell_type.value for c in row))
        return "\n".join(rows)

    def mark_cell_scanned(self, x: int, y: int) -> bool:
        """
        Mark a cell as scanned/explored.
        
        Args:
            x, y: Cell coordinates using bottom-left origin
            
        Returns:
            True if marked successfully, False if out of bounds
        """
        if not self.in_bounds(x, y):
            return False
        array_y = self._to_array_index(y)
        self.cells[array_y][x].scanned = True
        return True

    def get_all_unscanned_cells(self) -> list[tuple[int, int]]:
        """
        Get all unscanned cells in the grid.
        
        Returns:
            List of (x, y) coordinates for unscanned cells
        """
        unscanned = []
        for array_y in range(self.height):
            user_y = self.height - 1 - array_y
            for x in range(self.width):
                cell = self.cells[array_y][x]
                if not cell.scanned and cell.cell_type not in (CellType.OBSTACLE, CellType.HAZARD):
                    unscanned.append((x, user_y))
        return unscanned

    def get_nearest_unscanned_cell(self, drone_x: int, drone_y: int) -> Optional[tuple[int, int]]:
        """
        Find the nearest unscanned cell to a drone's position using Chebyshev distance.
        
        Args:
            drone_x, drone_y: Drone position
            
        Returns:
            (x, y) of nearest unscanned cell, or None if all cells scanned
        """
        unscanned = self.get_all_unscanned_cells()
        if not unscanned:
            return None
        
        # Use Chebyshev distance (max of absolute differences) for 8-directional movement
        nearest = min(
            unscanned,
            key=lambda cell: max(abs(cell[0] - drone_x), abs(cell[1] - drone_y))
        )
        return nearest

    def get_unscanned_cells_in_radius(self, x: int, y: int, radius: int) -> list[tuple[int, int]]:
        """
        Get all unscanned cells within Manhattan distance radius of a position.
        
        Args:
            x, y: Center position
            radius: Manhattan distance radius
            
        Returns:
            List of (x, y) coordinates for unscanned cells within radius
        """
        nearby_unscanned = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > radius:
                    continue
                cx, cy = x + dx, y + dy
                if self.in_bounds(cx, cy):
                    cell = self.get_cell(cx, cy)
                    if cell and not cell.scanned and cell.cell_type not in (CellType.OBSTACLE, CellType.HAZARD):
                        nearby_unscanned.append((cx, cy))
        return nearby_unscanned

    def get_scanned_percentage(self) -> float:
        """
        Get percentage of cells that have been scanned.
        
        Returns:
            Percentage (0-100) of scanned cells
        """
        total_cells = self.width * self.height
        scanned_count = sum(
            1 for array_y in range(self.height)
            for x in range(self.width)
            if self.cells[array_y][x].scanned
        )
        return (scanned_count / total_cells) * 100 if total_cells > 0 else 0


def place_survivors(grid: Grid, count: int, avoid_origin: bool = True) -> list[tuple[int, int]]:
    """
    Randomly place survivors on empty cells.
    
    Args:
        grid: The grid to place survivors on
        count: Number of survivors to place
        avoid_origin: If True, never place at (0, 0)
        
    Returns:
        List of (x, y) coordinates where survivors were placed
    """
    placed = []
    attempts = 0
    max_attempts = count * 10

    while len(placed) < count and attempts < max_attempts:
        x = random.randint(0, grid.width - 1)
        y = random.randint(0, grid.height - 1)

        if avoid_origin and (x, y) == (0, 0):
            attempts += 1
            continue

        cell = grid.get_cell(x, y)
        if cell and cell.cell_type == CellType.EMPTY:
            grid.set_cell_type(x, y, CellType.SURVIVOR)
            placed.append((x, y))

        attempts += 1

    return placed


def place_hazards(grid: Grid, count: int) -> list[tuple[int, int]]:
    """
    Randomly place hazards on empty cells.
    
    Args:
        grid: The grid to place hazards on
        count: Number of hazards to place
        
    Returns:
        List of (x, y) coordinates where hazards were placed
    """
    placed = []
    attempts = 0
    max_attempts = count * 10

    while len(placed) < count and attempts < max_attempts:
        x = random.randint(0, grid.width - 1)
        y = random.randint(0, grid.height - 1)

        if (x, y) == (0, 0):  # Never place at base
            attempts += 1
            continue

        cell = grid.get_cell(x, y)
        if cell and cell.cell_type == CellType.EMPTY:
            grid.set_cell_type(x, y, CellType.HAZARD)
            placed.append((x, y))

        attempts += 1

    return placed


def place_obstacles(grid: Grid, count: int) -> list[tuple[int, int]]:
    """
    Randomly place obstacles on empty cells.
    
    Args:
        grid: The grid to place obstacles on
        count: Number of obstacles to place
        
    Returns:
        List of (x, y) coordinates where obstacles were placed
    """
    placed = []
    attempts = 0
    max_attempts = count * 10

    while len(placed) < count and attempts < max_attempts:
        x = random.randint(0, grid.width - 1)
        y = random.randint(0, grid.height - 1)

        if (x, y) == (0, 0):  # Never place at base
            attempts += 1
            continue

        cell = grid.get_cell(x, y)
        if cell and cell.cell_type == CellType.EMPTY:
            grid.set_cell_type(x, y, CellType.OBSTACLE)
            placed.append((x, y))

        attempts += 1

    return placed
