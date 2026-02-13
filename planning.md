# Quiz Maze Game Planning

This document defines how work is split across developers/agents while keeping a playable mini-game at all times.

## Branch and Merge Strategy

- Create and use a shared planning baseline branch: `planning`.
- Developers branch from `planning` for feature work:
  - `feature/maze-contract`
  - `feature/db-json-repo`
  - `feature/engine-cli`
- Every feature branch must pass unit tests plus shared integration tests before merge.
- Merge order:
  1. `maze` and `db` can merge independently once contract tests pass.
  2. `engine-cli` merges after both contracts are stable.
  3. Final playable baseline merges back into `planning`.

## Shared Interface Contract

The source of truth for module contracts is `interfaces.md`.

- `maze.py` exposes topology and movement APIs only.
- `db.py` exposes repository APIs and stores JSON-safe primitives only.
- `main.py` wires modules together and runs command handling for CLI.

No module may reach across boundaries except through interfaces described in `interfaces.md`.

## Component Ownership

### Maze Developer/Agent (`maze.py`)

Responsibilities:
- Build deterministic `build_minimal_3x3_maze()`.
- Implement movement and gate query methods.
- Keep maze domain independent from DB and UI concerns.

Primary tests:
- `tests/test_maze_contract.py`
- Maze-focused unit tests for edge and wall behavior.

### Database Developer/Agent (`db.py`)

Responsibilities:
- Implement JSON-backed mock ORM/repository interface.
- Persist players, games, and scores with schema versioning.
- Maintain strict JSON serialization boundaries.

Primary tests:
- `tests/test_repo_contract.py`
- Unit tests for file load/save behavior and idempotent operations.

### Engine/CLI Developer/Agent (`main.py`)

Responsibilities:
- Implement game loop and command parser for CLI.
- Integrate maze and repository contracts without leaking abstractions.
- Handle puzzle prompts and completion flow.

Primary tests:
- `tests/test_engine_integration.py`
- Unit tests for command parsing and game state transitions.

## Integration Test Gate (Required for All Merges)

Each branch must pass these shared integration checks:

1. Maze factory creates valid in-bounds start/exit and a reachable path.
2. Repository supports create/load/save game and score queries.
3. End-to-end flow works:
   - start game
   - traverse maze
   - solve required puzzle(s)
   - reach exit
   - persist completion and score

## Playable Mini-Game Definition

The project is considered playable when:
- `main.py` starts a new game from terminal input.
- Player can move through a 3x3 maze via simple commands.
- At least one Python puzzle gates progression.
- Game completion writes score data via `db.py`.

## Notes for Future Expansion

- Keep the game engine UI-agnostic so PyQt can replace CLI rendering later.
- Keep repository interface stable so JSON backend can be swapped for SQLite.
- Add compatibility checks for `maze_version` and `schema_version` as scope grows.
