from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Field, Session, SQLModel, create_engine, select


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


# ---------------------------------------------------------------------------
# SQLModel tables for SqliteGameRepository
# ---------------------------------------------------------------------------


class PlayerModel(SQLModel, table=True):
    __tablename__ = "players"
    id: str = Field(primary_key=True)
    handle: str
    created_at: str


class GameModel(SQLModel, table=True):
    __tablename__ = "games"
    id: str = Field(primary_key=True)
    player_id: str
    maze_id: str
    maze_version: str
    state_json: str = Field(sa_column_kwargs={"name": "state"})
    status: str
    created_at: str
    updated_at: str


class ScoreModel(SQLModel, table=True):
    __tablename__ = "scores"
    id: str = Field(primary_key=True)
    player_id: str
    game_id: str
    maze_id: str
    maze_version: str
    metrics_json: str = Field(sa_column_kwargs={"name": "metrics"})
    created_at: str


class QuestionModel(SQLModel, table=True):
    __tablename__ = "questions"
    id: str = Field(primary_key=True)
    question_text: str
    correct_answer: str
    category: str = ""
    has_been_asked: bool = False


class SqliteGameRepository:
    """SQLite-backed repository using SQLModel. Same interface as JsonGameRepository."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{self.path}"
        self.engine = create_engine(url, connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(self.engine)
        self._verify_schema()

    def _verify_schema(self) -> None:
        """Drop and recreate tables if the existing schema is incompatible."""
        try:
            with Session(self.engine) as session:
                session.exec(select(GameModel).limit(1)).all()
                session.exec(select(ScoreModel).limit(1)).all()
        except Exception:
            SQLModel.metadata.drop_all(self.engine)
            SQLModel.metadata.create_all(self.engine)

    # Player ops
    def get_player(self, player_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(PlayerModel, player_id)
            if row is None:
                return None
            return {"id": row.id, "handle": row.handle, "created_at": row.created_at}

    def get_or_create_player(self, handle: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            stmt = select(PlayerModel).where(PlayerModel.handle == handle)
            row = session.exec(stmt).first()
            if row is not None:
                return {"id": row.id, "handle": row.handle, "created_at": row.created_at}
            created = PlayerModel(
                id=str(uuid4()),
                handle=handle,
                created_at=_utc_now_iso(),
            )
            session.add(created)
            session.commit()
            session.refresh(created)
            return {"id": created.id, "handle": created.handle, "created_at": created.created_at}

    # Game ops
    def create_game(
        self,
        player_id: str,
        maze_id: str,
        maze_version: str,
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        game_id = str(uuid4())
        with Session(self.engine) as session:
            row = GameModel(
                id=game_id,
                player_id=player_id,
                maze_id=maze_id,
                maze_version=maze_version,
                state_json=json.dumps(initial_state),
                status="in_progress",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()
        return {
            "id": game_id,
            "player_id": player_id,
            "maze_id": maze_id,
            "maze_version": maze_version,
            "state": initial_state,
            "status": "in_progress",
            "created_at": now,
            "updated_at": now,
        }

    def get_game(self, game_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(GameModel, game_id)
            if row is None:
                return None
            state = json.loads(row.state_json) if isinstance(row.state_json, str) else row.state_json
            return {
                "id": row.id,
                "player_id": row.player_id,
                "maze_id": row.maze_id,
                "maze_version": row.maze_version,
                "state": state,
                "status": row.status,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def save_game(self, game_id: str, state: dict[str, Any], status: str = "in_progress") -> dict[str, Any]:
        now = _utc_now_iso()
        with Session(self.engine) as session:
            row = session.get(GameModel, game_id)
            if row is None:
                raise KeyError(f"Unknown game_id: {game_id}")
            row.state_json = json.dumps(state)
            row.status = status
            row.updated_at = now
            session.add(row)
            session.commit()
            session.refresh(row)
        return {
            "id": row.id,
            "player_id": row.player_id,
            "maze_id": row.maze_id,
            "maze_version": row.maze_version,
            "state": state,
            "status": status,
            "created_at": row.created_at,
            "updated_at": now,
        }

    # Score ops
    def record_score(
        self,
        player_id: str,
        game_id: str,
        maze_id: str,
        maze_version: str,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        score_id = str(uuid4())
        with Session(self.engine) as session:
            row = ScoreModel(
                id=score_id,
                player_id=player_id,
                game_id=game_id,
                maze_id=maze_id,
                maze_version=maze_version,
                metrics_json=json.dumps(metrics),
                created_at=now,
            )
            session.add(row)
            session.commit()
        return {
            "id": score_id,
            "player_id": player_id,
            "game_id": game_id,
            "maze_id": maze_id,
            "maze_version": maze_version,
            "metrics": metrics,
            "created_at": now,
        }

    def top_scores(self, maze_id: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            stmt = select(ScoreModel)
            if maze_id is not None:
                stmt = stmt.where(ScoreModel.maze_id == maze_id)
            rows = session.exec(stmt).all()
        items = []
        for row in rows:
            metrics = json.loads(row.metrics_json) if isinstance(row.metrics_json, str) else row.metrics_json
            items.append({
                "id": row.id,
                "player_id": row.player_id,
                "game_id": row.game_id,
                "maze_id": row.maze_id,
                "maze_version": row.maze_version,
                "metrics": metrics,
                "created_at": row.created_at,
            })
        items.sort(key=lambda s: (
            s["metrics"].get("elapsed_seconds", float("inf")),
            s["metrics"].get("moves", float("inf")),
        ))
        return items[:limit]

    # Question Bank ops
    def get_random_question(self, category: str | None = None) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            stmt = select(QuestionModel).where(QuestionModel.has_been_asked == False)
            if category is not None:
                stmt = stmt.where(QuestionModel.category == category)
            rows = list(session.exec(stmt).all())
        if not rows:
            return None
        row = random.choice(rows)
        return {
            "id": row.id,
            "question_text": row.question_text,
            "correct_answer": row.correct_answer,
            "category": row.category,
        }

    def mark_question_asked(self, question_id: str) -> None:
        with Session(self.engine) as session:
            row = session.get(QuestionModel, question_id)
            if row is not None:
                row.has_been_asked = True
                session.add(row)
                session.commit()

    def seed_questions(self, questions: list[dict[str, Any]]) -> None:
        with Session(self.engine) as session:
            for q in questions:
                row = QuestionModel(
                    id=q.get("id", str(uuid4())),
                    question_text=q["question_text"],
                    correct_answer=q["correct_answer"],
                    category=q.get("category", ""),
                    has_been_asked=False,
                )
                session.merge(row)
            session.commit()

    def reset_questions(self) -> None:
        with Session(self.engine) as session:
            rows = session.exec(select(QuestionModel)).all()
            for row in rows:
                row.has_been_asked = False
                session.add(row)
            session.commit()

    def close(self) -> None:
        self.engine.dispose()


def open_repo(path: str | Path):
    """Return SqliteGameRepository for .db paths, JsonGameRepository otherwise."""
    path = Path(path)
    if path.suffix == ".db":
        return SqliteGameRepository(path)
    return JsonGameRepository(path)

