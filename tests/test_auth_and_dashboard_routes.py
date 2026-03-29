from datetime import UTC, datetime

from models.departments import Department
from models.documents import Document, DocumentRead
from models.users import User
from utils.auth import hash_password


def get_department_id(db_session, name: str = "Infraestructura") -> int:
    department = (
        db_session.query(Department)
        .filter(Department.departamento == name)
        .first()
    )
    assert department is not None
    return department.id


def login_user(client, username: str, password: str):
    response = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response


def test_login_view_renders_flash_message_and_clears_flash_cookies(client):
    client.cookies.set("flash_message", "Sesion iniciada")
    client.cookies.set("flash_type", "green")

    response = client.get("/api/v1/auth/login")

    assert response.status_code == 200
    assert "Sesion iniciada" in response.text
    delete_headers = response.headers.get_list("set-cookie")
    assert any("flash_message=\"\"" in value for value in delete_headers)
    assert any("flash_type=\"\"" in value for value in delete_headers)


def test_login_token_sets_access_cookie_for_active_user(client, db_session):
    password = "AuthPass123!"
    user = User(
        username="auth.login",
        email="auth.login@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/token",
        data={"username": user.username, "password": password},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert any("access_token=" in value for value in response.headers.get_list("set-cookie"))


def test_logout_redirects_and_deletes_access_cookie(client):
    response = client.post("/api/v1/auth/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/api/v1/auth/login")
    assert "access_token=\"\"" in response.headers["set-cookie"]


def test_dashboard_lists_only_pending_active_policies(client, db_session):
    password = "DashboardPass123!"
    user = User(
        username="dashboard.user",
        email="dashboard.user@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    pending_policy = Document(
        title="Politica Pendiente",
        description="Pendiente",
        version="1.0",
        code="POL-001",
        doc_type="policy",
        filename="pending.pdf",
        content_type="application/pdf",
        uploaded_by_id=1,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    read_policy = Document(
        title="Politica Leida",
        description="Leida",
        version="1.0",
        code="POL-002",
        doc_type="policy",
        filename="read.pdf",
        content_type="application/pdf",
        uploaded_by_id=1,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    inactive_policy = Document(
        title="Politica Inactiva",
        description="Inactiva",
        version="1.0",
        code="POL-003",
        doc_type="policy",
        filename="inactive.pdf",
        content_type="application/pdf",
        uploaded_by_id=1,
        is_active=False,
        created_at=datetime.now(UTC),
    )
    db_session.add_all([user, pending_policy, read_policy, inactive_policy])
    db_session.commit()

    db_session.add(
        DocumentRead(
            user_id=user.id,
            document_id=read_policy.id,
            read_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    login_user(client, user.username, password)
    response = client.get("/api/v1/dashboard/")

    assert response.status_code == 200
    assert "Politica Pendiente" in response.text
    assert "Politica Leida" not in response.text
    assert "Politica Inactiva" not in response.text
