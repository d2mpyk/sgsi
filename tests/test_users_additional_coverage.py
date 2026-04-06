import os
import uuid
import asyncio
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from models.users import User
from utils.auth import hash_password
from routers import users as users_router


def _login_admin(client, db_session, username: str = "admin.extra", email: str = "admin.extra@example.com"):
    password = "AdminPass123!"
    admin = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return admin


def test_get_users_clears_flash_cookies(client, db_session):
    _login_admin(client, db_session, username="admin.flash", email="admin.flash@example.com")
    client.cookies.set("flash_message", "ok")
    client.cookies.set("flash_type", "green")

    response = client.get("/api/v1/users")
    assert response.status_code == 200
    set_cookie_header = ", ".join(response.headers.get_list("set-cookie"))
    assert "flash_message=" in set_cookie_header
    assert "flash_type=" in set_cookie_header


def test_export_security_logs_handles_nonformatted_lines(client, db_session):
    _login_admin(client, db_session, username="admin.logs", email="admin.logs@example.com")

    log_file = "security.log"
    with open(log_file, "w", encoding="utf-8") as file:
        file.write("linea sin formato\n")
        file.write("2026-01-01 10:00:00,000 - INFO - logger - mensaje\n")

    try:
        response = client.get("/api/v1/users/admin/logs/export?limit=1")
        assert response.status_code == 200
        content = response.text
        assert "Timestamp,Level,Logger,Message,Raw Line" in content
        assert "linea sin formato" in content or "mensaje" in content
    finally:
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except PermissionError:
                pass


