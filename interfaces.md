## Quiz Maze Game — Module Interfaces (Walking Skeleton)

This document defines the *stable contracts* between the 3 modules:
- `maze.py` (domain / world model)
- `db.py` (persistence boundary; JSON-backed mock ORM for now)
- `main.py` (game engine + UI wiring; CLI now, PyQt later)

The goal is to allow each module to be developed and tested independently.

---

## 1) Dependency Rules (keeps modules separable)

- `maze.py` imports **nothing** from `db.py` or `main.py`.
- `db.py` imports **nothing** from `maze.py` or `main.py`.
- `main.py` is the **only** module that imports `maze` and `db` and wires them together.

Persistence stores **only JSON-serializable primitives**. Any `maze.Position` objects must be converted to/from `{"row": int, "col": int}` at the boundary.

---

## 2) Shared Serialization Rules (DB boundary)

All persisted state must be JSON-safe:
- `str | int | float | bool | None`
- `list[...]` of JSON-safe values
- `dict[str, ...]` of JSON-safe values

Timestamps: store as ISO-8601 UTC strings (e.g., `"2026-02-13T10:15:30Z"`).

---

## 3) `maze.py` — Domain Contract

### 3.1 Public Types

- `Direction` (Enum)
  - Values: `N`, `S`, `E`, `W`
  - Each direction has a delta `(dr, dc)`

- `Position` (dataclass)
  - Fields: `row: int`, `col: int`

- `CellKind` (Enum)
  - Values: `START`, `EXIT`, `NORMAL`

- `CellSpec` (dataclass or simple class; immutable preferred)
  - `pos: Position`
  - `kind: CellKind`
  - `title: str` (hacker/Tron flavor)
  - `description: str`
  - `blocked: set[Direction]`
    - Directions that cannot be traversed from this cell
  - `puzzle_id: str | None`
    - Puzzle encountered in this cell (if any)
  - `edge_gates: dict[Direction, str]`
    - Optional movement gates per direction.
    - Value is a `gate_id` (often the same as a `puzzle_id`) that must be satisfied before moving.

### 3.2 `Maze` Interface (what `main.py` relies on)

A concrete `Maze` class should expose at least:

- Identity / sizing
  - `maze_id: str` (stable identifier, e.g. `"maze-3x3-v1"`)
  - `maze_version: str` (semantic-ish, e.g. `"1.0"`)
  - `width: int`, `height: int`
  - `start: Position`, `exit: Position`

- Topology / queries
  - `in_bounds(pos: Position) -> bool`
  - `cell(pos: Position) -> CellSpec`
  - `available_moves(pos: Position) -> set[Direction]`
    - Must account for bounds + `blocked`
  - `next_pos(pos: Position, direction: Direction) -> Position | None`
    - Returns the destination position if the move is physically possible, else `None`

- Puzzle/gate hooks (no puzzle logic inside `maze.py`)
  - `puzzle_id_at(pos: Position) -> str | None`
  - `gate_id_for(pos: Position, direction: Direction) -> str | None`
    - Returns a `gate_id` required to move along that edge, else `None`

### 3.3 Factories

- `build_minimal_3x3_maze() -> Maze`
  - Deterministic hand-authored 3x3 layout
  - Must define `start`, `exit`, walls (`blocked`), and at least 1-2 puzzle placements/gates

- `build_square_maze(size: int, seed: int) -> Maze`
  - Procedurally generates an N×N maze using seeded randomness
  - Uses `random.Random(seed)` for deterministic generation (e.g., recursive backtracker)
  - Start at `Position(0, 0)`, exit at `Position(size-1, size-1)`
  - Must place at least one gate on an edge along a reachable path
  - Returns a `Maze` with `maze_id` and `maze_version` appropriate for the size

### 3.4 Fog of War (renderer responsibility)

Fog-of-war visibility is handled by the engine/CLI renderer, not by `maze.py`. The maze stays purely topological. The renderer receives a `visited: set[Position]` and hides unvisited cells (e.g., as `###`) and the exit until discovered.

---

## 4) `db.py` — Persistence Contract (JSON + SQLite via SQLModel)

### 4.1 Records (DTOs) returned to `main.py`

These are plain dataclasses OR plain dicts (implementation choice), but fields must be stable.

- `PlayerRecord`
  - `id: str`
  - `handle: str`
  - `created_at: str`

- `GameRecord`
  - `id: str`
  - `player_id: str`
  - `maze_id: str`
  - `maze_version: str`
  - `state: dict[str, AnyJSON]`  (opaque to the DB layer)
  - `status: str`  (`"in_progress"` or `"completed"`)
  - `created_at: str`
  - `updated_at: str`

- `ScoreRecord`
  - `id: str`
  - `player_id: str`
  - `game_id: str`
  - `maze_id: str`
  - `maze_version: str`
  - `metrics: dict[str, AnyJSON]`
  - `created_at: str`

### 4.2 Repository / Session Interface (minimum)

`main.py` depends on an object providing these methods:

- Player ops
  - `get_player(player_id: str) -> PlayerRecord | None`
  - `get_or_create_player(handle: str) -> PlayerRecord`

- Game ops
  - `create_game(player_id: str, maze_id: str, maze_version: str, initial_state: dict) -> GameRecord`
  - `get_game(game_id: str) -> GameRecord | None`
  - `save_game(game_id: str, state: dict, status: str = "in_progress") -> GameRecord`

