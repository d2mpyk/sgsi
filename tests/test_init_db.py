from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models.departments import Department
from models.users import ApprovedUsers, User
from utils import init_db


class SecretValue:
    def __init__(self, value: str):
        self.value = value

    def get_secret_value(self):
        return self.value


def build_settings(**overrides):
    defaults = {
        "SECRET_KEY": "secret-key",
        "SECRET_KEY_CHECK_MAIL": "secret-mail",
        "SECURITY_PASSWD_SALT": "salt",
        "ADMIN": "admin@example.com",
        "NAME": "admin",
        "EMAIL_SERVER": "smtp.example.com",
        "EMAIL_PORT": "465",
        "EMAIL_USER": "noreply@example.com",
        "EMAIL_PASSWD": "mail-password",
    }
    defaults.update(overrides)
    return SimpleNamespace(**{key: SecretValue(value) for key, value in defaults.items()})


def test_get_init_config_passes_with_complete_settings(monkeypatch):
    monkeypatch.setattr(init_db, "settings", build_settings())

    init_db.get_init_config()


def test_get_init_config_exits_when_security_settings_are_missing(monkeypatch):
    monkeypatch.setattr(init_db, "settings", build_settings(SECRET_KEY=""))

    with pytest.raises(SystemExit):
        init_db.get_init_config()


def test_seed_departments_creates_missing_catalog_and_returns_first_id(db_session):
    department_id = init_db.seed_departments(db_session)

    departments = db_session.query(Department).order_by(Department.id.asc()).all()
    assert department_id == departments[0].id
    assert [department.departamento for department in departments] == init_db.DEFAULT_DEPARTMENTS


def test_seed_departments_raises_when_catalog_cannot_be_initialized(db_session):
    class FakeOrderedQuery:
        def all(self):
            return []

    class FakeQuery:
        def all(self):
            return []

        def order_by(self, *args, **kwargs):
            return FakeOrderedQuery()

    fake_db = MagicMock()
    fake_db.query.return_value = FakeQuery()

    with pytest.raises(RuntimeError):
        init_db.seed_departments(fake_db)


def test_init_approved_users_creates_bootstrap_records(monkeypatch, db_session):
    monkeypatch.setattr(init_db, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(init_db, "settings", build_settings())
    monkeypatch.setattr(init_db, "hash_password", lambda _: "hashed-admin")
    monkeypatch.setattr(init_db, "seed_departments", lambda db: 1)

    init_db.init_approved_users()

    approved = db_session.query(ApprovedUsers).filter_by(email="admin@example.com").first()
    admin = db_session.query(User).filter_by(email="admin@example.com").first()
    assert approved is not None
    assert admin is not None
    assert admin.department_id == 1
    assert admin.password_hash == "hashed-admin"


def test_init_approved_users_exits_on_unexpected_error(monkeypatch, db_session):
    monkeypatch.setattr(init_db, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(init_db, "seed_departments", MagicMock(side_effect=RuntimeError("boom")))

    with pytest.raises(SystemExit):
        init_db.init_approved_users()


def test_ensure_document_reads_download_at_column_adds_missing_column(monkeypatch):
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["document_reads"]
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "user_id"}]

    executed = []

    class FakeConnection:
        def execute(self, statement):
            executed.append(str(statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(init_db, "inspect", lambda engine: inspector)
    monkeypatch.setattr(init_db.engine, "begin", lambda: FakeBegin())

    init_db.ensure_document_reads_download_at_column()

    assert any("ALTER TABLE document_reads ADD COLUMN download_at DATETIME" in sql for sql in executed)


def test_ensure_suggestions_table_creates_table_when_missing(monkeypatch):
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["users"]

    executed = []

    class FakeConnection:
        def execute(self, statement):
            executed.append(str(statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(init_db, "inspect", lambda engine: inspector)
    monkeypatch.setattr(init_db.engine, "begin", lambda: FakeBegin())

    init_db.ensure_suggestions_table()

    assert any("CREATE TABLE suggestions" in sql for sql in executed)


def test_ensure_users_department_column_adds_and_populates_column(monkeypatch):
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["users"]
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "email"}]

    executed = []

    class FakeConnection:
        def execute(self, statement, params=None):
            executed.append((str(statement), params))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSessionLocal:
        def __call__(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(init_db, "inspect", lambda engine: inspector)
    monkeypatch.setattr(init_db.engine, "begin", lambda: FakeBegin())
    monkeypatch.setattr(init_db, "SessionLocal", FakeSessionLocal())
    monkeypatch.setattr(init_db, "seed_departments", lambda db: 7)

    init_db.ensure_users_department_column()

    assert any("ALTER TABLE users ADD COLUMN department_id INTEGER" in sql for sql, _ in executed)
    assert any(
        "UPDATE users SET department_id = :department_id WHERE department_id IS NULL" in sql
        and params == {"department_id": 7}
        for sql, params in executed
    )
