import io
from unittest.mock import mock_open, patch

from models.departments import Department
from models.users import User
from utils.auth import hash_password, verify_password


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


def test_update_current_user_profile_rejects_empty_payload(client, db_session):
    password = "UserPass123!"
    user = User(
        username="profile.empty",
        email="profile.empty@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()
    login_user(client, user.username, password)

    response = client.patch("/api/v1/users/me")

    assert response.status_code == 400
    assert response.json()["detail"] == "No se proporcionaron datos para actualizar."


def test_update_current_user_profile_updates_username(client, db_session):
    password = "UserPass123!"
    user = User(
        username="profile.rename",
        email="profile.rename@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()
    login_user(client, user.username, password)

    response = client.patch("/api/v1/users/me", data={"username": "profile.renamed"})

    assert response.status_code == 200
    assert response.json()["username"] == "profile.renamed"
    db_session.refresh(user)
    assert user.username == "profile.renamed"


def test_update_current_user_profile_rejects_invalid_image_type(client, db_session):
    password = "UserPass123!"
    user = User(
        username="profile.invalid.image",
        email="profile.invalid.image@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()
    login_user(client, user.username, password)

    response = client.patch(
        "/api/v1/users/me",
        files={"image_file": ("avatar.gif", io.BytesIO(b"GIF89a"), "image/gif")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Tipo de archivo no válido. Solo se permiten .jpg y .png"


def test_update_current_user_profile_saves_profile_picture(client, db_session):
    password = "UserPass123!"
    user = User(
        username="profile.image",
        email="profile.image@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()
    login_user(client, user.username, password)

    with patch("routers.users.os.makedirs") as makedirs, patch(
        "routers.users.uuid.uuid4", return_value="fixed-uuid"
    ), patch("builtins.open", mock_open()) as mocked_open, patch(
        "routers.users.shutil.copyfileobj"
    ) as copyfileobj:
        response = client.patch(
            "/api/v1/users/me",
            files={"image_file": ("avatar.png", io.BytesIO(b"png-data"), "image/png")},
        )

    assert response.status_code == 200
    assert response.json()["image_file"] == "fixed-uuid.png"
    makedirs.assert_called_once()
    mocked_open.assert_called_once()
    copyfileobj.assert_called_once()


def test_update_current_user_password_updates_hash(client, db_session):
    current_password = "CurrentPass123!"
    new_password = "NewPass123!"
    user = User(
        username="profile.password",
        email="profile.password@example.com",
        password_hash=hash_password(current_password),
        role="user",
        is_active=True,
        department_id=get_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()
    login_user(client, user.username, current_password)

    response = client.patch(
        "/api/v1/users/me/password",
        json={
            "current_password": current_password,
            "new_password": new_password,
        },
    )

    assert response.status_code == 204
    db_session.refresh(user)
    assert verify_password(new_password, user.password_hash) is True
