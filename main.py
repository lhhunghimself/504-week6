from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from maze import Direction, Position


@dataclass(frozen=True)
class Command:
    """
    Normalized command object consumed by the engine.
    """

    verb: str
    args: list[str] = field(default_factory=list)


@dataclass
class GameView:
    """
    UI-agnostic state projection returned by the engine.
    """

    pos: dict[str, int]
    cell_title: str
    cell_description: str
    available_moves: list[str]
    pending_puzzle: dict[str, str] | None
    is_complete: bool
    move_count: int = 0


@dataclass
class GameOutput:
    """
    Wrapper for state + user-facing messages from engine commands.
    """

    view: GameView
    messages: list[str] = field(default_factory=list)
    did_persist: bool = False


class GameEngine:
    def __init__(
        self,
        *,
        maze: Any,
        repo: Any,
        puzzles: Any,
        player_id: str,
        game_id: str,
    ):
        self.maze = maze
        self.repo = repo
        self.puzzles = puzzles
        self.player_id = player_id
        self.game_id = game_id
        self._score_recorded = False
        self._load_state()

    def _load_state(self) -> None:
        game = self.repo.get_game(self.game_id)
        if game is None:
            raise KeyError(f"Unknown game_id: {self.game_id}")
        game_state = game["state"] if isinstance(game, dict) else game.state
        status = game["status"] if isinstance(game, dict) else game.status

        pos = game_state.get("pos", {"row": self.maze.start.row, "col": self.maze.start.col})
        self._pos = Position(row=pos["row"], col=pos["col"])
        self._move_count = int(game_state.get("move_count", 0))
        self._solved_gates = set(game_state.get("solved_gates", []))
        self._started_at = game_state.get("started_at")
        self._pending_gate_id: str | None = None
        self._is_complete = status == "completed"

    def _serialize_state(self) -> dict[str, Any]:
        return {
            "pos": {"row": self._pos.row, "col": self._pos.col},
            "move_count": self._move_count,
            "solved_gates": sorted(self._solved_gates),
            "started_at": self._started_at,
            "ended_at": _utc_now_iso() if self._is_complete else None,
        }

    def _persist(self, status: str = "in_progress") -> None:
        self.repo.save_game(game_id=self.game_id, state=self._serialize_state(), status=status)

    def _direction_from_token(self, token: str | None) -> Direction | None:
        if token is None:
            return None
        t = token.strip().upper()
        if t == "NORTH":
            t = "N"
        elif t == "SOUTH":
            t = "S"
        elif t == "EAST":
            t = "E"
        elif t == "WEST":
            t = "W"
        return Direction.__members__.get(t)

    def _pending_puzzle_payload(self) -> dict[str, str] | None:
        if self._pending_gate_id is None:
            return None
        puzzle = self.puzzles.get(self._pending_gate_id)
        return {"puzzle_id": puzzle.id, "title": puzzle.title, "prompt": puzzle.prompt}

    def _available_move_tokens(self) -> list[str]:
        return sorted(d.name for d in self.maze.available_moves(self._pos))

    def _maybe_finish(self) -> bool:
        if self._pos != self.maze.exit:
            return False
        self._is_complete = True
        self._persist(status="completed")

        if not self._score_recorded:
            metrics = {
                "elapsed_seconds": _elapsed_seconds(self._started_at),
                "moves": self._move_count,
                "puzzles_solved": len(self._solved_gates),
            }
            self.repo.record_score(
                player_id=self.player_id,
                game_id=self.game_id,
                maze_id=self.maze.maze_id,
                maze_version=self.maze.maze_version,
                metrics=metrics,
            )
            self._score_recorded = True
        return True

    def _make_view(self) -> GameView:
        cell = self.maze.cell(self._pos)
        return GameView(
            pos={"row": self._pos.row, "col": self._pos.col},
            cell_title=cell.title,
            cell_description=cell.description,
            available_moves=self._available_move_tokens(),
            pending_puzzle=self._pending_puzzle_payload(),
            is_complete=self._is_complete,
            move_count=self._move_count,
        )

    def view(self) -> GameView:
        return self._make_view()

    def handle(self, command: Command) -> GameOutput:
        verb = (command.verb or "").strip().lower()
        args = command.args or []
        messages: list[str] = []
        did_persist = False

        if verb in {"look", "map"}:
            return GameOutput(view=self._make_view(), messages=[], did_persist=False)

        if verb == "save":
            self._persist(status="completed" if self._is_complete else "in_progress")
            return GameOutput(view=self._make_view(), messages=["Progress saved."], did_persist=True)

        if verb == "answer":
            if self._pending_gate_id is None:
                return GameOutput(view=self._make_view(), messages=["No pending puzzle."], did_persist=False)
            answer = " ".join(args).strip()
            puzzle = self.puzzles.get(self._pending_gate_id)
            if puzzle.check(answer, self._serialize_state()):
                self._solved_gates.add(self._pending_gate_id)
                self._pending_gate_id = None
                self._persist(status="in_progress")
                did_persist = True
                messages.append("Correct.")
            else:
                messages.append("Incorrect answer.")
            return GameOutput(view=self._make_view(), messages=messages, did_persist=did_persist)

        if verb in {"n", "s", "e", "w"}:
            direction = self._direction_from_token(verb)
        elif verb == "go":
            direction = self._direction_from_token(args[0] if args else None)
        else:
            return GameOutput(view=self._make_view(), messages=["Unknown command."], did_persist=False)

        if direction is None:
            return GameOutput(view=self._make_view(), messages=["Invalid direction."], did_persist=False)

        if self._pending_gate_id is not None:
            return GameOutput(view=self._make_view(), messages=["Solve the pending puzzle first."], did_persist=False)

        gate_id = self.maze.gate_id_for(self._pos, direction)
        if gate_id is not None and gate_id not in self._solved_gates:
            self._pending_gate_id = gate_id
            return GameOutput(view=self._make_view(), messages=["Puzzle required."], did_persist=False)

        nxt = self.maze.next_pos(self._pos, direction)
        if nxt is None:
            return GameOutput(view=self._make_view(), messages=["Blocked path."], did_persist=False)

        self._pos = nxt
        self._move_count += 1
        completed = self._maybe_finish()
        if not completed:
            self._persist(status="in_progress")
        return GameOutput(view=self._make_view(), messages=[], did_persist=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _elapsed_seconds(started_at: str | None) -> int:
    if not started_at:
        return 0
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    now = datetime.now(timezone.utc)
    return max(0, int((now - dt).total_seconds()))


# ---------------------------------------------------------------------------
# CLI adapter
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
Commands:
  n / s / e / w   — move in that direction
  go <dir>        — move (north, south, east, west, or N/S/E/W)
  look            — re-describe current cell
  map             — show a simple maze map
  answer <text>   — answer a pending puzzle
  save            — save progress
  scores          — show top scores
  help            — show this help
  quit            — exit the game
"""


def _render_map(maze: Any, pos: Position) -> str:
    """Render a simple text map of the maze with the player marked."""
    lines: list[str] = []
    for r in range(maze.height):
        row_cells: list[str] = []
        for c in range(maze.width):
            p = Position(row=r, col=c)
            cell = maze.cell(p)
            if p == pos:
                icon = " @ "
            elif p == maze.start:
                icon = " S "
            elif p == maze.exit:
                icon = " X "
            elif cell.puzzle_id is not None:
                icon = " ? "
            else:
                icon = " . "
            row_cells.append(icon)

        # Horizontal connectors
        connected: list[str] = []
        for c, token in enumerate(row_cells):
            connected.append(token)
            if c < len(row_cells) - 1:
                p = Position(row=r, col=c)
                if Direction.E in maze.available_moves(p):
                    connected.append("--")
                else:
                    connected.append("  ")
        lines.append("".join(connected))

        # Vertical connectors
        if r < maze.height - 1:
            vert: list[str] = []
            for c in range(maze.width):
                p = Position(row=r, col=c)
                if Direction.S in maze.available_moves(p):
                    vert.append(" | ")
                else:
                    vert.append("   ")
                if c < maze.width - 1:
                    vert.append("  ")
            lines.append("".join(vert))
    return "\n".join(lines)


def _render_view(view: GameView, maze: Any, pos: Position, messages: list[str]) -> str:
    """Format engine output for terminal display."""
    parts: list[str] = []

    parts.append(f"\n--- {view.cell_title} ---")
    parts.append(view.cell_description)
    parts.append(f"Position: ({view.pos['row']}, {view.pos['col']})  |  Moves: {view.move_count}")
    parts.append(f"Exits: {', '.join(view.available_moves)}")

    if view.pending_puzzle:
        parts.append("")
        parts.append(f">> PUZZLE: {view.pending_puzzle['title']}")
        parts.append(view.pending_puzzle["prompt"])
        parts.append("  Use: answer <your answer>")

    if view.is_complete:
        parts.append("")
        parts.append("*** ACCESS GRANTED — You have reached root. Game complete! ***")

    for msg in messages:
        parts.append(f"  [{msg}]")

    return "\n".join(parts)


def _parse_input(raw: str) -> Command:
    """Parse raw CLI input into a Command."""
    tokens = raw.strip().split()
    if not tokens:
        return Command(verb="", args=[])
    return Command(verb=tokens[0], args=tokens[1:])


def cli_main() -> None:
    """Interactive CLI entry point for the quiz maze game."""
    from pathlib import Path

    from db import JsonGameRepository
    from maze import build_minimal_3x3_maze
    from puzzles import PuzzleRegistry

    print("=" * 50)
    print("  HACK THE MAZE  —  A Python Puzzle Adventure")
    print("=" * 50)
    print()

    # --- Setup ---
    save_path = Path("game_save.json")
    repo = JsonGameRepository(save_path)
    maze = build_minimal_3x3_maze()
    puzzles = PuzzleRegistry()

    handle = input("Enter your hacker handle: ").strip() or "anonymous"
    player = repo.get_or_create_player(handle)
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": _utc_now_iso(),
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = GameEngine(
        maze=maze,
        repo=repo,
        puzzles=puzzles,
        player_id=player_id,
        game_id=game_id,
    )

    # --- Initial view ---
    view = engine.view()
    print(_render_view(view, maze, engine._pos, []))
    print()
    print("Type 'help' for commands.")
    print()

    # --- Game loop ---
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession terminated. Progress auto-saved.")
            engine.handle(Command(verb="save", args=[]))
            break

        if not raw:
            continue

        cmd = _parse_input(raw)
        verb = cmd.verb.lower()

        if verb == "quit":
            engine.handle(Command(verb="save", args=[]))
            print("Progress saved. Until next time, hacker.")
            break

        if verb == "help":
            print(_HELP_TEXT)
            continue

        if verb == "scores":
            scores = repo.top_scores(maze_id=maze.maze_id, limit=5)
            if not scores:
                print("  No scores recorded yet.")
            else:
                print("  -- Top Scores --")
                for i, s in enumerate(scores, 1):
                    m = s.get("metrics", {}) if isinstance(s, dict) else s.metrics
                    print(f"  {i}. {m.get('moves', '?')} moves, {m.get('elapsed_seconds', '?')}s")
            print()
            continue

        if verb == "map":
            print()
            print(_render_map(maze, engine._pos))
            print()
            continue

        out = engine.handle(cmd)
        print(_render_view(out.view, maze, engine._pos, out.messages))
        print()

        if out.view.is_complete:
            print("Final score recorded. Type 'scores' to see the leaderboard, or 'quit' to exit.")
            print()


if __name__ == "__main__":
    cli_main()

