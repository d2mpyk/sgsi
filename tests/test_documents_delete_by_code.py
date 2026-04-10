from models.documents import Document
from models.users import User
from utils.auth import hash_password


def _create_user(db_session, username: str, email: str, role: str, password: str = "Pass123!"):
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


def test_admin_can_logically_delete_documents_by_code(client, db_session):
    admin_pass = "AdminPass123!"
    admin = _create_user(
        db_session,
        username="admin_delete_docs",
        email="admin_delete_docs@example.com",
        role="admin",
        password=admin_pass,
    )

    doc_1 = Document(
        title="Politica v1",
        version="1.0",
        code="POL-900",
        doc_type="policy",
        filename="pol900_v1.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    doc_2 = Document(
        title="Politica v2",
        version="2.0",
        code="POL-900",
        doc_type="policy",
        filename="pol900_v2.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    doc_other = Document(
        title="Politica otra",
        version="1.0",
        code="POL-901",
        doc_type="policy",
        filename="pol901_v1.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add_all([doc_1, doc_2, doc_other])
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_delete_docs", "password": admin_pass},
    )
    assert login_resp.status_code == 200

    response = client.delete("/api/v1/documents/by-code/pol-900")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "POL-900"
    assert payload["affected"] == 2

    db_session.refresh(doc_1)
    db_session.refresh(doc_2)
    db_session.refresh(doc_other)
    assert doc_1.is_active is False
    assert doc_2.is_active is False
    assert doc_other.is_active is True


def test_delete_documents_by_code_requires_admin_role(client, db_session):
    admin = _create_user(
        db_session,
        username="admin_for_role_check",
        email="admin_for_role_check@example.com",
        role="admin",
        password="AdminPass123!",
    )
    normal_user_pass = "UserPass123!"
    _create_user(
        db_session,
        username="normal_user_delete_docs",
        email="normal_user_delete_docs@example.com",
        role="user",
        password=normal_user_pass,
    )

    doc = Document(
        title="Documento protegido",
        version="1.0",
        code="POL-999",
        doc_type="policy",
        filename="pol999_v1.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "normal_user_delete_docs", "password": normal_user_pass},
    )
    assert login_resp.status_code == 200

    response = client.delete("/api/v1/documents/by-code/POL-999")
    assert response.status_code == 403

    db_session.refresh(doc)
    assert doc.is_active is True


def test_delete_documents_by_code_returns_404_when_code_does_not_exist(client, db_session):
    admin_pass = "AdminPass123!"
    _create_user(
        db_session,
        username="admin_missing_code",
        email="admin_missing_code@example.com",
        role="admin",
        password=admin_pass,
    )

    login_resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_missing_code", "password": admin_pass},
    )
    assert login_resp.status_code == 200

    response = client.delete("/api/v1/documents/by-code/POL-NO-EXISTE")
    assert response.status_code == 404
    assert "No se encontraron documentos" in response.json()["detail"]
