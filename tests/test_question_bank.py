"""Tests for the Question Bank feature (SqliteGameRepository only)."""

import pytest


@pytest.fixture
def sqlite_repo(db_module, tmp_path):
    """Provide a SqliteGameRepository for question bank tests."""
    repo_cls = getattr(db_module, "SqliteGameRepository", None)
    if repo_cls is None:
        pytest.fail("SqliteGameRepository not implemented yet (design contract)")
    return repo_cls(tmp_path / "questions.db")


def test_seed_and_fetch_question(sqlite_repo):
    """Seed questions, fetch one, verify it is returned."""
    questions = [
        {"id": "q1", "question_text": "What is 2+2?", "correct_answer": "4", "category": "math"},
        {"id": "q2", "question_text": "What is 3+3?", "correct_answer": "6", "category": "math"},
    ]
    sqlite_repo.seed_questions(questions)

    q = sqlite_repo.get_random_question()
    assert q is not None
    assert "id" in q
    assert "question_text" in q
    assert "correct_answer" in q
    assert q["question_text"] in ("What is 2+2?", "What is 3+3?")


def test_mark_question_asked_excludes_from_future(sqlite_repo):
    """Mark one asked, verify it is not returned again."""
    questions = [
        {"id": "q1", "question_text": "Q1", "correct_answer": "a1", "category": "x"},
        {"id": "q2", "question_text": "Q2", "correct_answer": "a2", "category": "x"},
    ]
    sqlite_repo.seed_questions(questions)

    q1 = sqlite_repo.get_random_question()
    assert q1 is not None
    asked_id = q1["id"]
    sqlite_repo.mark_question_asked(asked_id)

    for _ in range(10):
        q = sqlite_repo.get_random_question()
        if q is None:
            break
        assert q["id"] != asked_id, "Previously asked question should not be returned"


def test_all_questions_exhausted_returns_none(sqlite_repo):
    """Ask all questions, verify None returned."""
    questions = [
        {"id": "q1", "question_text": "Q1", "correct_answer": "a1", "category": "x"},
    ]
    sqlite_repo.seed_questions(questions)

    q = sqlite_repo.get_random_question()
    assert q is not None
    sqlite_repo.mark_question_asked(q["id"])

    assert sqlite_repo.get_random_question() is None


def test_reset_questions(sqlite_repo):
    """Reset, verify previously asked questions are available again."""
    questions = [
        {"id": "q1", "question_text": "Q1", "correct_answer": "a1", "category": "x"},
    ]
    sqlite_repo.seed_questions(questions)

    q = sqlite_repo.get_random_question()
    assert q is not None
    sqlite_repo.mark_question_asked(q["id"])
    assert sqlite_repo.get_random_question() is None

    sqlite_repo.reset_questions()
    q2 = sqlite_repo.get_random_question()
    assert q2 is not None
    assert q2["id"] == "q1"
