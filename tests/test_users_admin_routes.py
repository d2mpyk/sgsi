from unittest.mock import mock_open, patch

from models.users import User
from utils.auth import hash_password


def test_admin_cannot_delete_own_account(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="self.admin",
        email="self.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "self.admin", "password": admin_pass},
    )
    assert login_response.status_code == 200

    response = client.delete(f"/api/v1/users/{admin.id}")

    assert response.status_code == 406
    assert response.json()["detail"] == "Este usuario no puede eliminarse a si mismo."


def test_admin_can_delete_another_user(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="delete.admin",
        email="delete.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    target_user = User(
        username="deletable.user",
        email="deletable.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add_all([admin, target_user])
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "delete.admin", "password": admin_pass},
    )
    assert login_response.status_code == 200

    response = client.delete(f"/api/v1/users/{target_user.id}")

    assert response.status_code == 204
    assert db_session.get(User, target_user.id) is None


def test_admin_can_export_security_logs_filtered_as_csv(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="logs.admin",
        email="logs.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "logs.admin", "password": admin_pass},
    )
    assert login_response.status_code == 200

    fake_log_content = (
        "2026-03-28 10:00:00,000 - INFO - security - LOGIN OK\n"
        "2026-03-28 11:00:00,000 - WARNING - security - TOKEN INVALIDO\n"
    )
    with patch("routers.users.os.path.exists", return_value=True), patch(
        "routers.users.open", mock_open(read_data=fake_log_content)
    ):
        response = client.get("/api/v1/users/admin/logs/export?q=TOKEN&limit=10")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Content-Disposition" in response.headers
    assert "TOKEN INVALIDO" in response.text
    assert "LOGIN OK" not in response.text
