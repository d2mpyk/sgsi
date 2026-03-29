from models.users import User
from utils.auth import hash_password, generate_reset_password_token


def test_full_password_recovery_flow(client, db_session):
    """
    Verifica el flujo completo:
    1. Crear usuario con contraseña antigua.
    2. Solicitar reset (POST /forgot-password).
    3. Validar token y vista (GET /reset-password).
    4. Cambiar contraseña (POST /reset-password).
    5. Login exitoso con nueva contraseña.
    6. Login fallido con contraseña antigua.
    """

    # --- 1. Preparación: Crear Usuario ---
    email = "victim@example.com"
    old_password = "OldPassword123!"
    new_password = "NewPasswordSecure!2024"

    user = User(
        username="victim",
        email=email,
        password_hash=hash_password(old_password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # --- 2. Solicitar Reset (Forgot Password) ---
    # Nota: El endpoint espera un modelo Pydantic, así que enviamos JSON
    response = client.post(
        "/api/v1/users/forgot-password", json={"email": email}, follow_redirects=False
    )
    # Debe redirigir (303) o retornar 200 según tu implementación,
    # en tu código actual es RedirectResponse (303)
    assert response.status_code == 303

    # --- 3. Obtener Token (Simulación de Email) ---
    # Como no podemos interceptar el email real en un test unitario fácilmente,
    # generamos el token usando la misma utilidad que usa el backend.
    token = generate_reset_password_token(email)

    # Verificar que la vista del formulario carga correctamente
    response = client.get(f"/api/v1/users/reset-password/{token}")
    assert response.status_code == 200
    assert "Restablecer Contraseña" in response.text

    # --- 4. Ejecutar Cambio de Contraseña ---
    # Este endpoint usa Form data
    response = client.post(
        f"/api/v1/users/reset-password/{token}",
        data={"new_password": new_password, "confirm_password": new_password},
        follow_redirects=False,
    )
    assert response.status_code == 303  # Redirige al login

    # --- 5. Verificar Login con NUEVA contraseña ---
    login_response = client.post(
        "/api/v1/auth/token", data={"username": "victim", "password": new_password}
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()

    # --- 6. Verificar Login con ANTIGUA contraseña (debe fallar) ---
    fail_response = client.post(
        "/api/v1/auth/token", data={"username": "victim", "password": old_password}
    )
    assert fail_response.status_code == 401
