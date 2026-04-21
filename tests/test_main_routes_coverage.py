import asyncio
from datetime import timedelta

from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import main as main_module
from app.main import (
    forbidden_handler,
    internal_server_error_handler,
    rate_limit_exceeded_handler,
)
from utils.auth import create_access_token


def test_main_root_and_public_views(client, monkeypatch):
    root_response = client.get("/", follow_redirects=False)
    assert root_response.status_code in (307, 308)
    assert "/api/v1/auth/login" in root_response.headers.get("location", "")

    favicon_response = client.get("/favicon.ico")
    assert favicon_response.status_code == 200
    assert favicon_response.headers["content-type"].startswith("image/x-icon")

    forgot_response = client.get("/forgot-password")
    assert forgot_response.status_code == 200
    assert "Recupera" in forgot_response.text or "recupera" in forgot_response.text.lower()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/reset-password",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 5000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }

    class FakeTemplateResponse:
        status_code = 200

    monkeypatch.setattr(main_module.templates, "TemplateResponse", lambda **kwargs: FakeTemplateResponse())
    reset_response = main_module.reset_password_view(Request(scope))
    assert reset_response.status_code == 200


def test_rate_limit_exception_handler_returns_json():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 5000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    request = Request(scope)
    class DummyRateLimitExceeded:
        detail = "5/minute"

    exc = DummyRateLimitExceeded()
    response = asyncio.run(rate_limit_exceeded_handler(request, exc))

    assert response.status_code == 429
    assert b"L\xc3\xadmite de peticiones excedido" in response.body


def test_not_found_html_without_token_redirects_to_login(client):
    response = client.get(
        "/api/v1/posts/view/10",
        headers={"accept": "text/html"},
    )

    assert response.status_code == 404
    assert "Error 404" in response.text
    assert "/api/v1/auth/login" in response.text
    assert "Ir a Inicio de Sesi" in response.text


def test_not_found_html_with_active_token_redirects_to_dashboard(client):
    token = create_access_token(
        data={
            "id": "99",
            "sub": "qa.user",
            "email": "qa.user@example.com",
            "type": "user",
            "role": "user",
        },
        expires_delta=timedelta(minutes=10),
    )
    client.cookies.set("access_token", token)

    response = client.get(
        "/api/v1/posts/view/10",
        headers={"accept": "text/html"},
    )

    assert response.status_code == 404
    assert "/api/v1/dashboard/" in response.text
    assert "Ir al Dashboard" in response.text


def test_not_found_json_keeps_api_shape(client):
    response = client.get(
        "/api/v1/posts/view/10",
        headers={"accept": "application/json"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def build_request(path: str, accept: str = "text/html", cookie: str | None = None) -> Request:
    headers = [(b"accept", accept.encode())]
    if cookie:
        headers.append((b"cookie", cookie.encode()))

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "query_string": b"",
        "client": ("127.0.0.1", 5000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
        "app": main_module.app,
    }
    return Request(scope)


def test_forbidden_handler_returns_html_for_browser_requests():
    request = build_request("/api/v1/users/", accept="text/html")
    exc = StarletteHTTPException(status_code=403, detail="Acceso denegado")

    response = asyncio.run(forbidden_handler(request, exc))

    assert response.status_code == 403
    assert "/api/v1/auth/login" in response.body.decode()
    assert "Error 403" in response.body.decode()


def test_forbidden_handler_returns_json_for_api_requests():
    request = build_request("/api/v1/users/", accept="application/json")
    exc = StarletteHTTPException(status_code=403, detail="Acceso denegado")

    response = asyncio.run(forbidden_handler(request, exc))

    assert response.status_code == 403
    assert response.body == b'{"detail":"Acceso denegado"}'


def test_internal_server_error_handler_returns_html_with_dashboard_when_token_is_valid():
    token = create_access_token(
        data={
            "id": "99",
            "sub": "qa.user",
            "email": "qa.user@example.com",
            "type": "user",
            "role": "user",
        },
        expires_delta=timedelta(minutes=10),
    )
    request = build_request(
        "/api/v1/posts/view/10",
        accept="text/html",
        cookie=f"access_token={token}",
    )

    response = asyncio.run(internal_server_error_handler(request, Exception("boom")))

    assert response.status_code == 500
    assert "/api/v1/dashboard/" in response.body.decode()
    assert "Error 500" in response.body.decode()


def test_internal_server_error_handler_returns_json_for_api_requests():
    request = build_request("/api/v1/posts/view/10", accept="application/json")

    response = asyncio.run(internal_server_error_handler(request, Exception("boom")))

    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal Server Error"}'
