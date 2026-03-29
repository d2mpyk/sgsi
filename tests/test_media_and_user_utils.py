from unittest.mock import patch

import pytest
from fastapi import HTTPException

from models.users import User
from routers.media import get_profile_pic
from utils.auth import hash_password
from utils.users import (
    check_email_exists,
    check_username_exists,
    get_total_users,
)


def test_media_rejects_directory_traversal():
    with pytest.raises(HTTPException) as exc_info:
        get_profile_pic("../secret.txt")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Nombre de archivo inválido"


def test_media_returns_not_found_when_profile_picture_does_not_exist(client):
    with patch("routers.media.os.path.exists", return_value=False), patch(
        "routers.media.os.path.isfile", return_value=False
    ):
        response = client.get("/api/v1/media/media/profile_pics/avatar.png")

    assert response.status_code == 404
    assert response.json()["detail"] == "Archivo no encontrado"


def test_media_returns_file_when_profile_picture_exists(client):
    with patch("routers.media.os.path.exists", return_value=True), patch(
        "routers.media.os.path.isfile", return_value=True
    ), patch("routers.media.FileResponse") as mocked_file_response:
        mocked_file_response.return_value = "file-response"
        response = client.get("/api/v1/media/media/profile_pics/avatar.png")

    assert response.status_code == 200
    mocked_file_response.assert_called_once_with("media/profile_pics/avatar.png")


def test_get_total_users_returns_zero_for_empty_database(db_session):
    assert get_total_users(db_session) == 0


def test_get_total_users_returns_registered_users_count(db_session):
    db_session.add_all(
        [
            User(
                username="user.one",
                email="user.one@example.com",
                password_hash=hash_password("UserPass123!"),
                role="user",
                is_active=True,
            ),
            User(
                username="user.two",
                email="user.two@example.com",
                password_hash=hash_password("UserPass123!"),
                role="user",
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    assert get_total_users(db_session) == 2


def test_check_username_exists_allows_same_user_when_excluded(db_session):
    user = User(
        username="same.user",
        email="same.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    check_username_exists(db_session, "same.user", current_user_id=user.id)


def test_check_username_exists_raises_for_duplicate_case_insensitive(db_session):
    user = User(
        username="Duplicate.User",
        email="duplicate.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        check_username_exists(db_session, "duplicate.user")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Este nombre de usuario ya está registrado."


def test_check_email_exists_raises_for_duplicate_case_insensitive(db_session):
    user = User(
        username="email.user",
        email="Email.User@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        check_email_exists(db_session, "email.user@example.com")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Este Email ya está registrado."
