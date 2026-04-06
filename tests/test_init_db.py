import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models.departments import Department
from models.iso_controls import ISOControl
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


def test_get_init_config_exits_when_admin_or_name_missing(monkeypatch):
    monkeypatch.setattr(init_db, "settings", build_settings(ADMIN="", NAME=""))

    with pytest.raises(SystemExit):
        init_db.get_init_config()


def test_get_init_config_exits_when_email_settings_are_missing(monkeypatch):
    monkeypatch.setattr(init_db, "settings", build_settings(EMAIL_SERVER="", EMAIL_PORT=""))

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


def test_parse_iso_controls_file_extracts_the_93_controls_with_iso_themes():
    controls_text = """
controls = {
"A.5 Controles Organizacionales":[
"A.5.1 Políticas de seguridad",
"A.5.2 Roles y responsabilidades"
],
"A.6 Controles de Personas":[
"A.6.8 Reporte eventos"
],
"A.7 Controles Físicos":[
"A.7.1 Perímetros seguridad"
],
"A.8 Controles Tecnológicos":[
"A.8.4 Código fuente"
]
}
""".strip()
    source_file = os.path.join(os.getcwd(), f"tmp_controls_{uuid.uuid4().hex}.txt")
    try:
        with open(source_file, "w", encoding="utf-8") as file:
            file.write(controls_text)
        result = init_db.parse_iso_controls_file(source_file)
    finally:
        if os.path.exists(source_file):
            os.remove(source_file)

    assert result == [
        {"tema": "Organizacionales", "control": "A.5.1", "nombre": "Políticas de seguridad"},
        {"tema": "Organizacionales", "control": "A.5.2", "nombre": "Roles y responsabilidades"},
        {"tema": "Personas", "control": "A.6.8", "nombre": "Reporte eventos"},
        {"tema": "Físicos", "control": "A.7.1", "nombre": "Perímetros seguridad"},
        {"tema": "Tecnológicos", "control": "A.8.4", "nombre": "Código fuente"},
    ]


def test_seed_iso_controls_creates_and_updates_catalog_idempotently(db_session):
    controls_text = """
controls = {
"A.5 Controles Organizacionales":[
"A.5.1 Políticas de seguridad"
],
"A.8 Controles Tecnológicos":[
"A.8.4 Código fuente"
]
}
""".strip()
    source_file = os.path.join(os.getcwd(), f"tmp_controls_{uuid.uuid4().hex}.txt")
    try:
        with open(source_file, "w", encoding="utf-8") as file:
            file.write(controls_text)

        total = init_db.seed_iso_controls(db_session, controls_file=source_file)
        assert total == 2
        assert db_session.query(ISOControl).count() == 2

        # Ejecutar de nuevo no debe duplicar registros.
        total_second = init_db.seed_iso_controls(db_session, controls_file=source_file)
        assert total_second == 2
        assert db_session.query(ISOControl).count() == 2

        # Cambiar nombre de un control debe actualizar el catálogo.
        with open(source_file, "w", encoding="utf-8") as file:
            file.write(
                """
controls = {
"A.5 Controles Organizacionales":[
"A.5.1 Políticas y lineamientos de seguridad"
],
"A.8 Controles Tecnológicos":[
"A.8.4 Código fuente"
]
}
""".strip()
            )
        init_db.seed_iso_controls(db_session, controls_file=source_file)
        updated = db_session.query(ISOControl).filter(ISOControl.control == "A.5.1").first()
        assert updated is not None
        assert updated.nombre == "Políticas y lineamientos de seguridad"
    finally:
        if os.path.exists(source_file):
            os.remove(source_file)


def test_seed_iso_controls_raises_when_no_valid_controls_found(db_session):
    invalid_file = os.path.join(os.getcwd(), f"tmp_invalid_controls_{uuid.uuid4().hex}.txt")
    try:
        with open(invalid_file, "w", encoding="utf-8") as file:
            file.write("contenido sin controles válidos")
        with pytest.raises(RuntimeError):
            init_db.seed_iso_controls(db_session, controls_file=invalid_file)
    finally:
        if os.path.exists(invalid_file):
            os.remove(invalid_file)


def test_init_iso_controls_exits_on_unexpected_error(monkeypatch, db_session):
    monkeypatch.setattr(init_db, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(init_db, "seed_iso_controls", MagicMock(side_effect=RuntimeError("boom")))

    with pytest.raises(SystemExit):
        init_db.init_iso_controls()
