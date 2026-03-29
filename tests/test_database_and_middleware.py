import asyncio
from unittest.mock import patch

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from utils.database import get_db
from utils.middleware import HTMLAuthMiddleware


class DummySession:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


def build_request(path: str) -> Request:
    app = FastAPI()

    @app.get("/login", name="login")
    def login():
        return {"ok": True}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "app": app,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_get_db_yields_session_and_closes_it_after_iteration():
    fake_session = DummySession()

    with patch("utils.database.SessionLocal", return_value=fake_session):
        generator = get_db()
        yielded_session = next(generator)

        assert yielded_session is fake_session
        assert fake_session.closed is False

        try:
            next(generator)
        except StopIteration:
            pass

    assert fake_session.closed is True


def test_html_auth_middleware_allows_static_files_without_auth():
    middleware = HTMLAuthMiddleware(app=lambda scope, receive, send: None)
    request = build_request("/static/css/dashboard.css")

    async def call_next(req):
        assert req.url.path == "/static/css/dashboard.css"
        return Response("ok", status_code=200)

    response = asyncio.run(middleware.dispatch(request, call_next))

    assert response.status_code == 200


def test_html_auth_middleware_redirects_dashboard_when_token_is_invalid():
    middleware = HTMLAuthMiddleware(app=lambda scope, receive, send: None)
    request = build_request("/api/v1/dashboard/")
    request._cookies = {"access_token": "invalid-token"}

    async def call_next(_req):
        raise AssertionError("call_next no debe ejecutarse con token inválido")

    with patch("utils.middleware.verify_access_token", side_effect=Exception("invalid")):
        response = asyncio.run(middleware.dispatch(request, call_next))

    assert response.status_code == 307
    assert response.headers["location"].endswith("/login")
