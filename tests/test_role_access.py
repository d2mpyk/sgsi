from models.users import User
from utils.auth import hash_password


def test_non_admin_cannot_access_users_list(client, db_session):
    """
    Valida que un usuario con rol 'user' (no admin) reciba un error 403
    al intentar acceder a la ruta '/api/v1/users', que es exclusiva de administradores.
    """
    # 1. Configuración: Crear usuario estándar
    password = "UserPass123!"
    user = User(
        username="standard_user",
        email="user@test.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # 2. Autenticación (Login)
    login_response = client.post(
        "/api/v1/auth/token", data={"username": "standard_user", "password": password}
    )
    assert login_response.status_code == 200

    # 3. Intento de acceso a recurso protegido (Admin Only)
    # Al no ser admin, el dependency get_current_admin debe levantar una excepción
    response = client.get("/api/v1/users")

    # 4. Verificaciones
    assert response.status_code == 403
    # Verificamos también que el mensaje sea el esperado según utils/auth.py
    assert response.json()["detail"] == "Acceso denegado"


def test_non_admin_can_view_own_dummy_profile_form(client, db_session):
    password = "UserPass123!"
    user = User(
        username="self_user",
        email="self_user@test.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token", data={"username": "self_user", "password": password}
    )
    assert login_response.status_code == 200

    response = client.get(f"/api/v1/users/{user.id}/edit")

    assert response.status_code == 200
    assert "Mi información de usuario" in response.text
    assert "Este formulario es informativo" in response.text
    assert "self_user@test.com" in response.text


def test_non_admin_cannot_view_another_user_profile(client, db_session):
    password = "UserPass123!"
    owner = User(
        username="owner_user",
        email="owner_user@test.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    other = User(
        username="other_user",
        email="other_user@test.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add_all([owner, other])
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token", data={"username": "owner_user", "password": password}
    )
    assert login_response.status_code == 200

    response = client.get(f"/api/v1/users/{other.id}/edit")

    assert response.status_code == 403
    assert response.json()["detail"] == "No tienes permiso para ver este perfil."
