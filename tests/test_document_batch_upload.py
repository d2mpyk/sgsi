import io
from unittest.mock import patch, MagicMock
from models.users import User
from models.documents import Document
from utils.auth import hash_password


def test_batch_upload_documents_integration(client, db_session):
    """
    Prueba de integración para la subida por lotes.
    Verifica:
    1. Autenticación como Admin.
    2. Subida de múltiples archivos.
    3. Extracción automática de versiones del nombre del archivo.
    4. Creación correcta en BD.
    """
    # 1. Configuración: Admin User
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

    # Login
    login_resp = client.post(
        "/api/v1/auth/token", data={"username": "admin", "password": admin_pass}
    )
    assert login_resp.status_code == 200

    # 2. Preparar archivos simulados
    # Archivo 1: Normal (sin versión en nombre)
    file1_name = "Manual_Procedimientos.pdf"
    file1_content = b"%PDF-1.4 content..."

    # Archivo 2: Con versión en el nombre (v2.3)
    file2_name = "Politica_Acceso_v2.3.pdf"
    file2_content = b"%PDF-1.4 content..."

    # Formato para TestClient: list of ('files', (filename, fileobj, content_type))
    files_payload = [
        ("files", (file1_name, io.BytesIO(file1_content), "application/pdf")),
        ("files", (file2_name, io.BytesIO(file2_content), "application/pdf")),
    ]

    # 3. Ejecutar petición (Mockeando el sistema de archivos para no ensuciar el disco)
    # Mockeamos 'routers.documents.open' y 'os.makedirs' y 'shutil'
    with patch("routers.documents.open", new_callable=MagicMock), patch(
        "routers.documents.shutil.copyfileobj"
    ), patch("routers.documents.os.makedirs"):

        response = client.post(
            "/api/v1/documents/upload/batch",
            data={"doc_type": "policy"},  # Forzamos que sean políticas
            files=files_payload,
            follow_redirects=False,  # Esperamos un 303 Redirect
        )

    # 4. Validaciones
    assert response.status_code == 303

    # Verificar BD
    docs = db_session.query(Document).order_by(Document.title).all()
    assert len(docs) == 2

    # Validar Archivo 1 (Manual_Procedimientos) -> Versión Default
    doc1 = next(d for d in docs if "Manual" in d.title)
    assert doc1.title == "Manual_Procedimientos"
    assert doc1.version == "1.0"
    assert doc1.doc_type == "policy"
    assert doc1.description == (
        "Carga automática por lotes\nManual_Procedimientos.pdf"
    )

    # Validar Archivo 2 (Politica_Acceso_v2.3) -> Extracción de versión
    doc2 = next(d for d in docs if "Politica" in d.title)
    assert doc2.title == "Politica_Acceso"  # Nombre limpio (sin _v2.3)
    assert doc2.version == "2.3"  # Versión extraída
    assert doc2.doc_type == "policy"
    assert doc2.description == (
        "Carga automática por lotes\nPolitica_Acceso_v2.3.pdf"
    )
