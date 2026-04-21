from datetime import UTC, datetime

from models.documents import Document, DocumentRead
from models.users import User
from utils.auth import hash_password


def test_audit_view_allows_admin_and_renders_master_index(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="audit.admin",
        email="audit.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    employee = User(
        username="audit.employee",
        email="audit.employee@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add_all([admin, employee])
    db_session.commit()

    policy = Document(
        title="Politica de accesos",
        version="1.0",
        code="A.5.15",
        doc_type="policy",
        filename="policy_access.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    db_session.add(
        DocumentRead(
            user_id=employee.id,
            document_id=policy.id,
            download_at=datetime.now(UTC),
            read_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": admin.username, "password": admin_pass},
    )
    assert login.status_code == 200

    response = client.get("/api/v1/audit/view")
    assert response.status_code == 200
    assert "SGSI Master Index" in response.text
    assert "Documentos SGSI" in response.text
    assert "Confirmaciones de lectura" in response.text
    assert "ISO 27001 Control Mapping" not in response.text


def test_audit_view_allows_auditor_role(client, db_session):
    password = "AuditorPass123!"
    auditor = User(
        username="quality.auditor",
        email="quality.auditor@example.com",
        password_hash=hash_password(password),
        role="auditor",
        is_active=True,
    )
    db_session.add(auditor)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": auditor.username, "password": password},
    )
    assert login.status_code == 200

    response = client.get("/api/v1/audit/view")
    assert response.status_code == 200
    assert "Auditoría institucional" in response.text


def test_audit_view_denies_standard_user(client, db_session):
    password = "UserPass123!"
    user = User(
        username="normal.user",
        email="normal.user@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": user.username, "password": password},
    )
    assert login.status_code == 200

    response = client.get("/api/v1/audit/view")
    assert response.status_code == 403
    assert response.json()["detail"] == "Acceso denegado"


def test_audit_view_supports_documents_and_confirmations_pagination(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="sections.pagination.admin",
        email="sections.pagination.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    reader = User(
        username="sections.reader",
        email="sections.reader@example.com",
        password_hash=hash_password("ReaderPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add_all([admin, reader])
    db_session.commit()

    docs = []
    for idx in range(1, 16):
        doc = Document(
            title=f"Doc {idx}",
            version="1.0",
            code=f"DOC-{idx}",
            doc_type="policy",
            filename=f"doc_{idx}.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        )
        docs.append(doc)
    db_session.add_all(docs)
    db_session.commit()

    reads = []
    for idx, doc in enumerate(docs[:12], start=1):
        reads.append(
            DocumentRead(
                user_id=reader.id,
                document_id=doc.id,
                download_at=datetime.now(UTC),
                read_at=datetime.now(UTC) if idx % 2 == 0 else None,
            )
        )
    db_session.add_all(reads)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": admin.username, "password": admin_pass},
    )
    assert login.status_code == 200

    response = client.get(
        "/api/v1/audit/view?doc_page_size=10&doc_page=2&confirm_page_size=10&confirm_page=2"
    )
    assert response.status_code == 200
    assert "Mostrando 11-15 de 15 documentos." in response.text
    assert "Mostrando 11-12 de 12 confirmaciones." in response.text


def test_audit_view_handles_orphan_read_rows_and_no_evidence_status(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="audit.orphan.admin",
        email="audit.orphan.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    reader = User(
        username="audit.orphan.reader",
        email="audit.orphan.reader@example.com",
        password_hash=hash_password("ReaderPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add_all([admin, reader])
    db_session.commit()

    policy = Document(
        title="Policy orphan",
        version="1.0",
        code="POL-ORPHAN",
        doc_type="policy",
        filename="policy_orphan.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    record = Document(
        title="Record should skip",
        version="1.0",
        code="REC-SKIP",
        doc_type="record",
        filename="record_skip.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add_all([policy, record])
    db_session.commit()

    db_session.add_all(
        [
            DocumentRead(
                user_id=reader.id,
                document_id=policy.id,
                download_at=None,
                read_at=None,
            ),
            DocumentRead(
                user_id=reader.id,
                document_id=record.id,
                download_at=datetime.now(UTC),
                read_at=None,
            ),
        ]
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": admin.username, "password": admin_pass},
    )
    assert login.status_code == 200

    response = client.get("/api/v1/audit/view")
    assert response.status_code == 200
    assert "Sin evidencia" in response.text
