"""
grid.py — 2D Grid World
Member 3 (Simulation) workspace.

Defines the simulation environment: the grid, cell types,
survivor placement, and hazard placement.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


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


# ---------------------------------------------------------------------------
# TODO (Member 3): Add helper functions for:
#   - place_survivors(grid, count)
#   - place_hazards(grid, count)
#   - place_obstacles(grid, count)
# ---------------------------------------------------------------------------
