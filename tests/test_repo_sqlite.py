from pathlib import Path


def test_open_repo_selects_sqlite(db_module, tmp_path):
    path = tmp_path / "state.db"
    repo = db_module.open_repo(path)
    assert repo.__class__.__name__ == "SqliteGameRepository"


def test_sqlite_repo_round_trip_and_ordering(db_module, tmp_path):
    repo_cls = getattr(db_module, "SqliteGameRepository")
    repo = repo_cls(tmp_path / "state.db")

    player = repo.get_or_create_player("neo")
    game = repo.create_game(
        player_id=player["id"],
        maze_id="maze-5x5-v1",
        maze_version="1.0",
        initial_state={"pos": {"row": 0, "col": 0}, "move_count": 0, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"},
    )

    repo.save_game(
        game_id=game["id"],
        state={"pos": {"row": 1, "col": 1}, "move_count": 2, "solved_gates": [], "started_at": "2026-02-13T00:00:00Z"},
        status="in_progress",
    )
    loaded = repo.get_game(game["id"])
    assert loaded is not None
    assert loaded["state"]["move_count"] == 2

    repo.record_score(
        player_id=player["id"],
        game_id=game["id"],
        maze_id="maze-5x5-v1",
        maze_version="1.0",
        metrics={"elapsed_seconds": 12, "moves": 40},
    )
    repo.record_score(
        player_id=player["id"],
        game_id=game["id"],
        maze_id="maze-5x5-v1",
        maze_version="1.0",
        metrics={"elapsed_seconds": 9, "moves": 30},
    )
    repo.record_score(
        player_id=player["id"],
        game_id=game["id"],
        maze_id="maze-5x5-v1",
        maze_version="1.0",
        metrics={"elapsed_seconds": 9, "moves": 10},
    )

    top = repo.top_scores(maze_id="maze-5x5-v1", limit=2)
    assert len(top) == 2
    assert (top[0]["metrics"]["elapsed_seconds"], top[0]["metrics"]["moves"]) == (9, 10)

    if hasattr(repo, "close"):
        repo.close()
