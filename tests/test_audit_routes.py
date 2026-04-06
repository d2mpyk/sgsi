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


def test_admin_can_update_iso_mapping_inline(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="mapping.edit.admin",
        email="mapping.edit.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    owner = User(
        username="mapping.edit.owner",
        email="mapping.edit.owner@example.com",
        password_hash=hash_password("OwnerPass123!"),
        role="auditor",
        is_active=True,
    )
    db_session.add_all([admin, owner])
    db_session.commit()

    policy = Document(
        title="Politica editable",
        version="1.0",
        code="POL-EDIT",
        doc_type="policy",
        filename="editable.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    mapping = ISOControlMapping(
        control_iso="A.5.1",
        document_id=policy.id,
        evidence="Evidencia inicial",
        responsible_user_id=None,
        status="Pendiente",
    )
    db_session.add(mapping)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": admin.username, "password": admin_pass},
    )
    assert login.status_code == 200

    response = client.post(
        f"/api/v1/audit/mappings/{mapping.id}/update",
        data={
            "control_iso": "A.5.2",
            "evidence": "Evidencia actualizada",
            "responsible_user_id": str(owner.id),
            "status": "Implementado",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db_session.refresh(mapping)
    assert mapping.control_iso == "A.5.2"
    assert mapping.evidence == "Evidencia actualizada"
    assert mapping.responsible_user_id == owner.id
    assert mapping.status == "Implementado"


def test_audit_view_filters_by_control_status_and_responsible(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="mapping.filter.admin",
        email="mapping.filter.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    owner_a = User(
        username="owner.alpha",
        email="owner.alpha@example.com",
        password_hash=hash_password("OwnerPass123!"),
        role="auditor",
        is_active=True,
    )
    owner_b = User(
        username="owner.beta",
        email="owner.beta@example.com",
        password_hash=hash_password("OwnerPass123!"),
        role="auditor",
        is_active=True,
    )
    db_session.add_all([admin, owner_a, owner_b])
    db_session.commit()

    policy_a = Document(
        title="Politica Alpha",
        version="1.0",
        code="POL-A",
        doc_type="policy",
        filename="a.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    policy_b = Document(
        title="Politica Beta",
        version="1.0",
        code="POL-B",
        doc_type="policy",
        filename="b.pdf",
        content_type="application/pdf",
        uploaded_by_id=admin.id,
        is_active=True,
    )
    db_session.add_all([policy_a, policy_b])
    db_session.commit()

    db_session.add_all(
        [
            ISOControlMapping(
                control_iso="A.5.10",
                document_id=policy_a.id,
                evidence="Alpha evidencia",
                responsible_user_id=owner_a.id,
                status="Implementado",
            ),
            ISOControlMapping(
                control_iso="A.8.1",
                document_id=policy_b.id,
                evidence="Beta evidencia",
                responsible_user_id=owner_b.id,
                status="Pendiente",
            ),
        ]
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": admin.username, "password": admin_pass},
    )
    assert login.status_code == 200

    response = client.get(
        f"/api/v1/audit/view?control_q=A.5&status_filter=Implementado&responsible_filter={owner_a.id}"
    )
    assert response.status_code == 200
    assert "A.5.10" in response.text
    assert "Alpha evidencia" in response.text
    assert "A.8.1" not in response.text
    assert "Beta evidencia" not in response.text


def test_audit_view_supports_pagination_and_sorting(client, db_session):
    admin_pass = "AdminPass123!"
    admin = User(
        username="pagination.admin",
        email="pagination.admin@example.com",
        password_hash=hash_password(admin_pass),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    documents = []
    for idx in range(1, 13):
        doc = Document(
            title=f"Politica {idx}",
            version="1.0",
            code=f"POL-{idx}",
            doc_type="policy",
            filename=f"p{idx}.pdf",
            content_type="application/pdf",
            uploaded_by_id=admin.id,
            is_active=True,
        )
        documents.append(doc)
    db_session.add_all(documents)
    db_session.commit()

    db_session.add_all(
        [
            ISOControlMapping(
                control_iso=f"A.5.{idx:02d}",
                document_id=doc.id,
                evidence=f"Ev{idx:02d}",
                status="Pendiente" if idx % 2 == 0 else "Implementado",
            )
            for idx, doc in enumerate(documents, start=1)
        ]
    )
    db_session.commit()

    login = client.post(
        "/api/v1/auth/token",
        data={"username": admin.username, "password": admin_pass},
    )
    assert login.status_code == 200

    response_page_1 = client.get(
        "/api/v1/audit/view?sort_by=control_iso&sort_dir=asc&page_size=10&page=1"
    )
    assert response_page_1.status_code == 200
    assert "A.5.01" in response_page_1.text
    assert "A.5.10" in response_page_1.text
    assert "A.5.11" not in response_page_1.text
    assert "Página 1 / 2" in response_page_1.text

    response_page_3_desc = client.get(
        "/api/v1/audit/view?sort_by=control_iso&sort_dir=desc&page_size=10&page=2"
    )
    assert response_page_3_desc.status_code == 200
    assert "A.5.02" in response_page_3_desc.text
    assert "A.5.01" in response_page_3_desc.text
    assert "A.5.12" not in response_page_3_desc.text


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
