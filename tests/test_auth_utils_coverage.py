from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import unquote

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from models.users import User
from utils.auth import (
    authenticate_user,
    confirm_verification_token,
    create_access_token,
    get_current_user,
    get_current_admin,
    get_minutes_until_end_of_year,
    hash_password,
    send_email_confirmation,
    send_reset_password_email,
    verify_access_token,
    verify_password,
    verify_reset_password_token,
)


def decode_cookie_text(value: str) -> str:
    return unquote(value).encode("latin-1", "backslashreplace").decode("unicode_escape")


def build_request(cookies: dict[str, str] | None = None):
    return SimpleNamespace(
        cookies=cookies or {},
        url=SimpleNamespace(path="/api/v1/dashboard"),
        client=SimpleNamespace(host="127.0.0.1"),
        url_for=lambda name: "/api/v1/auth/login",
    )


def test_verify_password_returns_false_for_incorrect_password():
    password_hash = hash_password("CorrectPass123!")

    assert verify_password("WrongPass123!", password_hash) is False


def test_get_minutes_until_end_of_year_returns_non_negative_integer():
    minutes = get_minutes_until_end_of_year()

    assert isinstance(minutes, int)
    assert minutes >= 0


def test_create_and_verify_access_token_round_trip():
    token = create_access_token({"sub": "round.trip"}, expires_delta=timedelta(minutes=5))

    assert verify_access_token(token) == "round.trip"


def test_verify_access_token_raises_for_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        verify_access_token("token-invalido")

    assert exc_info.value.status_code == 401


def test_authenticate_user_accepts_email_case_insensitive(db_session):
    user = User(
        username="auth.user",
        email="Auth.User@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=1,
    )
    db_session.add(user)
    db_session.commit()

    authenticated = authenticate_user("auth.user@example.com", "UserPass123!", db_session)

    assert authenticated is not None
    assert authenticated.id == user.id


def test_confirm_verification_token_returns_false_for_invalid_token():
    assert confirm_verification_token("token-invalido") is False


def test_verify_reset_password_token_returns_none_for_invalid_token():
    assert verify_reset_password_token("token-invalido") is None


def test_send_email_confirmation_renders_template_and_delegates_send():
    template = Mock()
    template.render.return_value = "<p>ok</p>"

    with patch("utils.auth.templates.get_template", return_value=template) as get_template, patch(
        "utils.auth._send_email"
    ) as send_email:
        send_email_confirmation({"email": "user@example.com", "username": "user", "url": "http://test"})

    get_template.assert_called_once_with("email/email_confirmation.html")
    template.render.assert_called_once()
    send_email.assert_called_once()
    assert send_email.call_args.kwargs["recipient_email"] == "user@example.com"


def test_send_reset_password_email_renders_template_and_delegates_send():
    template = Mock()
    template.render.return_value = "<p>reset</p>"

    with patch("utils.auth.templates.get_template", return_value=template) as get_template, patch(
        "utils.auth._send_email"
    ) as send_email:
        send_reset_password_email({"email": "user@example.com", "url": "http://test"})

    get_template.assert_called_once_with("email/password_reset_email.html")
    template.render.assert_called_once()
    send_email.assert_called_once()
    assert send_email.call_args.kwargs["recipient_email"] == "user@example.com"


def test_get_current_admin_rejects_non_admin_user():
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/users"),
        client=SimpleNamespace(host="127.0.0.1"),
    )
    user = SimpleNamespace(username="plain.user", role="user")

    with pytest.raises(HTTPException) as exc_info:
        get_current_admin(request, user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Acceso denegado"


def test_get_current_user_returns_redirect_when_token_is_expired(db_session):
    user = User(
        username="expired.user",
        email="expired.user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=1,
    )
    db_session.add(user)
    db_session.commit()

    expired_token = create_access_token({"sub": user.username}, expires_delta=timedelta(minutes=-5))
    request = build_request({"access_token": expired_token})

    response = get_current_user(request, db_session, None)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"] == "/api/v1/auth/login"
    assert "Su sesión ha expirado" in decode_cookie_text(response.headers["set-cookie"])


def test_get_current_user_returns_redirect_when_token_is_invalid(db_session):
    request = build_request({"access_token": "token.invalido"})

    response = get_current_user(request, db_session, None)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"] == "/api/v1/auth/login"
    assert "Error de autenticación" in decode_cookie_text(response.headers["set-cookie"])


def test_get_current_user_returns_redirect_when_token_belongs_to_inactive_user(db_session):
    user = User(
        username="inactive.cookie",
        email="inactive.cookie@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=False,
        department_id=1,
    )
    db_session.add(user)
    db_session.commit()

    token = create_access_token({"sub": user.username}, expires_delta=timedelta(minutes=5))
    request = build_request({"access_token": token})

    response = get_current_user(request, db_session, None)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert response.headers["location"] == "/api/v1/auth/login"
    assert "Error de autenticación" in decode_cookie_text(response.headers["set-cookie"])
