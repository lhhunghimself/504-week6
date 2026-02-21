from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class Direction(Enum):
    N = (-1, 0)
    S = (1, 0)
    E = (0, 1)
    W = (0, -1)

    @property
    def delta(self) -> tuple[int, int]:
        return self.value

    @property
    def opposite(self) -> "Direction":
        return {
            Direction.N: Direction.S,
            Direction.S: Direction.N,
            Direction.E: Direction.W,
            Direction.W: Direction.E,
        }[self]


@dataclass(frozen=True)
class Position:
    row: int
    col: int


class CellKind(Enum):
    START = "start"
    EXIT = "exit"
    NORMAL = "normal"


@dataclass(frozen=True)
class CellSpec:
    pos: Position
    kind: CellKind
    title: str
    description: str
    blocked: frozenset[Direction] = field(default_factory=frozenset)
    puzzle_id: str | None = None
    edge_gates: Dict[Direction, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Maze:
    maze_id: str
    maze_version: str
    width: int
    height: int
    start: Position
    exit: Position
    cells: Dict[Position, CellSpec]

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.row < self.height and 0 <= pos.col < self.width

    def cell(self, pos: Position) -> CellSpec:
        if not self.in_bounds(pos):
            raise ValueError(f"Out of bounds position: {pos}")
        return self.cells[pos]

    def available_moves(self, pos: Position) -> set[Direction]:
        if not self.in_bounds(pos):
            return set()

        here = self.cell(pos)
        moves: set[Direction] = set()
        for direction in Direction:
            if direction in here.blocked:
                continue
            nxt = self.next_pos(pos, direction)
            if nxt is None:
                continue
            nxt_cell = self.cell(nxt)
            if direction.opposite in nxt_cell.blocked:
                continue
            moves.add(direction)
        return moves

    def next_pos(self, pos: Position, direction: Direction) -> Position | None:
        if not self.in_bounds(pos):
            return None
        here = self.cell(pos)
        if direction in here.blocked:
            return None
        dr, dc = direction.delta
        nxt = Position(row=pos.row + dr, col=pos.col + dc)
        if not self.in_bounds(nxt):
            return None
        nxt_cell = self.cell(nxt)
        if direction.opposite in nxt_cell.blocked:
            return None
        return nxt

    def puzzle_id_at(self, pos: Position) -> str | None:
        if not self.in_bounds(pos):
            return None
        return self.cell(pos).puzzle_id

    def gate_id_for(self, pos: Position, direction: Direction) -> str | None:
        if not self.in_bounds(pos):
            return None
        return self.cell(pos).edge_gates.get(direction)


def _make_grid(width: int, height: int) -> Dict[Position, dict]:
    data: Dict[Position, dict] = {}
    for r in range(height):
        for c in range(width):
            pos = Position(row=r, col=c)
            data[pos] = {
                "kind": CellKind.NORMAL,
                "title": f"Node {r},{c}",
                "description": "Neon-lit system corridor.",
                "blocked": set(),
                "puzzle_id": None,
                "edge_gates": {},
            }
    return data


def _add_wall(grid: Dict[Position, dict], pos: Position, direction: Direction) -> None:
    grid[pos]["blocked"].add(direction)
    dr, dc = direction.delta
    other = Position(row=pos.row + dr, col=pos.col + dc)
    if other in grid:
        grid[other]["blocked"].add(direction.opposite)


def build_minimal_3x3_maze() -> Maze:
    width, height = 3, 3
    start = Position(0, 0)
    exit_pos = Position(2, 2)

    grid = _make_grid(width=width, height=height)

    grid[start]["kind"] = CellKind.START
    grid[start]["title"] = "Ingress Port"
    grid[start]["description"] = "You jack into the internal network."

    grid[exit_pos]["kind"] = CellKind.EXIT
    grid[exit_pos]["title"] = "Root Access Gateway"
    grid[exit_pos]["description"] = "One final jump grants root shell."

    # A small fixed maze shape.
    _add_wall(grid, Position(0, 1), Direction.S)
    _add_wall(grid, Position(1, 0), Direction.S)
    _add_wall(grid, Position(1, 1), Direction.E)

    # Gate one edge and place a corresponding puzzle in the adjacent cell.
    gate_id = "gate-python-basics-1"
    grid[start]["edge_gates"][Direction.E] = gate_id
    grid[Position(0, 1)]["puzzle_id"] = gate_id
    grid[Position(0, 1)]["title"] = "Firewall Lattice"
    grid[Position(0, 1)]["description"] = "A Python challenge guards this route."

    cells: Dict[Position, CellSpec] = {}
    for pos, item in grid.items():
        cells[pos] = CellSpec(
            pos=pos,
            kind=item["kind"],
            title=item["title"],
            description=item["description"],
            blocked=frozenset(item["blocked"]),
            puzzle_id=item["puzzle_id"],
            edge_gates=dict(item["edge_gates"]),
        )

    return Maze(
        maze_id="maze-3x3-v1",
        maze_version="1.0",
        width=width,
        height=height,
        start=start,
        exit=exit_pos,
        cells=cells,
    )


def build_square_maze(size: int, seed: int) -> Maze:
    """Procedurally generate an NxN maze using seeded recursive backtracker."""
    rng = random.Random(seed)
    width = height = size
    start = Position(0, 0)
    exit_pos = Position(size - 1, size - 1)

    # Grid: each cell starts with all 4 walls (all directions blocked)
    grid = _make_grid(width=width, height=height)
    for pos in grid:
        grid[pos]["blocked"] = {Direction.N, Direction.S, Direction.E, Direction.W}

    # Recursive backtracker: carve passages
    visited: set[Position] = set()

    def carve(pos: Position) -> None:
        visited.add(pos)
        neighbors: list[tuple[Position, Direction]] = []
        for d in Direction:
            dr, dc = d.delta
            nr, nc = pos.row + dr, pos.col + dc
            if 0 <= nr < height and 0 <= nc < width:
                npos = Position(nr, nc)
                if npos not in visited:
                    neighbors.append((npos, d))
        rng.shuffle(neighbors)
        for npos, d in neighbors:
            if npos not in visited:
                # Remove wall between pos and npos
                grid[pos]["blocked"].discard(d)
                grid[npos]["blocked"].discard(d.opposite)
                carve(npos)

    carve(start)

    # Mark start and exit
    grid[start]["kind"] = CellKind.START
    grid[start]["title"] = "Ingress Port"
    grid[start]["description"] = "You jack into the internal network."

    grid[exit_pos]["kind"] = CellKind.EXIT
    grid[exit_pos]["title"] = "Root Access Gateway"
    grid[exit_pos]["description"] = "One final jump grants root shell."

    # Find path from start to exit (BFS) to place gate on an edge along the path
    path_edges: list[tuple[Position, Direction]] = []
    q: list[Position] = [start]
    parent: Dict[Position, tuple[Position, Direction] | None] = {start: None}
    while q:
        cur = q.pop(0)
        if cur == exit_pos:
            break
        for d in Direction:
            if d in grid[cur]["blocked"]:
                continue
            dr, dc = d.delta
            npos = Position(cur.row + dr, cur.col + dc)
            if npos not in parent:
                parent[npos] = (cur, d)
                q.append(npos)

    # Reconstruct path edges
    cur = exit_pos
    while parent[cur] is not None:
        prev, d = parent[cur]
        path_edges.append((prev, d))
        cur = prev

    # Place at least one gate on a random edge along the path
    if path_edges:
        gate_pos, gate_dir = path_edges[rng.randint(0, len(path_edges) - 1)]
        gate_id = f"gate-dynamic-{seed}"
        grid[gate_pos]["edge_gates"][gate_dir] = gate_id
        # Puzzle in the cell we're moving to
        dr, dc = gate_dir.delta
        next_pos = Position(gate_pos.row + dr, gate_pos.col + dc)
        grid[next_pos]["puzzle_id"] = gate_id
        grid[next_pos]["title"] = "Firewall Lattice"
        grid[next_pos]["description"] = "A challenge guards this route."

    cells: Dict[Position, CellSpec] = {}
    for pos, item in grid.items():
        cells[pos] = CellSpec(
            pos=pos,
            kind=item["kind"],
            title=item["title"],
            description=item["description"],
            blocked=frozenset(item["blocked"]),
            puzzle_id=item["puzzle_id"],
            edge_gates=dict(item["edge_gates"]),
        )

    return Maze(
        maze_id=f"maze-{size}x{size}-v1",
        maze_version="1.0",
        width=width,
        height=height,
        start=start,
        exit=exit_pos,
        cells=cells,
    )

