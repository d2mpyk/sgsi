from datetime import UTC, datetime, timedelta

from models.documents import Document, DocumentRead
from models.departments import Department
from models.users import User
from utils.auth import hash_password


def test_compliance_stats_assigns_40_for_download_and_100_for_confirmed_read(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_stats",
        email="admin_stats@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    user_downloaded = User(
        username="download_only",
        email="download_only@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    user_confirmed = User(
        username="confirmed_user",
        email="confirmed_user@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
    )
    db_session.add_all([admin, user_downloaded, user_confirmed])
    db_session.commit()

    policy = Document(
        title="Politica estadistica",
        version="1.0",
        code="POL-500",
        doc_type="policy",
        filename="policy_stats.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    db_session.add(
        DocumentRead(
            user_id=user_downloaded.id,
            document_id=policy.id,
            download_at=datetime.now(UTC),
            read_at=None,
        )
    )
    db_session.add(
        DocumentRead(
            user_id=user_confirmed.id,
            document_id=policy.id,
            download_at=datetime.now(UTC),
            read_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_stats", "password": admin_pass},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/documents/stats")
    assert response.status_code == 200

    data = response.json()
    stat = next(item for item in data if item["code"] == "POL-500")

    assert stat["total_users"] == 3
    assert stat["read_count"] == 1
    assert stat["compliance_percentage"] == 46.7


def test_policy_reading_report_exports_audit_ready_html_with_metrics_and_departments(client, db_session):
    admin_pass = "AdminPass123!"
    infra_department = (
        db_session.query(Department)
        .filter(Department.departamento == "Infraestructura")
        .first()
    )
    operations_department = (
        db_session.query(Department)
        .filter(Department.departamento == "Operaciones")
        .first()
    )
    assert infra_department is not None
    assert operations_department is not None

    admin = User(
        username="admin_report",
        email="admin_report@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
        department_id=infra_department.id,
    )
    user_downloaded = User(
        username="download_state",
        email="download_state@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=infra_department.id,
    )
    user_confirmed = User(
        username="confirmed_state",
        email="confirmed_state@example.com",
        password_hash=hash_password("UserPass123!"),
        role="user",
        is_active=True,
        department_id=operations_department.id,
    )
    db_session.add_all([admin, user_downloaded, user_confirmed])
    db_session.commit()

    first_policy = Document(
        title="Politica base",
        version="1.0",
        code="POL-010",
        doc_type="policy",
        filename="policy_010.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        created_at=datetime.now(UTC) - timedelta(days=90),
        is_active=True,
    )
    second_policy = Document(
        title="Politica extendida",
        version="1.0",
        code="POL-020",
        doc_type="policy",
        filename="policy_020.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add_all([first_policy, second_policy])
    db_session.commit()

    download_at = datetime.now(UTC)
    read_at = datetime.now(UTC)
    db_session.add(
        DocumentRead(
            user_id=user_downloaded.id,
            document_id=first_policy.id,
            download_at=download_at,
            read_at=None,
        )
    )
    db_session.add(
        DocumentRead(
            user_id=user_confirmed.id,
            document_id=second_policy.id,
            download_at=download_at,
            read_at=read_at,
        )
    )
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_report", "password": admin_pass},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/documents/reports/policies-reading-status")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert "Informe Global de Confirmación de Lectura de Políticas" in response.text
    assert "Resumen Ejecutivo" in response.text
    assert "Metodología de Medición" in response.text
    assert "Trazabilidad Detallada" in response.text
    assert "Infraestructura" in response.text
    assert "Operaciones" in response.text
    assert "POL-010" in response.text
    assert "POL-020" in response.text
    assert "fuera_de_plazo" in response.text
    assert "Confirmaciones" in response.text


def test_documents_view_shows_single_global_audit_report_button_for_admin(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_ui_report",
        email="admin_ui_report@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    db_session.add_all(
        [
            Document(
                title="Politica uno",
                version="1.0",
                code="POL-101",
                doc_type="policy",
                filename="policy_101.pdf",
                content_type="application/pdf",
                uploaded_by_id=admin.id,
                is_active=True,
            ),
            Document(
                title="Politica dos",
                version="1.0",
                code="POL-102",
                doc_type="policy",
                filename="policy_102.pdf",
                content_type="application/pdf",
                uploaded_by_id=admin.id,
                is_active=True,
            ),
        ]
    )
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_ui_report", "password": admin_pass},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/documents/view")
    assert response.status_code == 200
    assert response.text.count("Informe de Auditoría") == 1
    assert "Vista Previa" in response.text
    assert "/api/v1/documents/reports/policies-reading-status" in response.text
    assert "/api/v1/documents/reports/policies-reading-preview" in response.text
    assert "auditReportPreviewFrame" in response.text
    assert "/unread-report" not in response.text


def test_policy_reading_report_preview_renders_inline_without_download_header(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="admin_preview",
        email="admin_preview@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    db_session.add(
        Document(
            title="Politica preview",
            version="1.0",
            code="POL-301",
            doc_type="policy",
            filename="policy_301.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        )
    )
    db_session.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "admin_preview", "password": admin_pass},
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/documents/reports/policies-reading-preview")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "content-disposition" not in {key.lower(): value for key, value in response.headers.items()}
    assert "Informe Global de Confirmación de Lectura de Políticas" in response.text
    assert "Politica preview" in response.text
