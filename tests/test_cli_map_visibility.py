from maze import Position


def test_exit_hidden_until_discovered(maze_module):
    import main

    maze = maze_module.build_minimal_3x3_maze()
    pos = maze.start

    fog_map = main._render_map(maze, pos, visited={pos}, reveal_all=False)
    assert " X " not in fog_map

    revealed = main._render_map(maze, pos, visited={pos, maze.exit}, reveal_all=False)
    assert " X " in revealed


def test_unvisited_cells_are_masked(maze_module):
    import main

    maze = maze_module.build_minimal_3x3_maze()
    pos = maze.start
    fog_map = main._render_map(maze, pos, visited={pos}, reveal_all=False)
    assert "###" in fog_map
