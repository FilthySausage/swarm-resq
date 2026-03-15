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


class Grid:
    def __init__(self, width: int = 20, height: int = 20):
        self.width = width
        self.height = height
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(width)] for _ in range(height)
        ]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        if not self.in_bounds(x, y):
            return None
        return self.cells[y][x]

    def set_cell_type(self, x: int, y: int, cell_type: CellType) -> None:
        if self.in_bounds(x, y):
            self.cells[y][x].cell_type = cell_type

    def to_dict(self) -> dict:
        """Serialize the grid state for the MCP server / UI."""
        return {
            "width": self.width,
            "height": self.height,
            "cells": [
                [
                    {
                        "x": x,
                        "y": y,
                        "type": self.cells[y][x].cell_type.value,
                        "drone_id": self.cells[y][x].drone_id,
                    }
                    for x in range(self.width)
                ]
                for y in range(self.height)
            ],
        }

    def __repr__(self) -> str:
        rows = []
        for row in self.cells:
            rows.append(" ".join(c.cell_type.value for c in row))
        return "\n".join(rows)


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
