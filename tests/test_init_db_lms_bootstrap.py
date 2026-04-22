from pathlib import Path
import uuid
from types import SimpleNamespace

import pytest

from models.lms import LMSPost
from utils import init_db, lms_seed


class DummySession:
    def __init__(self):
        self.closed = False
        self.committed = False

    def close(self):
        self.closed = True


class DummyDB:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_lms_seed_catalog_db_and_slugify_idempotent(db_session):
    assert lms_seed._slugify("CONCIENTIZACIÓN EN SEGURIDAD (A.6.3)") == "concientizacion-en-seguridad-a63"

    first = lms_seed.seed_lms_catalog_db(db_session)
    second = lms_seed.seed_lms_catalog_db(db_session)

    assert first == len(lms_seed.TOPICS)
    assert second == 0
    assert db_session.query(LMSPost).count() == len(lms_seed.TOPICS)


def test_lms_seed_catalog_wrapper_uses_session_local(monkeypatch):
    fake_db = DummySession()
    called = {"seeded": False}

    def fake_seed(db):
        called["seeded"] = True
        assert db is fake_db
        return 1

    monkeypatch.setattr(lms_seed, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(lms_seed, "seed_lms_catalog_db", fake_seed)

    lms_seed.seed_lms_catalog()

    assert called["seeded"] is True
    assert fake_db.closed is True


def test_load_bootstrap_payload_happy_and_missing(monkeypatch):
    payload_file = Path(".") / f"tmp_lms_bootstrap_{uuid.uuid4().hex}.json"
    payload_file.write_text('{"posts": [], "themes": [], "quizzes": []}', encoding="utf-8")
    monkeypatch.setattr(init_db, "LMS_BOOTSTRAP_DATA_PATH", payload_file)

    payload = init_db._load_lms_bootstrap_payload()
    assert payload["posts"] == []

    missing_path = Path(".") / f"tmp_missing_{uuid.uuid4().hex}.json"
    monkeypatch.setattr(init_db, "LMS_BOOTSTRAP_DATA_PATH", missing_path)
    with pytest.raises(RuntimeError):
        init_db._load_lms_bootstrap_payload()

    if payload_file.exists():
        payload_file.unlink()


def test_seed_lms_posts_themes_and_quizzes(db_session, monkeypatch):
    payload = {
        "posts": [
            {
                "title": "Tema A",
                "slug": "tema-a",
                "category": "Capacitación SGSI",
                "version": "1.0",
                "status": "published",
                "html_content": "",
                "porcentaje_aprobacion": 80,
                "max_intentos": 3,
            }
        ],
        "themes": [],
        "quizzes": [
            {
                "post_slug": "tema-a",
                "title": "Quiz A",
                "instructions": "",
                "version": "1.0",
                "is_active": True,
                "questions": [
                    {
                        "question_order": 1,
                        "statement": "Pregunta",
                        "options": [
                            {"option_order": 1, "option_text": "Correcta", "is_correct": True},
                            {"option_order": 2, "option_text": "Incorrecta", "is_correct": False},
                        ],
                    }
                ],
            },
            {
                "post_slug": "missing-slug",
                "title": "Quiz missing",
                "questions": [],
            },
        ],
    }

    init_db._ensure_lms_themes_table(db_session)
    init_db._seed_lms_posts(db_session, payload)
    assert db_session.query(LMSPost).filter(LMSPost.slug == "tema-a").first() is not None

    init_db._seed_lms_themes(db_session, payload)
    themes_qty = init_db._count_rows(db_session, "lms_themes")
    assert themes_qty >= 1

    calls = {"count": 0}

    def fake_upsert_quiz(**kwargs):
        calls["count"] += 1
        assert kwargs["post_id"] > 0

    monkeypatch.setattr(init_db.lms_service, "upsert_quiz", fake_upsert_quiz)
    init_db._seed_lms_quizzes(db_session, payload)
    assert calls["count"] == 1


def test_ensure_lms_required_tables_exist_raises_when_tables_still_missing(monkeypatch):
    class FakeInspector:
        def get_table_names(self):
            return []

    fake_db = SimpleNamespace(bind=object())

    monkeypatch.setattr(init_db, "inspect", lambda _bind: FakeInspector())
    monkeypatch.setattr(init_db.Base.metadata, "create_all", lambda bind: None)

    with pytest.raises(RuntimeError):
        init_db._ensure_lms_required_tables_exist(fake_db)


def test_ensure_lms_bootstrap_data_success_and_failure_paths(monkeypatch):
    fake_db = DummyDB()
    called = {
        "themes": 0,
        "tables": 0,
        "load": 0,
        "posts": 0,
        "themes_seed": 0,
        "quizzes": 0,
    }

    monkeypatch.setattr(init_db, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(init_db, "_ensure_lms_themes_table", lambda db: called.__setitem__("themes", called["themes"] + 1))
    monkeypatch.setattr(init_db, "_ensure_lms_required_tables_exist", lambda db: called.__setitem__("tables", called["tables"] + 1))
    monkeypatch.setattr(
        init_db,
        "_get_lms_table_counts",
        lambda db: {
            "lms_posts": 0,
            "lms_quizzes": 0,
            "lms_quiz_questions": 0,
            "lms_quiz_options": 0,
            "lms_themes": 0,
        },
    )
    monkeypatch.setattr(init_db, "_load_lms_bootstrap_payload", lambda: called.__setitem__("load", called["load"] + 1) or {"posts": [], "themes": [], "quizzes": []})
    monkeypatch.setattr(init_db, "_seed_lms_posts", lambda db, payload: called.__setitem__("posts", called["posts"] + 1))
    monkeypatch.setattr(init_db, "_seed_lms_themes", lambda db, payload: called.__setitem__("themes_seed", called["themes_seed"] + 1))
    monkeypatch.setattr(init_db, "_seed_lms_quizzes", lambda db, payload: called.__setitem__("quizzes", called["quizzes"] + 1))
    monkeypatch.setattr(init_db, "_count_rows", lambda db, table_name: 1)

    init_db.ensure_lms_bootstrap_data()
    assert called["themes"] == 1
    assert called["tables"] == 1
    assert called["load"] == 1
    assert called["posts"] == 1
    assert called["themes_seed"] == 1
    assert called["quizzes"] == 1
    assert fake_db.closed is True

    bad_db = DummyDB()
    monkeypatch.setattr(init_db, "SessionLocal", lambda: bad_db)
    monkeypatch.setattr(init_db, "_ensure_lms_themes_table", lambda db: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(SystemExit):
        init_db.ensure_lms_bootstrap_data()
    assert bad_db.closed is True
