# SGSI FastAPI

Aplicación web desarrollada con FastAPI para gestionar documentación de un SGSI, controlar el acceso de usuarios y auditar la lectura de políticas internas.

La solución combina backend API, vistas HTML renderizadas en servidor con Jinja2, almacenamiento de archivos en disco y persistencia en MariaDB/MySQL. Su foco principal es la operación documental del SGSI: publicación de políticas, control de versiones, confirmación de lectura, generación de evidencia PDF y reportes de cumplimiento para auditoría.

## Qué hace la aplicación

La app resuelve estos flujos principales:

- autenticación por formulario con JWT almacenado en cookie `HttpOnly`
- dashboard HTML protegido para usuarios autenticados
- gestión de usuarios, activación por correo y recuperación de contraseña
- catálogo base de departamentos y asignación de usuarios a un área
- carga individual y masiva de documentos
- control de versiones por código documental
- publicación de políticas activas para lectura obligatoria
- registro de descarga y confirmación de lectura por usuario
- generación y almacenamiento de certificados PDF de lectura
- métricas de cumplimiento y reporte global de auditoría
- buzón interno de sugerencias
- exportación y consulta de logs de seguridad

## Arquitectura general

El punto de entrada es `app/main.py`. Al importarse no solo crea la instancia de FastAPI: también valida la configuración sensible, crea tablas, ejecuta ajustes incrementales de esquema y siembra datos iniciales como el admin principal y el catálogo de departamentos.

### Componentes principales

- `app/main.py`: inicialización de la app, montaje de `static/` y `media/`, middleware y registro de routers.
- `routers/auth.py`: login, logout y emisión de token.
- `routers/dashboard.py`: dashboard principal con pendientes de lectura.
- `routers/documents.py`: gestión documental, descargas, confirmación de lectura, estadísticas y reportes.
- `routers/users.py`: perfil, administración, activación por correo, reenvío de verificación y recuperación de contraseña.
- `routers/suggestions.py`: creación y consulta de sugerencias.
- `routers/media.py`: entrega segura de imágenes de perfil.
- `models/`: entidades SQLAlchemy para usuarios, departamentos, documentos, lecturas y sugerencias.
- `schemas/`: contratos Pydantic para usuarios, documentos y departamentos.
- `utils/auth.py`: hash de contraseñas, JWT, envío de correo, logging de seguridad y resolución del usuario actual.
- `utils/init_db.py`: validaciones de arranque, bootstrap de datos base y pequeñas migraciones.
- `utils/middleware.py`: protección de vistas HTML mediante cookie de autenticación.
- `templates/`: vistas HTML y correos.
- `static/`: CSS, JavaScript e imágenes de la interfaz.
- `media/`: fotos de perfil, documentos subidos y certificados generados.

## Flujos funcionales

### 1. Inicio de sesión y sesión web

El login acepta usuario o correo. Si la autenticación es correcta, genera un JWT y lo guarda en la cookie `access_token`. La navegación HTML protegida usa esa cookie para redirigir al login cuando no existe o es inválida.

### 2. Gestión de usuarios

Los administradores pueden crear usuarios, asignar departamento, administrar rol y activar o desactivar cuentas. El alta deja al usuario inicialmente inactivo y envía un correo de verificación. También existen flujos para:

- editar el propio perfil
- cambiar contraseña
- reenviar verificación de correo
- solicitar recuperación de contraseña
- restablecer contraseña con token temporal
- exportar y consultar logs de seguridad

### 3. Gestión documental

Los administradores pueden subir documentos unitarios o por lotes. Cada documento puede ser:

- `policy`: política con lectura obligatoria
- `record`: documento o evidencia interna

Cuando se sube un documento con `code`, la app desactiva versiones activas anteriores con ese mismo código, manteniendo el historial por obsolescencia en lugar de borrado.

Los usuarios normales solo ven políticas activas. Los administradores ven todo el inventario documental.

### 4. Confirmación de lectura y evidencia

Para confirmar una política, primero debe existir una descarga previa. Ese flujo genera o actualiza un registro en `document_reads`:

- `download_at`: evidencia de descarga
- `read_at`: evidencia de confirmación de lectura

Cuando el usuario confirma lectura, la app genera un certificado PDF con datos del usuario, política, timestamps, hash y trazabilidad, y además guarda una copia en `media/documents/certificates/`.

### 5. Cumplimiento y auditoría

La app expone métricas de cumplimiento por política y genera un informe global HTML de auditoría con:

- resumen ejecutivo
- cumplimiento global
- cumplimiento por área
- trazabilidad detallada por usuario y política
- tendencia histórica
- visualizaciones SVG

También existe vista previa en línea del informe para administradores.

### 6. Sugerencias internas

