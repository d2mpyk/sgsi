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
- `routers/audit.py`: consultas y vistas del reporte global de auditoría.
- `utils/auth.py`: hash, JWT, usuario actual, tokens de correo y logs de seguridad.
- `utils/middleware.py`: protección de vistas HTML del dashboard por cookie.
- `utils/init_db.py`: bootstrap y ajustes de esquema.
- `models/`: entidades SQLAlchemy 2.x (`users`, `approved`, `departments`, `documents`, `document_reads`, `suggestions`, `lms`).
- `schemas/`: modelos Pydantic de entrada/salida.
- `services/lms_service.py`: reglas de evaluación, intentos, estados y certificados LMS.
- `repositories/lms_repository.py`: consultas y persistencia específica del LMS.
- `alembic/`: migraciones versionadas; actualmente existe una migración inicial para las tablas LMS.

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
repositories/
routers/
schemas/
services/
static/
templates/
  auth/
  dashboard/
  email/
media/
alembic/
tests/
utils/
```

Las rutas HTTP se publican bajo `/api/v1` por defecto y la aplicación usa `/sgsi` como `root_path` por defecto. El prefijo puede cambiarse mediante `API_PREFIX` y `ROOT_PATH`.

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

No versionar `.env`: contiene credenciales de base de datos, secretos JWT y credenciales SMTP. Usa `.env_example` como plantilla y rota cualquier secreto que haya sido expuesto.

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

Estado de la última verificación local (11 de agosto de 2026): 165 pruebas recolectadas, 160 pasaron y 5 fallaron. Las fallas se producen al escribir PDFs en `media/documents` o `media/documents/certificates` con `PermissionError`; antes de atribuirlas a lógica de negocio, verifica que el usuario del proceso tenga permisos de lectura/escritura sobre `media/`.

La suite usa SQLite en memoria, mientras que el runtime usa MySQL/MariaDB. Por ello, las pruebas no sustituyen una verificación de migraciones, charset, permisos de archivos y conectividad contra la base de datos real.

## Persistencia y despliegue

- La conexión de producción se construye como `mysql+pymysql` desde las variables `DB_*`.
- `app.main` ejecuta `Base.metadata.create_all()` y ajustes incrementales al importarse. Esto puede modificar el esquema durante un arranque; coordina este comportamiento con Alembic antes de desplegar varias réplicas.
- `alembic.ini` contiene una URL de ejemplo; si se adopta Alembic como mecanismo principal, debe configurarse la URL real en el entorno de migración y revisar el orden de las revisiones.
- `media/` contiene documentos, certificados y perfiles; debe tener backup, permisos mínimos y una política de retención acorde con la evidencia SGSI.

## Seguridad y operación

- El login deja `secure=False` en cookie (válido para local); en producción HTTPS debe endurecerse con `Secure`, `HttpOnly`, `SameSite` y una estrategia CSRF apropiada.
- Hay dos capas de acceso:
  - middleware HTML (`utils/middleware.py`)
  - dependencias por router (`get_current_user` / `get_current_admin`)
- `static/` y `media/` se montan como directorios estáticos en `app.main` y el middleware permite su acceso sin autenticación. No coloques secretos ni archivos que deban estar sujetos a autorización dentro de esas rutas; las descargas de documentos sensibles deben pasar por los endpoints que validan rol y trazabilidad.
- Logs:
  - `security.log`
  - `email_logs.log`
- Archivos persistidos y evidencia en `media/`.

## Hallazgos de la revisión del repositorio

- La arquitectura está separada en routers, modelos, schemas, servicios y repositorios, con cobertura funcional extensa para autenticación, usuarios, documentos, auditoría, LMS y sugerencias.
- La cadena documental queda explícita: descarga (`download_at`) -> confirmación (`read_at`) -> certificado PDF -> auditoría.
- La cadena LMS queda explícita: intento -> aprobación/bloqueo -> métricas -> informe PDF versionado.
- El arranque tiene efectos de esquema y bootstrap; debe tratarse como operación de infraestructura, no como una importación inocua.
- El principal bloqueo observado en la ejecución de pruebas fue la escritura en `media/`; corregir permisos del directorio y repetir la suite antes de aceptar un cambio que genere evidencia PDF.
- La publicación directa de `/media` y la cookie no segura son decisiones válidas para el entorno local, pero riesgosas si se trasladan sin cambios a producción.

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
- dependencias fijadas en `requirements.txt`; runtime verificado con Python 3.14 en el entorno local inspeccionado.
- orientación: portal SGSI enfocado en trazabilidad de lectura y evidencia auditable
- Ruta de despliegue:
  - Server: 192.168.42.23
  - Path: /var/www/html/sgsi