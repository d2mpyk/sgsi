from datetime import UTC, datetime, timedelta
from unittest.mock import mock_open, patch

from models.documents import Document, DocumentRead
from models.departments import Department
from models.users import User
from utils.auth import hash_password
from utils.stats import get_dashboard_stats


def test_mark_document_as_read_saves_certificate_on_server(client, db_session):
    password = "UserPass123!"
    infra_department = (
        db_session.query(Department)
        .filter(Department.departamento == "Infraestructura")
        .first()
    )
    assert infra_department is not None
    user = User(
        username="reader.user",
        email="reader@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
        department_id=infra_department.id,
    )
    db_session.add(user)
    db_session.commit()

    document = Document(
        title="Politica de seguridad",
        version="1.0",
        code="POL-777",
        doc_type="policy",
        filename="policy.pdf",
        content_type="application/pdf",
        uploaded_by_id=user.id,
        is_active=True,
    )
    db_session.add(document)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "reader.user", "password": password},
    )
    assert login_response.status_code == 200

    db_session.add(
        DocumentRead(
            user_id=user.id,
            document_id=document.id,
            download_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    mocked_open = mock_open()
    with patch("routers.documents.os.makedirs") as mocked_makedirs, patch(
        "routers.documents.open", mocked_open
    ):
        response = client.post(f"/api/v1/documents/{document.id}/read")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["action"] == "certificate_generated"
    assert payload["certificate_filename"].endswith(".pdf")
    assert f"/media/documents/certificates/Infraestructura/" in payload["certificate_url"]

    mocked_makedirs.assert_called_once()
    saved_path = mocked_open.call_args[0][0]
    assert "media" in saved_path
    assert "documents" in saved_path
    assert "certificates" in saved_path
    assert "Infraestructura" in saved_path
    assert "reader.user" in saved_path
    assert "POL-777" in saved_path

    written_bytes = mocked_open().write.call_args[0][0]
    assert isinstance(written_bytes, bytes)
    assert len(written_bytes) > 0


def test_mark_document_as_read_requires_prior_download(client, db_session):
    password = "UserPass123!"
    user = User(
        username="reader.no.download",
        email="reader.no.download@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    document = Document(
        title="Politica sin descarga previa",
        version="1.0",
        code="POL-700",
        doc_type="policy",
        filename="policy.pdf",
        content_type="application/pdf",
        uploaded_by_id=user.id,
        is_active=True,
    )
    db_session.add(document)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "reader.no.download", "password": password},
    )
    assert login_response.status_code == 200

    response = client.post(f"/api/v1/documents/{document.id}/read")

    assert response.status_code == 409
    payload = response.json()
    assert payload["action"] == "download_required"
    assert "Primero debe descargar la política" in payload["detail"]
    assert payload["download_url"].endswith(f"/api/v1/documents/{document.id}/download")

    read_record = db_session.query(DocumentRead).filter_by(document_id=document.id).first()
    assert read_record is None


def test_download_policy_updates_download_at_only_until_read_is_confirmed(client, db_session):
    password = "UserPass123!"
    user = User(
        username="download.user",
        email="download@example.com",
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    document = Document(
        title="Politica descargable",
        version="1.0",
        code="POL-888",
        doc_type="policy",
        filename="policy.pdf",
        content_type="application/pdf",
        uploaded_by_id=user.id,
        is_active=True,
    )
    db_session.add(document)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "download.user", "password": password},
    )
    assert login_response.status_code == 200

    with patch("routers.documents.os.path.exists", return_value=True), patch(
        "routers.documents.FileResponse"
    ) as mocked_file_response:
        mocked_file_response.return_value = "file-response"
        response = client.get(f"/api/v1/documents/{document.id}/download")

    assert response.status_code == 200

    read_record = db_session.query(DocumentRead).filter_by(document_id=document.id).first()
    assert read_record is not None
    assert read_record.download_at is not None
    assert read_record.read_at is None

    previous_download_at = read_record.download_at
    read_record.download_at = previous_download_at - timedelta(minutes=5)
    db_session.commit()

    with patch("routers.documents.os.path.exists", return_value=True), patch(
        "routers.documents.FileResponse"
    ) as mocked_file_response:
        mocked_file_response.return_value = "file-response"
        client.get(f"/api/v1/documents/{document.id}/download")

    db_session.refresh(read_record)
    assert read_record.download_at > previous_download_at - timedelta(minutes=5)
    assert read_record.read_at is None

    read_record.read_at = datetime.now(UTC)
    frozen_download_at = read_record.download_at
    db_session.commit()

    with patch("routers.documents.os.path.exists", return_value=True), patch(
        "routers.documents.FileResponse"
    ) as mocked_file_response:
        mocked_file_response.return_value = "file-response"
        client.get(f"/api/v1/documents/{document.id}/download")

    db_session.refresh(read_record)
    assert read_record.download_at == frozen_download_at


