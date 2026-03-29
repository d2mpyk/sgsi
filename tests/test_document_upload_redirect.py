import io
from unittest.mock import MagicMock, patch

from models.documents import Document
from models.users import User
from utils.auth import hash_password


def test_single_upload_redirects_with_flash_and_shows_new_document(client, db_session):
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

    login_resp = client.post(
        "/api/v1/auth/token", data={"username": "admin", "password": admin_pass}
    )
    assert login_resp.status_code == 200

    with patch("routers.documents.open", new_callable=MagicMock), patch(
        "routers.documents.shutil.copyfileobj"
    ), patch("routers.documents.os.makedirs"):
        response = client.post(
            "/api/v1/documents/upload",
            data={
                "title": "Politica de escritorio limpio",
                "doc_type": "policy",
                "version": "1.0",
                "code": "POL-99",
            },
            files={
                "file": ("politica.pdf", io.BytesIO(b"%PDF-1.4 content..."), "application/pdf")
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/api/v1/documents/view")

    flash_messages = [
        cookie.value
        for cookie in client.cookies.jar
        if cookie.name == "flash_message"
    ]
    assert any(
        "Documento agregado satisfactoriamente" in message
        for message in flash_messages
    )

    saved_doc = db_session.query(Document).filter_by(code="POL-99").first()
    assert saved_doc is not None
    assert saved_doc.title == "Politica de escritorio limpio"
    assert saved_doc.description == "politica.pdf"

    page = client.get("/api/v1/documents/view")
    assert page.status_code == 200
    assert "Documento agregado satisfactoriamente" in page.text
    assert "Politica de escritorio limpio" in page.text


def test_single_upload_appends_original_filename_to_custom_description(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_description",
        email="admin_description@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_description", "password": admin_pass},
    )
    assert login_resp.status_code == 200

    with patch("routers.documents.open", new_callable=MagicMock), patch(
        "routers.documents.shutil.copyfileobj"
    ), patch("routers.documents.os.makedirs"):
        response = client.post(
            "/api/v1/documents/upload",
            data={
                "title": "Politica con descripcion",
                "doc_type": "policy",
                "description": "Documento para pruebas",
                "version": "1.0",
                "code": "POL-152",
            },
            files={
                "file": (
                    "Politica_Pruebas.pdf",
                    io.BytesIO(b"%PDF-1.4 content..."),
                    "application/pdf",
                )
            },
            follow_redirects=False,
        )

    assert response.status_code == 303

    saved_doc = db_session.query(Document).filter_by(code="POL-152").first()
    assert saved_doc is not None
    assert saved_doc.description == (
        "Documento para pruebas\nPolitica_Pruebas.pdf"
    )


def test_single_upload_extracts_version_from_filename_when_present(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_version",
        email="admin_version@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/token", data={"username": "admin_version", "password": admin_pass}
    )
    assert login_resp.status_code == 200

    with patch("routers.documents.open", new_callable=MagicMock), patch(
        "routers.documents.shutil.copyfileobj"
    ), patch("routers.documents.os.makedirs"):
        response = client.post(
            "/api/v1/documents/upload",
            data={
                "title": "Titulo manual",
                "doc_type": "policy",
                "version": "1.0",
                "code": "POL-150",
            },
            files={
                "file": (
                    "Politica_Acceso_v2.3.pdf",
                    io.BytesIO(b"%PDF-1.4 content..."),
                    "application/pdf",
                )
            },
            follow_redirects=False,
        )

    assert response.status_code == 303

    saved_doc = db_session.query(Document).filter_by(code="POL-150").first()
    assert saved_doc is not None
    assert saved_doc.title == "Titulo manual"
    assert saved_doc.version == "2.3"


def test_single_upload_keeps_form_version_when_filename_has_no_version(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_version_default",
        email="admin_version_default@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_version_default", "password": admin_pass},
    )
    assert login_resp.status_code == 200

    with patch("routers.documents.open", new_callable=MagicMock), patch(
        "routers.documents.shutil.copyfileobj"
    ), patch("routers.documents.os.makedirs"):
        response = client.post(
            "/api/v1/documents/upload",
            data={
                "title": "Titulo sin version en nombre",
                "doc_type": "policy",
                "version": "7.4",
                "code": "POL-151",
            },
            files={
                "file": (
                    "Politica_Acceso.pdf",
                    io.BytesIO(b"%PDF-1.4 content..."),
                    "application/pdf",
                )
            },
            follow_redirects=False,
        )

    assert response.status_code == 303

    saved_doc = db_session.query(Document).filter_by(code="POL-151").first()
    assert saved_doc is not None
    assert saved_doc.title == "Titulo sin version en nombre"
    assert saved_doc.version == "7.4"


def test_documents_view_lists_items_sorted_by_code(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_sort",
        email="admin_sort@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    docs = [
        Document(
            title="Politica B",
            version="1.0",
            code="POL-200",
            doc_type="policy",
            filename="pol_b.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        ),
        Document(
            title="Politica A",
            version="1.0",
            code="POL-100",
            doc_type="policy",
            filename="pol_a.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        ),
        Document(
            title="Registro B",
            version="1.0",
            code="REG-200",
            doc_type="record",
            filename="reg_b.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        ),
        Document(
            title="Registro A",
            version="1.0",
            code="REG-100",
            doc_type="record",
            filename="reg_a.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        ),
    ]
    db_session.add_all(docs)
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_sort", "password": admin_pass},
    )
    assert login_resp.status_code == 200

    page = client.get("/api/v1/documents/view")
    assert page.status_code == 200

    assert page.text.index("POL-100") < page.text.index("POL-200")
    assert page.text.index("REG-100") < page.text.index("REG-200")