- Score ops
  - `record_score(player_id: str, game_id: str, maze_id: str, maze_version: str, metrics: dict) -> ScoreRecord`
  - `top_scores(maze_id: str | None = None, limit: int = 10) -> list[ScoreRecord]`

Notes:
- `state` is treated as an opaque JSON dict by the DB layer (no imports from `maze.py`).
- IDs are strings (uuid recommended).
- DB implementation should be safe against partial writes (write-then-rename strategy recommended later).

### 4.3 JSON File Shape (JsonGameRepository implementation detail)

Top-level JSON object:
- `schema_version: int`
- `players: { "<player_id>": PlayerRecord-as-dict }`
- `games: { "<game_id>": GameRecord-as-dict }`
- `scores: { "<score_id>": ScoreRecord-as-dict }`

### 4.4 SQLite Backend (SqliteGameRepository)

- `SqliteGameRepository` — same interface as `JsonGameRepository` but backed by SQLite via SQLModel
- Uses SQLModel table classes for `players`, `games`, `scores`, and `questions`
- All methods return plain dicts (or dict-like records) matching the existing contract

- `open_repo(path: str | Path) -> GameRepository`
  - If `path` suffix is `.db` → return `SqliteGameRepository(path)`
  - Otherwise → return `JsonGameRepository(path)` (backward compatible)

### 4.5 Question Bank (SQLite only)

- `QuestionRecord` (table/model) fields:
  - `id: str`
  - `question_text: str`
  - `correct_answer: str`
  - `category: str` (optional grouping)
  - `has_been_asked: bool`

- New methods on repository (SqliteGameRepository; JsonGameRepository may stub or raise):
  - `get_random_question(category: str | None = None) -> dict | None` — returns a random question where `has_been_asked` is `False`; returns `None` if all exhausted
  - `mark_question_asked(question_id: str) -> None` — sets `has_been_asked = True`
  - `seed_questions(questions: list[dict]) -> None` — bulk insert questions for initial population
  - `reset_questions() -> None` — resets all `has_been_asked` to `False`

---

## 5) `main.py` — Engine + UI Wiring (CLI now, PyQt later)

### 5.1 Game State (engine-owned; persisted via DB as JSON dict)

The engine maintains a state object; when persisting, it must be converted to JSON-safe dict.

Minimum suggested persisted keys:
- `pos: {"row": int, "col": int}`
- `move_count: int`
- `solved_gates: list[str]` (or `solved_puzzles: list[str]`)
- `started_at: str`
- `ended_at: str | None`
- `visited: list[{"row": int, "col": int}]` — cells the player has been to; used for fog-of-war rendering

### 5.2 Puzzle Contract (no UI assumptions)

- `Puzzle`
  - `id: str`
  - `title: str`
  - `prompt: str`
  - `check(answer: str, state: dict[str, AnyJSON]) -> bool`
    - Engine passes a JSON-safe view of state (or a lightweight state object internally)

- `PuzzleRegistry`
  - `get(puzzle_id: str) -> Puzzle`

### 5.3 Engine Contract (UI-agnostic)

The engine should not print or read input directly. It should accept intents/commands and return a result.

Minimum:

- `GameEngine`
  - Constructor inputs:
    - `maze: Maze` (from `maze.py`)
    - `repo: GameRepository` (from `db.py`)
    - `puzzles: PuzzleRegistry`
    - `player_id: str`
    - `game_id: str`
    - (optional) `question_source` — repository with `get_random_question` / `mark_question_asked` for DB-backed questions at gates
  - Methods:
    - `view() -> GameView`
    - `handle(command: Command) -> GameOutput`
  - When a player hits a gated door, engine may request an unused question from `question_source` (repo) via `get_random_question()`; falls back to `PuzzleRegistry` if none available. On correct answer, calls `mark_question_asked(question_id)`.

- `Command` (parsed from UI)
  - `verb: str`
  - `args: list[str]`

- `GameView` (what UI renders)
  - `pos: {"row": int, "col": int}`
  - `cell_title: str`
  - `cell_description: str`
  - `available_moves: list[str]` (e.g. `["N","E"]`)
  - `pending_puzzle: {"puzzle_id": str, "title": str, "prompt": str} | None`
  - `is_complete: bool`
  - (optional) `map_text: str | None` — pre-rendered fog-of-war ASCII map for display

- `GameOutput`
  - `view: GameView`
  - `messages: list[str]` (UI can display however it wants)
  - `did_persist: bool` (optional)

### 5.4 CLI rendering (fog of war)

- `_render_map(maze, pos, visited: set[Position], reveal_all: bool = True) -> str`
  - Renders ASCII map with player at `pos`
  - When `reveal_all=False`: unvisited cells show as `###`; exit hidden until in `visited`
  - When `reveal_all=True`: full map visible (legacy behavior)
  - Engine tracks `visited` in state and persists as `list[{"row": int, "col": int}]`

### 5.5 CLI command grammar (walking skeleton)

Minimum verbs (CLI now; PyQt will trigger equivalent commands):
- Movement: `n|s|e|w` or `go <n|s|e|w>`
- `look` (re-describe current cell)
- `map` (show 3x3 view)
- `answer <text>` (submit answer to pending puzzle)
- `save` (persist explicitly; engine may also autosave)
- `quit`

---

## 6) Versioning & Compatibility

- Maze compatibility keys stored in DB:
  - `maze_id`, `maze_version`
- DB compatibility:
  - `schema_version`
- Rule: if `schema_version` changes, provide a migration path (later). For now, keep it at `1` and preserve backward compatibility within the prototype.
