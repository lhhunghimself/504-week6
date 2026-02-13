from collections import deque

import pytest


def _import_required(name: str):
    try:
        return __import__(name)
    except ModuleNotFoundError as e:
        pytest.fail(
            f"Required module '{name}.py' not found yet. "
            f"Create {name}.py to satisfy the engine integration test contract. "
            f"Original error: {e}"
        )


def _dir_token(direction) -> str:
    # Prefer enum name (e.g. "N") but tolerate other representations.
    return getattr(direction, "name", str(direction))


def _bfs_path_to_exit(maze):
    """
    Compute a physical path (list of Directions) from start to exit using only the maze API.
    Ignores gating/puzzles; engine tests will handle gates dynamically.
    """
    start = maze.start
    goal = maze.exit

    q = deque([start])
    prev = {start: None}
    prev_dir = {}

    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for d in maze.available_moves(cur):
            nxt = maze.next_pos(cur, d)
            if nxt is None or nxt in prev:
                continue
            prev[nxt] = cur
            prev_dir[nxt] = d
            q.append(nxt)

    assert goal in prev, "Exit must be reachable for engine integration tests"

    # Reconstruct directions from start->goal
    dirs = []
    cur = goal
    while cur != start:
        d = prev_dir[cur]
        dirs.append(d)
        cur = prev[cur]
    dirs.reverse()
    return dirs


def test_new_game_view_has_valid_position_and_moves(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None, "main.GameEngine must exist per interfaces.md"
    assert cmd_cls is not None, "main.Command must exist per interfaces.md"

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)
    view = engine.view()

    pos = view["pos"] if isinstance(view, dict) else view.pos
    assert maze.in_bounds(maze_module.Position(row=pos["row"], col=pos["col"]))

    moves = view["available_moves"] if isinstance(view, dict) else view.available_moves
    assert moves, "available_moves should be non-empty at start"


def test_player_can_progress_after_solving_required_puzzle(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    path = _bfs_path_to_exit(maze)
    assert path, "Path to exit should have at least one move in a 3x3 maze"

    # Try first move; if gated, solve puzzle and retry.
    first_dir = path[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(first_dir)]))
    view = out["view"] if isinstance(out, dict) else out.view

    pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
    if pending is not None:
        # Solve any pending puzzle with the registry's known correct answer ('solve').
        out2 = engine.handle(cmd_cls(verb="answer", args=["solve"]))
        view2 = out2["view"] if isinstance(out2, dict) else out2.view
        pending2 = view2["pending_puzzle"] if isinstance(view2, dict) else view2.pending_puzzle
        assert pending2 is None, "Puzzle should clear after correct answer"

        out3 = engine.handle(cmd_cls(verb="go", args=[_dir_token(first_dir)]))
        view3 = out3["view"] if isinstance(out3, dict) else out3.view
        pending3 = view3["pending_puzzle"] if isinstance(view3, dict) else view3.pending_puzzle
        assert pending3 is None


def test_reaching_exit_completes_game_and_records_score(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    for d in _bfs_path_to_exit(maze):
        out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
        view = out["view"] if isinstance(out, dict) else out.view

        pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
        while pending is not None:
            out = engine.handle(cmd_cls(verb="answer", args=["solve"]))
            view = out["view"] if isinstance(out, dict) else out.view
            pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
            if pending is not None:
                # If puzzle remains pending, engine is not accepting correct answers.
                pytest.fail("Pending puzzle did not clear after answer")

            # retry the move after solving
            out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
            view = out["view"] if isinstance(out, dict) else out.view
            pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle

    final_view = engine.view()
    is_complete = final_view["is_complete"] if isinstance(final_view, dict) else final_view.is_complete
    assert is_complete is True

    # Verify game marked completed in persistence
    saved = repo.get_game(game_id)
    status = saved["status"] if isinstance(saved, dict) else saved.status
    assert status == "completed"

    # Verify a score exists for this maze (exact retrieval mechanism is repo-defined;
    # we use top_scores to confirm at least one entry exists).
    scores = repo.top_scores(maze_id=maze.maze_id, limit=10)
    assert scores, "Expected at least one score to be recorded on completion"


def test_save_command_persists_progress_mid_run(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    # Make at least one move; if first edge is gated, solve and retry.
    d = _bfs_path_to_exit(maze)[0]
    out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    view = out["view"] if isinstance(out, dict) else out.view
    pending = view["pending_puzzle"] if isinstance(view, dict) else view.pending_puzzle
    if pending is not None:
        engine.handle(cmd_cls(verb="answer", args=["solve"]))
        engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
    engine.handle(cmd_cls(verb="save", args=[]))

    saved = repo.get_game(game_id)
    state = saved["state"] if isinstance(saved, dict) else saved.state
    assert state.get("move_count", 0) >= 1


def test_invalid_command_does_not_corrupt_state(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine", None)
    cmd_cls = getattr(main, "Command", None)
    assert engine_cls is not None
    assert cmd_cls is not None

    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {"pos": {"row": maze.start.row, "col": maze.start.col}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"}
    game = repo.create_game(player_id=player_id, maze_id=maze.maze_id, maze_version=maze.maze_version, initial_state=initial_state)
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(maze=maze, repo=repo, puzzles=puzzle_registry, player_id=player_id, game_id=game_id)

    baseline = engine.view()
    baseline_pos = baseline["pos"] if isinstance(baseline, dict) else baseline.pos
    baseline_moves = baseline.get("move_count") if isinstance(baseline, dict) else getattr(baseline, "move_count", None)

    out = engine.handle(cmd_cls(verb="warp", args=["now"]))
    view = out["view"] if isinstance(out, dict) else out.view

    after = engine.view()
    after_pos = after["pos"] if isinstance(after, dict) else after.pos
    after_moves = after.get("move_count") if isinstance(after, dict) else getattr(after, "move_count", None)

    assert after_pos == baseline_pos
    if baseline_moves is not None and after_moves is not None:
        assert after_moves == baseline_moves

