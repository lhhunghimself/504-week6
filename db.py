from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_record(obj: Any) -> Any:
    # Return dicts as-is; convert dataclasses to dicts if needed.
    if isinstance(obj, dict):
        return obj
    try:
        return asdict(obj)
    except TypeError:
        return obj


@dataclass
class PlayerRecord:
    id: str
    handle: str
    created_at: str


@dataclass
class GameRecord:
    id: str
    player_id: str
    maze_id: str
    maze_version: str
    state: dict[str, Any]
    status: str
    created_at: str
    updated_at: str


@dataclass
class ScoreRecord:
    id: str
    player_id: str
    game_id: str
    maze_id: str
    maze_version: str
    metrics: dict[str, Any]
    created_at: str


class JsonGameRepository:
    def __init__(self, path: str | Path, schema_version: int = 1):
        self.path = Path(path)
        self.schema_version = schema_version
        self._ensure_store()

    def _empty_doc(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "players": {},
            "games": {},
            "scores": {},
        }

    def _ensure_store(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_doc(self._empty_doc())

    def _read_doc(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_doc()
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return self._empty_doc()
        doc = json.loads(raw)
        # Backfill missing keys if needed.
        doc.setdefault("schema_version", self.schema_version)
        doc.setdefault("players", {})
        doc.setdefault("games", {})
        doc.setdefault("scores", {})
        return doc

    def _write_doc(self, doc: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.path)

    def _save_doc(self, doc: dict[str, Any]) -> None:
        doc["schema_version"] = self.schema_version
        self._write_doc(doc)

    # Player ops
    def get_player(self, player_id: str) -> dict[str, Any] | None:
        doc = self._read_doc()
        return doc["players"].get(player_id)

    def get_or_create_player(self, handle: str) -> dict[str, Any]:
        doc = self._read_doc()
        for player in doc["players"].values():
            if player.get("handle") == handle:
                return player

        created = PlayerRecord(
            id=str(uuid4()),
            handle=handle,
            created_at=_utc_now_iso(),
        )
        record = _as_record(created)
        doc["players"][record["id"]] = record
        self._save_doc(doc)
        return record

    # Game ops
    def create_game(
        self,
        player_id: str,
        maze_id: str,
        maze_version: str,
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        doc = self._read_doc()
        now = _utc_now_iso()
        created = GameRecord(
            id=str(uuid4()),
            player_id=player_id,
            maze_id=maze_id,
            maze_version=maze_version,
            state=initial_state,
            status="in_progress",
            created_at=now,
            updated_at=now,
        )
        record = _as_record(created)
        doc["games"][record["id"]] = record
        self._save_doc(doc)
        return record

    def get_game(self, game_id: str) -> dict[str, Any] | None:
        doc = self._read_doc()
        return doc["games"].get(game_id)

    def save_game(self, game_id: str, state: dict[str, Any], status: str = "in_progress") -> dict[str, Any]:
        doc = self._read_doc()
        game = doc["games"].get(game_id)
        if game is None:
            raise KeyError(f"Unknown game_id: {game_id}")
        game["state"] = state
        game["status"] = status
        game["updated_at"] = _utc_now_iso()
        self._save_doc(doc)
        return game

    # Score ops
    def record_score(
        self,
        player_id: str,
        game_id: str,
        maze_id: str,
        maze_version: str,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        doc = self._read_doc()
        created = ScoreRecord(
            id=str(uuid4()),
            player_id=player_id,
            game_id=game_id,
            maze_id=maze_id,
            maze_version=maze_version,
            metrics=metrics,
            created_at=_utc_now_iso(),
        )
        record = _as_record(created)
        doc["scores"][record["id"]] = record
        self._save_doc(doc)
        return record

    def top_scores(self, maze_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        doc = self._read_doc()
        items = list(doc["scores"].values())
        if maze_id is not None:
            items = [s for s in items if s.get("maze_id") == maze_id]

        def key_fn(score: dict[str, Any]) -> tuple[Any, Any]:
            metrics = score.get("metrics", {})
            return (metrics.get("elapsed_seconds", float("inf")), metrics.get("moves", float("inf")))

        items.sort(key=key_fn)
        return items[:limit]


# Optional aliases for test/consumer flexibility.
Repository = JsonGameRepository
GameRepository = JsonGameRepository


def open_repo(path: str | Path) -> JsonGameRepository:
    return JsonGameRepository(path)

