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

