import io
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.responses import RedirectResponse

from models.documents import Document, DocumentRead
from models.users import User
from routers import documents as documents_router
from utils.auth import hash_password


def _fake_request(path: str = "/api/v1/documents/view"):
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(path=path),
        url_for=lambda name, **kwargs: "/api/v1/auth/login",
    )


def _create_user(
    db_session,
    username: str,
    email: str,
    role: str = "admin",
    password: str = "Pass123!",
):
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_helper_functions_cover_additional_branches():
    assert documents_router.get_compliance_semaphore(80) == "yellow"
    assert documents_router.get_compliance_semaphore(40) == "red"
    assert documents_router.normalize_datetime(None) is None

    naive_dt = datetime(2026, 1, 1, 0, 0, 0)
    normalized = documents_router.normalize_datetime(naive_dt)
    assert normalized is not None
    assert normalized.tzinfo == UTC

    svg = documents_router.svg_trend_chart([])
    assert "No hay datos suficientes" in str(svg)


def test_calculate_next_report_version_fallback_when_versions_are_not_numeric(db_session):
    admin = _create_user(
        db_session,
        username="admin_version_fallback",
        email="admin_version_fallback@example.com",
    )
    docs = [
        Document(
            title="Reporte X",
            version="alpha",
            code=documents_router.AUDIT_REPORT_DOC_CODE,
            doc_type="record",
            filename="x.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        ),
        Document(
            title="Reporte Y",
            version="beta",
            code=documents_router.AUDIT_REPORT_DOC_CODE,
            doc_type="record",
            filename="y.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=False,
        ),
    ]
    db_session.add_all(docs)
    db_session.commit()

    next_version = documents_router.calculate_next_report_version(
        db=db_session,
        report_code=documents_router.AUDIT_REPORT_DOC_CODE,
    )
    assert next_version == "3.0"


def test_preview_policy_reading_report_returns_redirect_from_dependency(db_session):
    redirect = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    response = documents_router.preview_policy_reading_report(
        request=_fake_request(path="/api/v1/documents/reports/policies-reading-preview"),
        db=db_session,
        admin_user=redirect,
    )
    assert response is redirect


def test_get_documents_returns_redirect_from_dependency(db_session):
    redirect = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    response = documents_router.get_documents(user_or_redirect=redirect, db=db_session)
    assert response is redirect


def test_get_documents_admin_marks_read_status(db_session):
    admin = _create_user(
        db_session,
        username="admin_read_map",
        email="admin_read_map@example.com",
    )
    doc = Document(
        title="Politica lectura",
        version="1.0",
        code="POL-777",
        doc_type="policy",
        filename="pol777.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()

    read = DocumentRead(
        user_id=admin.id,
        document_id=doc.id,
        download_at=datetime.now(UTC),
        read_at=datetime.now(UTC),
    )
    db_session.add(read)
    db_session.commit()

    response = documents_router.get_documents(user_or_redirect=admin, db=db_session)
    assert len(response) == 1
    assert response[0].is_read_by_user is True
    assert response[0].read_at is not None


def test_get_compliance_stats_returns_redirect_from_dependency(db_session):
    redirect = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    response = documents_router.get_compliance_stats(
        db=db_session,
        admin_user=redirect,
    )
    assert response is redirect


def test_delete_documents_by_code_returns_redirect_from_dependency(db_session):
    redirect = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    response = documents_router.delete_documents_by_code(
        request=_fake_request(),
        code="POL-123",
        db=db_session,
        admin_user=redirect,
    )
    assert response is redirect


def test_delete_documents_by_code_empty_code_returns_400(db_session):
    admin = _create_user(
        db_session,
        username="admin_empty_code",
        email="admin_empty_code@example.com",
    )
    try:
        documents_router.delete_documents_by_code(
            request=_fake_request(),
            code="   ",
            db=db_session,
            admin_user=admin,
        )
        assert False, "Se esperaba HTTPException por código vacío"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400


def test_download_document_redirect_from_dependency(db_session):
    redirect = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    response = documents_router.download_document(
        request=_fake_request(path="/api/v1/documents/1/download"),
        doc_id=1,
        user_or_redirect=redirect,
        db=db_session,
    )
    assert response is redirect


def test_download_document_error_paths(db_session):
    admin = _create_user(
        db_session,
        username="admin_download_paths",
        email="admin_download_paths@example.com",
    )
    user = _create_user(
        db_session,
        username="user_download_paths",
        email="user_download_paths@example.com",
        role="user",
    )

    # not found
    try:
        documents_router.download_document(
            request=_fake_request(path="/api/v1/documents/999/download"),
            doc_id=999,
            user_or_redirect=admin,
            db=db_session,
        )
        assert False, "Se esperaba 404 por documento inexistente"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404

    record_doc = Document(
        title="Registro restringido",
        version="1.0",
        code="REG-403",
        doc_type="record",
        filename="reg403.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    inactive_policy = Document(
        title="Politica inactiva",
        version="1.0",
        code="POL-404",
        doc_type="policy",
        filename="pol404.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=False,
    )
    db_session.add_all([record_doc, inactive_policy])
    db_session.commit()

    # forbidden
    try:
        documents_router.download_document(
            request=_fake_request(path=f"/api/v1/documents/{record_doc.id}/download"),
            doc_id=record_doc.id,
            user_or_redirect=user,
            db=db_session,
        )
        assert False, "Se esperaba 403 por rol sin permiso"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403

    # inactive policy
    try:
        documents_router.download_document(
            request=_fake_request(path=f"/api/v1/documents/{inactive_policy.id}/download"),
            doc_id=inactive_policy.id,
            user_or_redirect=user,
            db=db_session,
        )
        assert False, "Se esperaba 404 por política inactiva"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404

    # file missing branch (admin can access, but physical file does not exist)
    active_policy = Document(
        title="Politica sin archivo",
        version="1.0",
        code="POL-405",
        doc_type="policy",
        filename="pol405.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(active_policy)
    db_session.commit()

    with patch("routers.documents.os.path.exists", return_value=False):
        try:
            documents_router.download_document(
                request=_fake_request(path=f"/api/v1/documents/{active_policy.id}/download"),
                doc_id=active_policy.id,
                user_or_redirect=admin,
                db=db_session,
            )
            assert False, "Se esperaba 404 por archivo físico faltante"
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404


def test_mark_document_as_read_error_paths(db_session):
    user = _create_user(
        db_session,
        username="user_mark_read_paths",
        email="user_mark_read_paths@example.com",
        role="user",
    )

    redirect = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    response = documents_router.mark_document_as_read(
        request=_fake_request(path="/api/v1/documents/1/read"),
        doc_id=1,
        user_or_redirect=redirect,
        db=db_session,
    )
    assert response is redirect

    # not found
    try:
        documents_router.mark_document_as_read(
            request=_fake_request(path="/api/v1/documents/999/read"),
            doc_id=999,
            user_or_redirect=user,
            db=db_session,
        )
        assert False, "Se esperaba 404 por documento inexistente"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404

    record_doc = Document(
        title="Registro no política",
        version="1.0",
        code="REG-READ-01",
        doc_type="record",
        filename="regread01.pdf",
        content_type="application/pdf",
        uploaded_by_id=user.id,
        is_active=True,
    )
    db_session.add(record_doc)
    db_session.commit()

    try:
        documents_router.mark_document_as_read(
            request=_fake_request(path=f"/api/v1/documents/{record_doc.id}/read"),
            doc_id=record_doc.id,
            user_or_redirect=user,
            db=db_session,
        )
        assert False, "Se esperaba 400 por tipo de documento no policy"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400


def test_upload_error_paths_via_http(client, db_session):
    admin_pass = "AdminUploadPaths123!"
    _create_user(
        db_session,
        username="admin_upload_paths",
        email="admin_upload_paths@example.com",
        role="admin",
        password=admin_pass,
    )

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_upload_paths", "password": admin_pass},
    )
    assert login_resp.status_code == 200

    invalid_mime = client.post(
        "/api/v1/documents/upload",
        data={"title": "Invalido", "doc_type": "policy", "version": "1.0"},
        files={"file": ("bad.txt", io.BytesIO(b"bad"), "text/plain")},
        follow_redirects=False,
    )
    assert invalid_mime.status_code == 400

    huge_file = io.BytesIO(b"A" * (22 * 1024 * 1024))
    huge_resp = client.post(
        "/api/v1/documents/upload",
        data={"title": "Grande", "doc_type": "policy", "version": "1.0"},
        files={"file": ("huge.pdf", huge_file, "application/pdf")},
        follow_redirects=False,
    )
    assert huge_resp.status_code == 400

    with patch("routers.documents.open", new_callable=MagicMock), patch(
        "routers.documents.shutil.copyfileobj", side_effect=Exception("disk fail")
    ), patch("routers.documents.os.makedirs"):
        save_error_resp = client.post(
            "/api/v1/documents/upload",
            data={"title": "SaveError", "doc_type": "policy", "version": "1.0"},
            files={"file": ("ok.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            follow_redirects=False,
        )
    assert save_error_resp.status_code == 500


def test_upload_batch_error_paths_via_http(client, db_session):
    admin_pass = "AdminBatchPaths123!"
    _create_user(
        db_session,
        username="admin_batch_paths",
        email="admin_batch_paths@example.com",
        role="admin",
        password=admin_pass,
    )

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_batch_paths", "password": admin_pass},
    )
    assert login_resp.status_code == 200

    # Invalid MIME should be collected as error and return redirect with warning flash.
    batch_invalid = client.post(
        "/api/v1/documents/upload/batch",
        data={"doc_type": "record"},
        files={"files": ("bad.txt", io.BytesIO(b"bad"), "text/plain")},
        follow_redirects=False,
    )
    assert batch_invalid.status_code == 303
    flash_messages = [
        cookie.value for cookie in client.cookies.jar if cookie.name == "flash_message"
    ]
    assert any("Errores" in msg for msg in flash_messages)

    # Exception during copy is also captured as error.
    with patch("routers.documents.open", new_callable=MagicMock), patch(
        "routers.documents.shutil.copyfileobj", side_effect=Exception("copy fail")
    ), patch("routers.documents.os.makedirs"):
        batch_copy_error = client.post(
            "/api/v1/documents/upload/batch",
            data={"doc_type": "record"},
            files={"files": ("ok.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            follow_redirects=False,
        )
    assert batch_copy_error.status_code == 303