def test_create_user_returns_redirect_error_when_department_is_invalid(client, db_session):
    _login_admin(client, db_session, username="admin.create.user", email="admin.create.user@example.com")

    random_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/users/create",
        data={
            "username": f"user_{uuid.uuid4().hex[:6]}",
            "email": random_email,
            "password": "UserPass123!",
            "department_id": 999999,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db_session.query(User).filter(User.email == random_email).first() is None


def test_get_approved_users_returns_not_found_when_empty(client, db_session):
    _login_admin(client, db_session, username="admin.approved.empty", email="admin.approved.empty@example.com")

    response = client.get("/api/v1/users/approved")
    assert response.status_code == 404
    assert response.json()["detail"] == "No hay usuarios que mostrar"


def test_update_user_partial_validates_duplicate_username(client, db_session):
    admin = _login_admin(client, db_session, username="admin.partial", email="admin.partial@example.com")
    other = User(
        username="existing.user",
        email="existing.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    target = User(
        username="target.user",
        email="target.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add_all([other, target])
    db_session.commit()

    response = client.patch(
        f"/api/v1/users/{target.id}",
        json={"username": other.username},
    )
    assert response.status_code == 400
    assert "nombre de usuario" in response.json()["detail"].lower()

    # sanity: admin exists and route was authenticated
    assert admin.id is not None


def test_delete_user_handles_not_found_and_self_delete(client, db_session):
    admin = _login_admin(client, db_session, username="admin.delete.coverage", email="admin.delete.coverage@example.com")

    not_found = client.delete("/api/v1/users/999999")
    assert not_found.status_code == 404

    self_delete = client.delete(f"/api/v1/users/{admin.id}")
    assert self_delete.status_code == 406


def test_users_router_direct_redirect_branches(db_session):
    redirect = RedirectResponse(url="/login", status_code=303)

    assert users_router.get_current_user_endpoint(redirect) is redirect

    payload = users_router.UserPasswordUpdate(
        current_password="x",
        new_password="Password123!",
    )
    assert users_router.update_current_user_password(payload, redirect, db_session) is redirect

    assert users_router.get_approved_users(db_session, redirect) is redirect
    assert users_router.create_approved_user("user@example.com", db_session, redirect) is redirect
    assert users_router.get_user(1, db_session, redirect) is redirect
    assert users_router.update_user_role(
        1,
        MagicMock(client=MagicMock(host="127.0.0.1")),
        users_router.UserRoleUpdate(role="user"),
        db_session,
        redirect,
    ) is redirect
    assert users_router.update_user_partial(
        1,
        users_router.UserUpdate(),
        db_session,
        redirect,
    ) is redirect
    assert users_router.delete_user(
        MagicMock(client=MagicMock(host="127.0.0.1")),
        1,
        db_session,
        redirect,
    ) is redirect
    assert users_router.view_security_logs(
        MagicMock(),
        db_session,
        redirect,
    ) is redirect
    assert users_router.export_security_logs(db_session, redirect) is redirect

    async_result = asyncio.run(
        users_router.update_current_user_profile(
            redirect,
            db_session,
            username="x",
            image_file=None,
        )
    )
    assert async_result is redirect

    async_edit_result = asyncio.run(
        users_router.post_user_edit_view(
            MagicMock(client=MagicMock(host="127.0.0.1"), url_for=lambda *args, **kwargs: "/x"),
            1,
            db_session,
            redirect,
            username="x",
            role=None,
            department_id=None,
            is_active=None,
            password=None,
        )
    )
    assert async_edit_result is redirect


def test_users_router_profile_image_size_validation_branch(client, db_session):
    password = "UserPass123!"
    user = User(
        username="oversize.user",
        email="oversize.user@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": user.username, "password": password},
    )
    assert login.status_code == 200

    oversized_content = b"a" * (2 * 1024 * 1024 + 1)
    response = client.patch(
        "/api/v1/users/me",
        files={"image_file": ("oversize.png", oversized_content, "image/png")},
    )
    assert response.status_code == 400
    assert "demasiado grande" in response.json()["detail"].lower()


def test_users_router_reset_password_user_not_found_branch(client, monkeypatch):
    monkeypatch.setattr(users_router, "verify_reset_password_token", lambda _: "ghost@example.com")

    response = client.post(
        "/api/v1/users/reset-password/token123",
        data={"new_password": "Password123!", "confirm_password": "Password123!"},
    )
    assert response.status_code == 404


def test_users_router_security_logs_error_branch(client, db_session):
    _login_admin(client, db_session, username="admin.logs.error", email="admin.logs.error@example.com")

    with patch("routers.users.open", side_effect=OSError("read-error")):
        with patch("routers.users.os.path.exists", return_value=True):
            response = client.get("/api/v1/users/admin/logs")
            assert response.status_code == 200


def test_users_router_get_user_edit_and_post_edit_edge_branches(client, db_session):
    admin = _login_admin(client, db_session, username="admin.edit.edges", email="admin.edit.edges@example.com")
    user = User(
        username="target.edit.edges",
        email="target.edit.edges@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    not_found_get = client.get("/api/v1/users/999999/edit")
    assert not_found_get.status_code == 404

    not_found_post = client.post(
        "/api/v1/users/999999/edit",
        data={"username": "anything"},
    )
    assert not_found_post.status_code == 404

    invalid_role_post = client.post(
        f"/api/v1/users/{user.id}/edit",
        data={"role": "invalid-role"},
        follow_redirects=False,
    )
    assert invalid_role_post.status_code == 303

    unauthorized_user = User(
        username="unauthorized.editor",
        email="unauthorized.editor@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add(unauthorized_user)
    db_session.commit()

    client.post(
        "/api/v1/auth/logout",
        follow_redirects=False,
    )
    login_user = client.post(
        "/api/v1/auth/token",
        data={"username": unauthorized_user.username, "password": "UserPass123!"},
    )
    assert login_user.status_code == 200

    unauthorized_post = client.post(
        f"/api/v1/users/{admin.id}/edit",
        data={"username": "hacker"},
    )
    assert unauthorized_post.status_code == 403


def test_users_router_create_user_duplicate_validation_branch(client, db_session):
    admin = _login_admin(client, db_session, username="admin.create.dup", email="admin.create.dup@example.com")
    existing = User(
        username="already.used",
        email="already.used@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add(existing)
    db_session.commit()

    response = client.post(
        "/api/v1/users/create",
        data={
            "username": existing.username,
            "email": f"new_{uuid.uuid4().hex[:6]}@example.com",
            "password": "UserPass123!",
            "department_id": 1,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # use admin variable to avoid lint-style unused warning in strict runners
    assert admin.id is not None
