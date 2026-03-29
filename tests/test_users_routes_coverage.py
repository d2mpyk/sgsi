from unittest.mock import mock_open, patch
from urllib.parse import unquote

from models.departments import Department
from models.users import ApprovedUsers, User
from utils.auth import (
    generate_verification_token,
    hash_password,
    verify_password,
)


def get_department_id(db_session, name: str = "Infraestructura") -> int:
    department = (
        db_session.query(Department)
        .filter(Department.departamento == name)
        .first()
    )
    assert department is not None
    return department.id


def decode_cookie_text(value: str) -> str:
    return unquote(value).encode("latin-1", "backslashreplace").decode("unicode_escape")


def login_as_admin(client, username: str, password: str):
    response = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response


def test_get_current_user_endpoint_returns_authenticated_user(client, db_session):
    password = "UserPass123!"
    user = User(
        username="me.user",
        email="me.user@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "me.user", "password": password},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["username"] == "me.user"
    assert response.json()["department_name"] == "Infraestructura"


def test_update_current_user_password_rejects_incorrect_current_password(client, db_session):
    password = "UserPass123!"
    user = User(
        username="pwd.user",
        email="pwd.user@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()

    client.post(
        "/api/v1/auth/token",
        data={"username": "pwd.user", "password": password},
    )

    response = client.patch(
        "/api/v1/users/me/password",
        json={
            "current_password": "WrongPassword123!",
            "new_password": "NewPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "La contraseña actual es incorrecta."


def test_forgot_password_view_renders_flash_message_and_clears_flash_cookies(client):
    client.cookies.set("flash_message", "Correo enviado")
    client.cookies.set("flash_type", "green")

    response = client.get("/api/v1/users/forgot-password")

    assert response.status_code == 200
    assert "Correo enviado" in response.text
    delete_headers = response.headers.get_list("set-cookie")
    assert any("flash_message=\"\"" in value for value in delete_headers)
    assert any("flash_type=\"\"" in value for value in delete_headers)


def test_reset_password_returns_error_when_passwords_do_not_match(client):
    response = client.post(
        "/api/v1/users/reset-password/invalid-token",
        data={"new_password": "NewPassword123!", "confirm_password": "DistinctPassword123!"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/api/v1/users/reset-password/invalid-token")
    flash_messages = response.headers.get_list("set-cookie")
    assert any("Las contraseñas no coinciden." in decode_cookie_text(value) for value in flash_messages)


def test_reset_password_returns_error_when_password_is_too_short(client):
    response = client.post(
        "/api/v1/users/reset-password/invalid-token",
        data={"new_password": "short", "confirm_password": "short"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/api/v1/users/reset-password/invalid-token")
    flash_messages = response.headers.get_list("set-cookie")
    assert any(
        "La contraseña debe tener al menos 8 caracteres." in decode_cookie_text(value)
        for value in flash_messages
    )


def test_reset_password_redirects_to_login_when_token_is_invalid(client):
    response = client.post(
        "/api/v1/users/reset-password/invalid-token",
        data={"new_password": "ValidPass123!", "confirm_password": "ValidPass123!"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/api/v1/auth/login")
    flash_messages = response.headers.get_list("set-cookie")
    assert any(
        "El enlace para restablecer la contraseña es inválido o ha expirado."
        in decode_cookie_text(value)
        for value in flash_messages
    )


def test_get_users_admin_view_renders_departments(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="users.admin",
        email="users.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session, "Dirección Ejecutiva"),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "users.admin", admin_pass)

    response = client.get("/api/v1/users")

    assert response.status_code == 200
    assert "Gestión de Usuarios" in response.text
    assert "Infraestructura" in response.text
    assert "Dirección Ejecutiva" in response.text


def test_get_approved_users_returns_404_when_empty(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="approved.empty.admin",
        email="approved.empty.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "approved.empty.admin", admin_pass)

    response = client.get("/api/v1/users/approved")

    assert response.status_code == 404
    assert response.json()["detail"] == "No hay usuarios que mostrar"


def test_get_approved_users_returns_existing_records(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="approved.list.admin",
        email="approved.list.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    approved = ApprovedUsers(email="approved.user@example.com")
    db_session.add_all([admin, approved])
    db_session.commit()

    login_as_admin(client, "approved.list.admin", admin_pass)

    response = client.get("/api/v1/users/approved")

    assert response.status_code == 200
    assert response.json()[0]["email"] == "approved.user@example.com"


def test_create_approved_user_rejects_already_approved_email(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="approved.dup.admin",
        email="approved.dup.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    approved = ApprovedUsers(email="dup@example.com")
    db_session.add_all([admin, approved])
    db_session.commit()

    login_as_admin(client, "approved.dup.admin", admin_pass)

    response = client.post("/api/v1/users/approved/dup@example.com")

    assert response.status_code == 400
    assert response.json()["detail"] == "Este usuario ya ha sido aprobado."


def test_create_approved_user_rejects_registered_email(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="approved.registered.admin",
        email="approved.registered.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    existing_user = User(
        username="existing.registered",
        email="registered@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add_all([admin, existing_user])
    db_session.commit()

    login_as_admin(client, "approved.registered.admin", admin_pass)

    response = client.post("/api/v1/users/approved/registered@example.com")

    assert response.status_code == 400
    assert response.json()["detail"] == "Este email ya está registrado."


def test_post_user_edit_view_rejects_invalid_department(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="edit.invalid.department.admin",
        email="edit.invalid.department.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    target_user = User(
        username="target.invalid.department",
        email="target.invalid.department@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add_all([admin, target_user])
    db_session.commit()

    login_as_admin(client, "edit.invalid.department.admin", admin_pass)

    response = client.post(
        f"/api/v1/users/{target_user.id}/edit",
        data={
            "username": "target.invalid.department",
            "role": "user",
            "department_id": "9999",
            "is_active": "on",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/api/v1/users/{target_user.id}/edit")
    flash_messages = [
        decode_cookie_text(cookie.value).strip('"')
        for cookie in client.cookies.jar
        if cookie.name == "flash_message"
    ]
    assert any("Debe seleccionar un departamento válido." in message for message in flash_messages)


def test_post_user_edit_view_blocks_admin_self_deactivation(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="edit.self.admin",
        email="edit.self.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "edit.self.admin", admin_pass)

    response = client.post(
        f"/api/v1/users/{admin.id}/edit",
        data={
            "username": "edit.self.admin",
            "role": "admin",
            "department_id": str(admin.department_id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/api/v1/users/{admin.id}/edit")
    db_session.refresh(admin)
    assert admin.is_active is True


def test_post_user_edit_view_updates_user_password_for_admin(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="edit.password.admin",
        email="edit.password.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    target_user = User(
        username="target.password.user",
        email="target.password.user@example.com",
        password_hash=hash_password("OldPassword123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add_all([admin, target_user])
    db_session.commit()

    login_as_admin(client, "edit.password.admin", admin_pass)

    response = client.post(
        f"/api/v1/users/{target_user.id}/edit",
        data={
            "username": target_user.username,
            "role": "user",
            "department_id": str(target_user.department_id),
            "is_active": "on",
            "password": "UpdatedPassword123!",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/api/v1/users")
    db_session.refresh(target_user)
    assert verify_password("UpdatedPassword123!", target_user.password_hash) is True


def test_post_user_edit_view_rejects_short_password(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="edit.short.password.admin",
        email="edit.short.password.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    target_user = User(
        username="target.short.password",
        email="target.short.password@example.com",
        password_hash=hash_password("OldPassword123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add_all([admin, target_user])
    db_session.commit()

    login_as_admin(client, "edit.short.password.admin", admin_pass)

    response = client.post(
        f"/api/v1/users/{target_user.id}/edit",
        data={
            "username": target_user.username,
            "role": "user",
            "department_id": str(target_user.department_id),
            "is_active": "on",
            "password": "short",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/api/v1/users/{target_user.id}/edit")
    flash_messages = response.headers.get_list("set-cookie")
    assert any(
        "La contraseña debe tener al menos 8 caracteres." in decode_cookie_text(value)
        for value in flash_messages
    )


def test_verify_user_email_returns_blue_when_account_is_already_active(client, db_session):
    user = User(
        username="already.active",
        email="already.active@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()

    token = generate_verification_token(user.email)

    response = client.get(f"/api/v1/users/verify/{token}", follow_redirects=False)

    assert response.status_code == 303
    flash_messages = response.headers.get_list("set-cookie")
    assert any("La cuenta ya estaba verificada." in value for value in flash_messages)


def test_verify_user_email_returns_error_when_token_belongs_to_missing_user(client):
    token = generate_verification_token("missing.user@example.com")

    response = client.get(f"/api/v1/users/verify/{token}", follow_redirects=False)

    assert response.status_code == 303
    flash_messages = response.headers.get_list("set-cookie")
    assert any("Usuario no encontrado" in value for value in flash_messages)


def test_resend_verification_email_returns_generic_message_for_unknown_email(client):
    response = client.post(
        "/api/v1/users/resend-verification",
        data={"email": "unknown@example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    flash_messages = response.headers.get_list("set-cookie")
    assert any(
        "Si el correo está registrado, se enviará un enlace de verificación." in decode_cookie_text(value)
        for value in flash_messages
    )


def test_resend_verification_email_returns_blue_for_active_user(client, db_session):
    user = User(
        username="active.resend",
        email="active.resend@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/v1/users/resend-verification",
        data={"email": user.email},
        follow_redirects=False,
    )

    assert response.status_code == 303
    flash_messages = response.headers.get_list("set-cookie")
    assert any(
        "Esta cuenta ya está activa. Por favor inicie sesión." in decode_cookie_text(value)
        for value in flash_messages
    )


def test_resend_verification_email_sends_for_inactive_user(client, db_session):
    user = User(
        username="inactive.resend",
        email="inactive.resend@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=False,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()

    with patch("routers.users.send_email_confirmation") as mock_email:
        response = client.post(
            "/api/v1/users/resend-verification",
            data={"email": user.email},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert mock_email.called


def test_resend_verification_view_renders_flash_message_and_clears_flash_cookies(client):
    client.cookies.set("flash_message", "Reenvio listo")
    client.cookies.set("flash_type", "blue")

    response = client.get("/api/v1/users/resend-verification")

    assert response.status_code == 200
    assert "Reenvio listo" in response.text
    delete_headers = response.headers.get_list("set-cookie")
    assert any("flash_message=\"\"" in value for value in delete_headers)
    assert any("flash_type=\"\"" in value for value in delete_headers)


def test_update_user_role_rejects_admin_self_role_change(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="role.self.admin",
        email="role.self.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "role.self.admin", admin_pass)

    response = client.patch(
        f"/api/v1/users/{admin.id}/role",
        json={"role": "user"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Un administrador no puede cambiar su propio rol."


def test_update_user_partial_rejects_duplicate_email(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="partial.admin",
        email="partial.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    user_one = User(
        username="partial.one",
        email="partial.one@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    user_two = User(
        username="partial.two",
        email="partial.two@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add_all([admin, user_one, user_two])
    db_session.commit()

    login_as_admin(client, "partial.admin", admin_pass)

    response = client.patch(
        f"/api/v1/users/{user_two.id}",
        json={"email": user_one.email},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Este Email ya está registrado."


def test_get_user_returns_404_when_user_does_not_exist(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="get.missing.admin",
        email="get.missing.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "get.missing.admin", admin_pass)

    response = client.get("/api/v1/users/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Este usuario no existe"


def test_update_user_role_returns_404_when_target_user_does_not_exist(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="role.missing.admin",
        email="role.missing.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "role.missing.admin", admin_pass)

    response = client.patch(
        "/api/v1/users/9999/role",
        json={"role": "user"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Este usuario no existe"


def test_update_user_partial_returns_404_when_target_user_does_not_exist(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="partial.missing.admin",
        email="partial.missing.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "partial.missing.admin", admin_pass)

    response = client.patch(
        "/api/v1/users/9999",
        json={"username": "new.name"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Este usuario no existe"


def test_view_security_logs_renders_filtered_html(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="view.logs.admin",
        email="view.logs.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(admin)
    db_session.commit()

    login_as_admin(client, "view.logs.admin", admin_pass)

    fake_log_content = (
        "2026-03-28 10:00:00,000 - INFO - security - LOGIN OK\n"
        "2026-03-28 11:00:00,000 - WARNING - security - TOKEN INVALIDO\n"
    )
    with patch("routers.users.os.path.exists", return_value=True), patch(
        "routers.users.open", mock_open(read_data=fake_log_content)
    ):
        response = client.get("/api/v1/users/admin/logs?q=TOKEN&limit=10")

    assert response.status_code == 200
    assert "Auditoría de Seguridad" in response.text
    assert "TOKEN INVALIDO" in response.text
    assert "LOGIN OK" not in response.text
