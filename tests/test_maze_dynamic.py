from collections import deque


def _reachable(maze):
    q = deque([maze.start])
    seen = {maze.start}
    while q:
        cur = q.popleft()
        if cur == maze.exit:
            return True
        for direction in maze.available_moves(cur):
            nxt = maze.next_pos(cur, direction)
            if nxt is None or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)
    return False


def test_build_square_maze_size_and_bounds(maze_module):
    maze = maze_module.build_square_maze(size=7, seed=11)
    assert maze.width == 7
    assert maze.height == 7
    assert maze.in_bounds(maze.start)
    assert maze.in_bounds(maze.exit)


def test_build_square_maze_exit_is_reachable(maze_module):
    maze = maze_module.build_square_maze(size=9, seed=3)
    assert _reachable(maze)


def test_build_square_maze_places_at_least_one_gate(maze_module):
    maze = maze_module.build_square_maze(size=8, seed=2)
    gates = []
    for row in range(maze.height):
        for col in range(maze.width):
            pos = maze_module.Position(row=row, col=col)
            for direction in maze_module.Direction:
                gate = maze.gate_id_for(pos, direction)
                if gate is not None:
                    gates.append(gate)
    assert gates
