from collections import deque

import pytest


def _import_required(name: str):
    try:
        return __import__(name)
    except ModuleNotFoundError as e:
        pytest.fail(
            f"Required module '{name}.py' not found yet. "
            f"Create {name}.py to satisfy the engine unit test contract. "
            f"Original error: {e}"
        )


def _dir_token(direction) -> str:
    return getattr(direction, "name", str(direction))


def _build_engine(maze_module, repo, puzzle_registry):
    main = _import_required("main")
    maze = maze_module.build_minimal_3x3_maze()
    player = repo.get_or_create_player("trinity")
    player_id = player["id"] if isinstance(player, dict) else player.id
    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id
    engine = main.GameEngine(
        maze=maze,
        repo=repo,
        puzzles=puzzle_registry,
        player_id=player_id,
        game_id=game_id,
    )
    return main, maze, engine


def _path_to_exit(maze):
    q = deque([maze.start])
    prev = {maze.start: None}
    prev_dir = {}
    while q:
        cur = q.popleft()
        if cur == maze.exit:
            break
        for d in maze.available_moves(cur):
            nxt = maze.next_pos(cur, d)
            if nxt is None or nxt in prev:
                continue
            prev[nxt] = cur
            prev_dir[nxt] = d
            q.append(nxt)
    assert maze.exit in prev
    dirs = []
    cur = maze.exit
    while cur != maze.start:
        dirs.append(prev_dir[cur])
        cur = prev[cur]
    dirs.reverse()
    return dirs


def _first_gated_direction(maze):
    for d in maze.available_moves(maze.start):
        if maze.gate_id_for(maze.start, d) is not None:
            return d
    pytest.fail("Expected at least one gated direction from start.")


def _first_ungated_direction(maze):
    for d in maze.available_moves(maze.start):
        if maze.gate_id_for(maze.start, d) is None:
            return d
    pytest.fail("Expected at least one ungated direction from start.")


def test_direction_parsing(maze_module, repo, puzzle_registry):
    main, _, engine = _build_engine(maze_module, repo, puzzle_registry)
    out = engine.handle(main.Command(verb="go", args=["E"]))
    assert out.view.pending_puzzle is not None


def test_ungated_move_updates_position(maze_module, repo, puzzle_registry):
    main, maze, engine = _build_engine(maze_module, repo, puzzle_registry)
    d = _first_ungated_direction(maze)
    before = engine.view().pos
    out = engine.handle(main.Command(verb="go", args=[_dir_token(d)]))
    after = out.view.pos
    assert after != before
    assert out.view.move_count == 1


def test_gated_move_blocks_without_answer(maze_module, repo, puzzle_registry):
    main, maze, engine = _build_engine(maze_module, repo, puzzle_registry)
    d = _first_gated_direction(maze)
    before = engine.view().pos
    out = engine.handle(main.Command(verb="go", args=[_dir_token(d)]))
    assert out.view.pos == before
    assert out.view.pending_puzzle is not None
    assert out.view.move_count == 0


def test_correct_answer_clears_pending_puzzle(maze_module, repo, puzzle_registry):
    main, maze, engine = _build_engine(maze_module, repo, puzzle_registry)
    d = _first_gated_direction(maze)
    engine.handle(main.Command(verb="go", args=[_dir_token(d)]))
    out = engine.handle(main.Command(verb="answer", args=["solve"]))
    assert out.view.pending_puzzle is None


def test_incorrect_answer_keeps_puzzle_pending(maze_module, repo, puzzle_registry):
    main, maze, engine = _build_engine(maze_module, repo, puzzle_registry)
    d = _first_gated_direction(maze)
    engine.handle(main.Command(verb="go", args=[_dir_token(d)]))
    out = engine.handle(main.Command(verb="answer", args=["wrong"]))
    assert out.view.pending_puzzle is not None


def test_save_command_sets_did_persist(maze_module, repo, puzzle_registry):
    main, _, engine = _build_engine(maze_module, repo, puzzle_registry)
    out = engine.handle(main.Command(verb="save", args=[]))
    assert out.did_persist is True


def test_completion_records_score_once(maze_module, repo, puzzle_registry):
    main, maze, engine = _build_engine(maze_module, repo, puzzle_registry)
    for d in _path_to_exit(maze):
        out = engine.handle(main.Command(verb="go", args=[_dir_token(d)]))
        while out.view.pending_puzzle is not None:
            engine.handle(main.Command(verb="answer", args=["solve"]))
            out = engine.handle(main.Command(verb="go", args=[_dir_token(d)]))
    scores_before = len(repo.top_scores(maze_id=maze.maze_id, limit=50))
    engine.handle(main.Command(verb="save", args=[]))
    scores_after = len(repo.top_scores(maze_id=maze.maze_id, limit=50))
    assert scores_before == 1
    assert scores_after == 1


def test_invalid_command_returns_error_message(maze_module, repo, puzzle_registry):
    main, _, engine = _build_engine(maze_module, repo, puzzle_registry)
    before = engine.view()
    out = engine.handle(main.Command(verb="warp", args=["now"]))
    after = engine.view()
    assert out.messages
    assert after.pos == before.pos
    assert after.move_count == before.move_count


def test_save_load_round_trip_preserves_state(maze_module, repo, puzzle_registry):
    """Create engine, make moves, save, then create a NEW engine from same
    game_id and verify state was reconstructed correctly."""
    main, maze, engine = _build_engine(maze_module, repo, puzzle_registry)
    d = _first_ungated_direction(maze)
    engine.handle(main.Command(verb="go", args=[_dir_token(d)]))
    engine.handle(main.Command(verb="save", args=[]))

    saved_view = engine.view()

    # Build a brand-new engine from the same persisted game
    engine2 = main.GameEngine(
        maze=maze,
        repo=repo,
        puzzles=puzzle_registry,
        player_id=engine.player_id,
        game_id=engine.game_id,
    )
    restored_view = engine2.view()

    assert restored_view.pos == saved_view.pos
    assert restored_view.move_count == saved_view.move_count
    assert restored_view.is_complete == saved_view.is_complete


def test_short_form_direction_verbs(maze_module, repo, puzzle_registry):
    """Bare n/s/e/w verbs should work like 'go N/S/E/W'."""
    main, maze, engine = _build_engine(maze_module, repo, puzzle_registry)
    d = _first_ungated_direction(maze)
    token = _dir_token(d).lower()  # e.g. "s"
    before = engine.view().pos
    out = engine.handle(main.Command(verb=token, args=[]))
    assert out.view.pos != before
    assert out.view.move_count == 1


def test_look_command_returns_current_view(maze_module, repo, puzzle_registry):
    main, _, engine = _build_engine(maze_module, repo, puzzle_registry)
    baseline = engine.view()
    out = engine.handle(main.Command(verb="look", args=[]))
    assert out.view.pos == baseline.pos
    assert out.view.cell_title == baseline.cell_title
    assert out.did_persist is False


def test_map_command_returns_current_view(maze_module, repo, puzzle_registry):
    main, _, engine = _build_engine(maze_module, repo, puzzle_registry)
    baseline = engine.view()
    out = engine.handle(main.Command(verb="map", args=[]))
    assert out.view.pos == baseline.pos
    assert out.did_persist is False


def test_answer_without_pending_puzzle(maze_module, repo, puzzle_registry):
    main, _, engine = _build_engine(maze_module, repo, puzzle_registry)
    out = engine.handle(main.Command(verb="answer", args=["something"]))
    assert "No pending puzzle" in out.messages[0]
    assert out.did_persist is False