def test_admin_policy_download_and_confirmation_follow_business_rules(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_reader",
        email="admin_reader@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    policy = Document(
        title="Politica admin",
        version="1.0",
        code="POL-999",
        doc_type="policy",
        filename="policy_admin.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_reader", "password": admin_pass},
    )
    assert login_response.status_code == 200

    response_without_download = client.post(f"/api/v1/documents/{policy.id}/read")
    assert response_without_download.status_code == 409

    read_record = db_session.query(DocumentRead).filter_by(
        user_id=admin.id, document_id=policy.id
    ).first()
    assert read_record is None

    with patch("routers.documents.os.path.exists", return_value=True), patch(
        "routers.documents.FileResponse"
    ) as mocked_file_response:
        mocked_file_response.return_value = "file-response"
        first_download_response = client.get(f"/api/v1/documents/{policy.id}/download")

    assert first_download_response.status_code == 200

    read_record = db_session.query(DocumentRead).filter_by(
        user_id=admin.id, document_id=policy.id
    ).first()
    assert read_record is not None
    assert read_record.download_at is not None
    assert read_record.read_at is None

    original_download_at = read_record.download_at
    read_record.download_at = original_download_at - timedelta(minutes=5)
    db_session.commit()

    with patch("routers.documents.os.path.exists", return_value=True), patch(
        "routers.documents.FileResponse"
    ) as mocked_file_response:
        mocked_file_response.return_value = "file-response"
        second_download_response = client.get(f"/api/v1/documents/{policy.id}/download")

    assert second_download_response.status_code == 200

    db_session.refresh(read_record)
    refreshed_download_at = read_record.download_at
    assert refreshed_download_at > original_download_at - timedelta(minutes=5)
    assert read_record.read_at is None

    mocked_open = mock_open()
    with patch("routers.documents.os.makedirs"), patch(
        "routers.documents.open", mocked_open
    ):
        confirm_response = client.post(f"/api/v1/documents/{policy.id}/read")

    assert confirm_response.status_code == 200
    confirm_payload = confirm_response.json()
    assert confirm_payload["action"] == "certificate_generated"
    assert confirm_payload["certificate_filename"].endswith(".pdf")

    db_session.refresh(read_record)
    assert read_record.download_at == refreshed_download_at
    assert read_record.read_at is not None

    final_download_at = read_record.download_at
    with patch("routers.documents.os.path.exists", return_value=True), patch(
        "routers.documents.FileResponse"
    ) as mocked_file_response:
        mocked_file_response.return_value = "file-response"
        third_download_response = client.get(f"/api/v1/documents/{policy.id}/download")

    assert third_download_response.status_code == 200

    db_session.refresh(read_record)
    assert read_record.download_at == final_download_at
    assert read_record.read_at is not None


def test_dashboard_stats_counts_only_unconfirmed_policies_per_user(db_session):
    user = User(
        username="stats.user",
        email="stats@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    policies = [
        Document(
            title="Politica 1",
            version="1.0",
            code="POL-001",
            doc_type="policy",
            filename="p1.pdf",
            content_type="application/pdf",
            uploaded_by_id=user.id,
            is_active=True,
        ),
        Document(
            title="Politica 2",
            version="1.0",
            code="POL-002",
            doc_type="policy",
            filename="p2.pdf",
            content_type="application/pdf",
            uploaded_by_id=user.id,
            is_active=True,
        ),
        Document(
            title="Politica 3",
            version="1.0",
            code="POL-003",
            doc_type="policy",
            filename="p3.pdf",
            content_type="application/pdf",
            uploaded_by_id=user.id,
            is_active=True,
        ),
    ]
    db_session.add_all(policies)
    db_session.commit()

    db_session.add(
        DocumentRead(
            user_id=user.id,
            document_id=policies[0].id,
            download_at=datetime.now(UTC),
            read_at=None,
        )
    )
    db_session.add(
        DocumentRead(
            user_id=user.id,
            document_id=policies[1].id,
            download_at=datetime.now(UTC),
            read_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    stats = get_dashboard_stats(db_session, current_user=user)
    assert stats["total_pending"] == 2