Los usuarios pueden registrar sugerencias de mejora. Un usuario normal ve solo las suyas; un administrador puede consultar las de todos.

## Base de datos y arranque

El proyecto usa SQLAlchemy 2.x y una base MariaDB/MySQL en runtime. Al importar `app.main` se ejecutan tareas con efectos laterales:

- validación de secretos y variables sensibles
- `Base.metadata.create_all(bind=engine)`
- creación del usuario admin por defecto si aún no existe
- siembra del catálogo de departamentos
- creación de la tabla `suggestions` si falta
- agregado de la columna `download_at` en `document_reads` si falta
- agregado e inicialización de `department_id` en `users` si falta

Esto significa que cambios en arranque, configuración o modelos pueden impactar desarrollo local, pruebas y despliegue desde el momento del import.

## Estructura del proyecto

```text
app/
  main.py
models/
  users.py
  departments.py
  documents.py
  suggestions.py
routers/
  auth.py
  dashboard.py
  documents.py
  media.py
  suggestions.py
  users.py
schemas/
templates/
  auth/
  dashboard/
  email/
static/
media/
tests/
utils/
```

## Requisitos

- Python 3.12 o compatible con las dependencias del proyecto
- MariaDB/MySQL accesible desde la app
- servidor SMTP SSL para notificaciones por correo

Dependencias relevantes:

- `fastapi`
- `sqlalchemy`
- `pydantic-settings`
- `PyMySQL`
- `PyJWT`
- `pwdlib`
- `slowapi`
- `reportlab`
- `pytest`

## Configuración

Usa `.env_example` como base para crear `.env`.

Variables principales:

- `ADMIN`, `NAME`: bootstrap del administrador inicial
- `COMPANY_NAME`, `PROJECT_NAME`: textos institucionales
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`: conexión a base de datos
- `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`: autenticación JWT
- `SECRET_KEY_CHECK_MAIL`, `SECURITY_PASSWD_SALT`: tokens de verificación y reseteo
- `DOMINIO`: base usada en correos y enlaces
- `EMAIL_SERVER`, `EMAIL_PORT`, `EMAIL_USER`, `EMAIL_PASSWD`: SMTP

La app lee además `ROOT_PATH` desde el entorno y usa `/sgsi` por defecto.

## Ejecución local

### 1. Crear entorno e instalar dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 2. Configurar variables

Crear `.env` a partir de `.env_example` y completar credenciales reales.

### 3. Levantar el servidor

```powershell
.\.venv\Scripts\uvicorn app.main:app --reload
```

Con la configuración actual, la app queda bajo el `root_path` `/sgsi`, por lo que en desarrollo o detrás de proxy las URLs deben respetar ese prefijo.

## Pruebas

La suite usa `pytest` y `TestClient`. Las pruebas reemplazan la base real por SQLite en memoria y desactivan el rate limiter.

Ejecutar toda la suite:

```powershell
.\.venv\Scripts\pytest tests -q
```

Ejecutar un archivo puntual:

```powershell
.\.venv\Scripts\pytest tests\test_document_read_certificate.py -q
```

Coberturas actuales observables en `tests/`:

- autenticación y dashboard
- activación de cuenta y recuperación de contraseña
- roles y permisos
- gestión de usuarios y perfiles
- carga documental individual y por lotes
- descargas y confirmación de lectura
- certificados PDF y reportes de cumplimiento
- sugerencias y utilidades auxiliares

## Seguridad y consideraciones operativas

- El login usa JWT en cookie `HttpOnly`; en producción conviene endurecer `secure=True` bajo HTTPS.
- `utils/middleware.py` protege navegación HTML por cookie, mientras dependencias de `utils/auth.py` controlan acceso por usuario y rol.
- Los logs de seguridad se escriben en `security.log` y los de correo en `email_logs.log`.
- Los documentos y certificados se guardan en disco bajo `media/`.
- `routers/media.py` incluye validación básica contra path traversal para fotos de perfil.

## Riesgos y puntos sensibles al cambiar código

- `app/main.py`: cualquier cambio puede alterar arranque y side effects.
- `utils/config.py`, `utils/database.py`, `utils/init_db.py`: afectan boot, conexión y siembra inicial.
- `utils/auth.py`, `utils/middleware.py`: impactan autenticación, cookies y autorización.
- `routers/documents.py`: concentra gran parte de la lógica crítica del negocio.
- `routers/users.py`: concentra el ciclo de vida de cuentas.

## Resumen rápido

Este proyecto es un portal SGSI orientado a control documental y evidencia de lectura. Su valor principal no está solo en listar documentos, sino en mantener trazabilidad: quién descargó una política, quién la confirmó, qué porcentaje de cumplimiento existe y qué evidencia puede presentarse en auditoría.
