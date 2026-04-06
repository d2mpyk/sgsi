import asyncio

from fastapi import Request

from app import main as main_module
from app.main import rate_limit_exceeded_handler


def test_main_root_and_public_views(client, monkeypatch):
    root_response = client.get("/", follow_redirects=False)
    assert root_response.status_code in (307, 308)
    assert "/api/v1/auth/login" in root_response.headers.get("location", "")

    favicon_response = client.get("/favicon.ico")
    assert favicon_response.status_code == 200
    assert favicon_response.headers["content-type"].startswith("image/png")

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
