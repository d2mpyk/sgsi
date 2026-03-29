from unittest.mock import patch
from models.departments import Department
from models.users import User, ApprovedUsers
from utils.auth import hash_password, generate_verification_token


def test_account_activation_flow(client, db_session):
    """
    Verifica el flujo completo de activación de cuenta:
    1. Setup: Crear Admin.
    2. Admin agrega email a ApprovedUsers (POST /approved).
    3. Admin crea el usuario (POST /create).
    4. Verificar que el usuario se crea inactivo (is_active=False).
    5. Simular click en enlace de correo (Generar token y GET /verify).
    6. Verificar que el usuario pasa a activo (is_active=True).
    7. Verificar Login exitoso.
    """

    # --- 1. Setup: Crear Admin y Loguearse ---
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin",
        email="admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    # Login para obtener cookies de sesión
    login_response = client.post(
        "/api/v1/auth/token", data={"username": "admin", "password": admin_pass}
    )
    assert login_response.status_code == 200
    # El cliente (TestClient) mantiene las cookies de sesión automáticamente

    # Datos del nuevo usuario
    new_email = "colaborador@example.com"
    new_user_pass = "SecurePass2024!"
    department = (
        db_session.query(Department)
        .filter(Department.departamento == "Infraestructura")
        .first()
    )
    assert department is not None

    # --- 2. Agregar a ApprovedUsers ---
    res_approve = client.post(f"/api/v1/users/approved/{new_email}")
    assert res_approve.status_code == 201
    assert res_approve.json()["email"] == new_email

    # --- 3. Crear Usuario (Mockeando el envío de email) ---
    with patch("routers.users.send_email_confirmation") as mock_email:
        res_create = client.post(
            "/api/v1/users/create",
            data={
                "username": "colaborador",
                "email": new_email,
                "password": new_user_pass,
                "department_id": str(department.id),
            },
            follow_redirects=False,
        )
        assert res_create.status_code == 303  # Redirección exitosa
        # Asegurar que se intentó enviar el correo (Background Task)
        # Nota: TestClient ejecuta background tasks sincrónicamente
        assert mock_email.called

    # --- 4. Verificar estado Inactivo ---
    # Usamos db_session inyectada
    user = db_session.query(User).filter(User.email == new_email).first()
    assert user is not None
    assert user.is_active is False  # Debe estar inactivo inicialmente
    assert user.department_id == department.id
    assert user.department_name == "Infraestructura"

    # --- 5. Activación (Simular verificación por token) ---
    # Generamos el token manualmente usando la misma lógica del backend
    token = generate_verification_token(new_email)

    res_verify = client.get(f"/api/v1/users/verify/{token}", follow_redirects=False)
    assert res_verify.status_code == 303  # Redirige al login tras éxito

    # --- 6. Verificar estado Activo ---
    user_active = db_session.query(User).filter(User.email == new_email).first()
    assert user_active.is_active is True

    # --- 7. Verificar Login del Nuevo Usuario ---
    res_login = client.post(
        "/api/v1/auth/token",
        data={"username": "colaborador", "password": new_user_pass},
    )
    assert res_login.status_code == 200
    assert "access_token" in res_login.json()
