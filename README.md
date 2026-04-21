# SGSI FastAPI

Aplicación web para gestionar el ciclo documental de un SGSI: publicación de políticas, control de versiones, evidencia de lectura por colaborador y reportes de cumplimiento para auditoría.

## Resumen funcional

Esta app combina API + vistas HTML server-side (Jinja2) para operar un portal interno de cumplimiento documental.

Flujos principales:
- autenticación por formulario (`/api/v1/auth/token`) con JWT en cookie `HttpOnly`
- dashboard HTML con pendientes de lectura por usuario
- dashboard HTML con pendientes de evaluaciones LMS por usuario
- administración de usuarios, activación por correo y recuperación de contraseña
- catálogo de departamentos y asignación de usuarios
- carga documental unitaria y por lotes
- control de versiones por `code` (desactiva versiones activas previas)
- descarga y confirmación de lectura de políticas
- generación y almacenamiento físico de certificados PDF de lectura
- reporte global de auditoría de lectura por política/área/usuario
- academia interna LMS SGSI con posts, quizzes e intentos por semestre
- métricas LMS por período (cumplimiento, aprobación, dificultad, pendientes)
- generación/exportación de informe PDF de cumplimiento LMS con versionado documental
- buzón interno de sugerencias con visibilidad por rol

## Arquitectura

Punto de entrada: `app/main.py`.

Al importarse, **no es pasivo**: ejecuta validaciones y tareas de arranque.

### Side effects de arranque
- valida configuración sensible con `get_init_config()`
- crea tablas con `Base.metadata.create_all(bind=engine)`
- ejecuta ajustes incrementales:
  - `ensure_document_reads_download_at_column()`
  - `ensure_suggestions_table()`
  - `ensure_users_department_column()`
- inicializa usuarios aprobados/admin con `init_approved_users()`

### Módulos clave
- `routers/auth.py`: login/logout y emisión de token.
- `routers/dashboard.py`: dashboard principal.
- `routers/documents.py`: núcleo de negocio documental (carga, lectura, certificados, cumplimiento, auditoría).
- `routers/lms.py`: academia interna SGSI, quizzes, intentos, métricas y reporte LMS.
- `routers/users.py`: ciclo de vida de cuentas y administración.
- `routers/suggestions.py`: sugerencias internas.
- `routers/media.py`: entrega segura de imágenes de perfil.
- `utils/auth.py`: hash, JWT, usuario actual, tokens de correo y logs de seguridad.
- `utils/middleware.py`: protección de vistas HTML del dashboard por cookie.
- `utils/init_db.py`: bootstrap y ajustes de esquema.
- `models/`: entidades SQLAlchemy 2.x (`users`, `approved`, `departments`, `documents`, `document_reads`, `suggestions`, `lms`).

## Reglas de negocio importantes

- Usuarios `user` solo ven políticas activas; `admin` ve todo el inventario.
- Confirmar lectura de política requiere descarga previa (`download_at`).
- El registro `document_reads` conserva dos hitos: `download_at` y `read_at`.
- Cuando se confirma lectura, se genera certificado PDF y se guarda en:
  - `media/documents/certificates/<departamento>/...pdf`
- En documentos con `code`, una nueva versión activa desactiva las anteriores activas del mismo código.
- En LMS, cada post tiene máximo `max_intentos` por semestre (actualmente 3).
- Si un usuario aprueba un post LMS, se bloquean intentos restantes del semestre para ese post.
- Si agota intentos sin aprobar, queda bloqueado hasta el siguiente semestre.
- El período activo LMS se resuelve automáticamente por semestre: `01-ene` a `30-jun` y `01-jul` a `31-dic`.
- Los reportes LMS en PDF se guardan como documento versionado en `media/documents/`.

## Estructura del repositorio

```text
app/
models/
routers/
schemas/
static/
templates/
  auth/
  dashboard/
  email/
media/
tests/
utils/
```

## Requisitos

- Python 3.12+
- MariaDB/MySQL (runtime real)
- SMTP SSL para correos de verificación y recuperación

## Configuración

La configuración se carga desde `.env` con `pydantic-settings` (`utils/config.py`).

Usa `.env_example` como plantilla y define, al menos:
- DB: `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`
- JWT: `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`
- verificación/reset: `SECRET_KEY_CHECK_MAIL`, `SECURITY_PASSWD_SALT`
- bootstrap admin: `ADMIN`, `NAME`
- SMTP: `EMAIL_SERVER`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWD`
- branding/URLs: `COMPANY_NAME`, `PROJECT_NAME`, `DOMINIO`

`ROOT_PATH` se lee del entorno y por defecto es `/sgsi`.

## Ejecución local

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --reload
```

## Pruebas

La suite usa `pytest` + `TestClient`.

En pruebas, `tests/conftest.py`:
- reemplaza la DB por SQLite en memoria (`StaticPool`)
- sobreescribe `get_db`
- desactiva temporalmente el rate limiter

Ejecutar todo:

```powershell
.\.venv\Scripts\pytest tests -q
```

Ejecutar archivo puntual:

```powershell
.\.venv\Scripts\pytest tests\test_document_read_certificate.py -q
```

## Seguridad y operación

- El login deja `secure=False` en cookie (válido para local); en producción HTTPS debe endurecerse.
- Hay dos capas de acceso:
  - middleware HTML (`utils/middleware.py`)
  - dependencias por router (`get_current_user` / `get_current_admin`)
- Logs:
  - `security.log`
  - `email_logs.log`
- Archivos persistidos y evidencia en `media/`.

## Riesgos al modificar

Revisa con cuidado cambios en:
- `app/main.py`
- `utils/config.py`, `utils/database.py`, `utils/init_db.py`
- `utils/auth.py`, `utils/middleware.py`
- `routers/documents.py`
- `routers/lms.py`
- `routers/users.py`

## Estado actual

- versión de app declarada en FastAPI: `5.3.1`
- orientación: portal SGSI enfocado en trazabilidad de lectura y evidencia auditable
