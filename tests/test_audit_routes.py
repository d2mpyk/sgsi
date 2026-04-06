from datetime import UTC, datetime

from models.documents import Document, DocumentRead
from models.iso_control_mappings import ISOControlMapping
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
    assert "ISO 27001 Control Mapping" in response.text
    assert "Control ISO" in response.text
    assert "Documento SGSI" in response.text
    assert "Evidencia" in response.text
    assert "Responsable" in response.text
    assert "Estado" in response.text


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


def test_admin_can_create_iso_mapping_in_database(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="mapping.admin",
        email="mapping.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    owner = User(
        username="mapping.owner",
        email="mapping.owner@example.com",
        password_hash=hash_password("OwnerPass123!"),
        role="auditor",
        is_active=True,
    )
    db_session.add_all([admin, owner])
    db_session.commit()

    policy = Document(
        title="Politica continuidad",
        version="2.0",
        code="POL-ISO-1",
        doc_type="policy",
        filename="continuidad.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": admin.username, "password": admin_pass},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/v1/audit/mappings/create",
        data={
            "control_iso": "A.5.30",
            "document_id": str(policy.id),
            "evidence": "Acta de control documental",
            "responsible_user_id": str(owner.id),
            "status": "Implementado",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    mapping = db_session.query(ISOControlMapping).first()
    assert mapping is not None
    assert mapping.control_iso == "A.5.30"
    assert mapping.document_id == policy.id
    assert mapping.status == "Implementado"

    audit_view = client.get("/api/v1/audit/view")
    assert audit_view.status_code == 200
    assert "A.5.30" in audit_view.text
    assert "Acta de control documental" in audit_view.text
    assert "Pendiente de mapeo" not in audit_view.text


def test_auditor_cannot_create_iso_mapping(client, db_session):
    auditor_pass = "AuditorPass123!"
    auditor = User(
        username="mapping.auditor",
        email="mapping.auditor@example.com",
        password_hash=hash_password(auditor_pass),
        role="auditor",
        is_active=True,
    )
    admin = User(
        username="mapping.admin.seed",
        email="mapping.admin.seed@example.com",
        password_hash=hash_password("AdminPass123!"),
        role="admin",
        is_active=True,
    )
    db_session.add_all([auditor, admin])
    db_session.commit()

    policy = Document(
        title="Politica auditoria",
        version="1.0",
        code="POL-ISO-2",
        doc_type="policy",
        filename="auditoria.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": auditor.username, "password": auditor_pass},
    )
    assert login.status_code == 200

    response = client.post(
        "/api/v1/audit/mappings/create",
        data={
            "control_iso": "A.5.1",
            "document_id": str(policy.id),
            "status": "Pendiente",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Acceso denegado"
