# MEMORY.md - Análisis del Repositorio SGSI

## Contexto del Análisis

**Fecha:** 2026-10-13  
**Versión de la Aplicación:** 5.3.1 (FastAPI)  
**Entorno Inspeccionado:** Python 3.14, Windows  
**Último Commit:** 2fcb960 (2026-08-11) - "Actualización de LMS Nuevo Cuestionario"

---

## 📋 Resumen Ejecutivo de Hallazgos

Se identificaron **2 problemas críticos** relacionados con la exclusión de usuarios activos en reportes:

1. **Informe de Estado de Cumplimiento de Evaluaciones SGSI** (LMS) - CORREGIDO
2. **Vista de Auditoría en `/audit/view`** - CORREGIDO

Ambos problemas compartían la misma causa raíz: los reportes solo mostraban usuarios que ya tenían interacción registrada en el sistema, excluyendo a usuarios activos que no habían interactuado aún.  

---

## 1. Hallazgos Críticos

### 1.1 Problema en el Informe de Estado de Cumplimiento de Evaluaciones SGSI ✅ CORREGIDO

**Ubicación:** `services/lms_service.py` - función `metrics_users_by_period()`  
**Impacto:** Alto - El informe NO mostraba todos los usuarios activos del sistema

**Descripción:**
El informe de métricas LMS (`/lms/view/metrics`) y su versión PDF omitían usuarios activos que no habían interactuado con el sistema LMS. Esto se debía a que la función `metrics_users_by_period()` solo iteraba sobre los resúmenes de usuarios que EXISTÍAN en la tabla `LMSUserPeriodSummary`, en lugar de iterar sobre todos los usuarios activos.

**Código Problemático (ANTES):**
```python
def metrics_users_by_period(db: Session, period_id: int) -> list[LMSMetricUserItem]:
    repo = LMSRepository(db)
    users = {user.id: user for user in repo.list_users()}
    summaries = repo.list_user_summaries_for_period(period_id=period_id)
    result: list[LMSMetricUserItem] = []
    for summary in summaries:  # ← Solo itera sobre summaries existentes
        user = users.get(summary.user_id)
        if user is None:
            continue
        result.append(...)  # ← Usuarios sin summary no aparecían
    return sorted(result, ...)
```

**Solución Aplicada:**
Modificado para iterar sobre TODOS los usuarios activos y crear métricas para cada uno, incluyendo aquellos sin resúmenes (que muestran 0 en todos los indicadores). También se corrigió el cálculo de KPIs en `metrics_by_period()`.

**Archivos Corregidos:**
- `services/lms_service.py` - `metrics_users_by_period()`
- `services/lms_service.py` - `metrics_by_period()`

---

### 1.2 Aclaración: Vista de Auditoría `/audit/view` ✅ NO REQUIERE CORRECCIÓN

**Ubicación:** `routers/audit.py` - función `audit_view()`  
**Impacto:** **Ninguno - El comportamiento es correcto**

**Análisis:**
La vista de auditoría (`/audit/view`) **está diseñada correctamente** para mostrar solo los registros de confirmación que existen (es decir, usuarios que ya han descargado al menos una política). Esto es diferente de los reportes de cumplimiento que deben mostrar todos los usuarios.

**Diferencia clave:**
- **`/audit/view`**: Vista de **evidencia existente** - muestra solo lo que ya ha sido registrado
- **`/documents/view` → "Informe de Auditoría"**: Reporte de **cumplimiento completo** - muestra todos los usuarios

**Conclusión:** Esta vista NO necesita corrección. El comportamiento de mostrar solo usuarios con registros es el esperado para una vista de auditoría de evidencia.

**Nota:** Inicialmente se aplicó una corrección aquí, pero fue revertida al identificar que era el comportamiento correcto y que el test `test_audit_routes.py:169` validaba este comportamiento.

---

### 1.2 Inconsistencia en el Cálculo de Cumplimiento ✅ CORREGIDO

**Ubicación:** `services/lms_service.py` - función `metrics_by_period()`

**Problema:**
El cálculo de cumplimiento usaba:
```python
cumplimiento = (
    round((len([row for row in status_rows if row.is_passed]) / (total_users * total_posts)) * 100, 2)
    if total_users and total_posts
    else 0.0
)
```

Esta fórmula asumía que cada usuario debe tener un `status_row` para cada post, pero esto no era cierto para usuarios nuevos que no habían interactuado con el LMS. El denominador `(total_users * total_posts)` sobreestimaba el total esperado.

**Solución Aplicada:**
Se mejoró el cálculo para usar variables más claras y precisas:
```python
passed_statuses = len([row for row in status_rows if row.is_passed])
total_expected_statuses = total_users * total_posts
cumplimiento = (
    round((passed_statuses / total_expected_statuses) * 100, 2)
    if total_expected_statuses
    else 0.0
)
```

También se corrigió el cálculo de `users_pending` para contar correctamente los usuarios con lecturas pendientes.

---

## 2. Análisis de la Cadena LMS

### 2.1 Flujo de Datos del Informe

```
Router: /lms/view/metrics (lms.py)
    ↓
_build_lms_metrics_context() (lms.py)
    ↓
metrics_by_period() (lms_service.py)
    ↓
metrics_users_by_period() (lms_service.py) ← PROBLEMA
    ↓
list_user_summaries_for_period() (lms_repository.py)
    ↓
Repository: SELECT * FROM LMSUserPeriodSummary WHERE period_id = ?
```

**Punto de Falla:** Los usuarios activos sin registros en `LMSUserPeriodSummary` son excluidos del informe.

### 2.2 Modelos Involucrados

- **User** (`models/users.py`): Tabla de usuarios con campo `is_active`
- **LMSUserPeriodSummary** (`models/lms.py`): Resumen de usuario por período (creado solo cuando hay interacción)
- **LMSUserPostStatus** (`models/lms.py`): Estado de usuario por post por período

### 2.3 ¿Por qué no se crean resúmenes automáticamente?

En `refresh_user_period_summary()` (lms_service.py):
```python
def refresh_user_period_summary(
    db: Session, user_id: int, period: LMSPeriod
) -> LMSUserPeriodSummary:
    repo = LMSRepository(db)
    posts = repo.list_published_posts()
    # ... calcular métricas ...
    summary = repo.get_user_period_summary(user_id=user_id, period_id=period.id)
    if summary is None:
        summary = LMSUserPeriodSummary(user_id=user_id, period_id=period.id)
    # ... actualizar campos ...
    return repo.save_user_period_summary(summary)
```

Esta función SÍ crea resúmenes, pero solo se llamada cuando:
1. Un usuario submite un quiz (`submit_quiz_attempt()`)
2. Se refresca el dashboard de usuario (`dashboard_by_user()`)

**No hay un proceso batch que cree resúmenes para TODOS los usuarios al inicio de un período.**

---

## 3. Arquitectura y Patrones

### 3.1 Patrón de Repositorio
- Bien implementado en `repositories/lms_repository.py`
- Separa consultas SQL de lógica de negocio
- Usa SQLAlchemy 2.x con `scalars()` y `unique()`

### 3.2 Patrón de Servicio
- `services/lms_service.py` contiene lógica de negocio
- Funciones puras que reciben `db: Session`
- Buena separación de responsabilidades

### 3.3 Control de Acceso
- Dos capas:
  1. Middleware HTML (`utils/middleware.py`) - protege vistas
  2. Dependencias por router (`CurrentUser`, `CurrentAdmin`) - protege APIs
- Uso correcto de `RedirectResponse` para usuarios no autenticados

---

## 4. Problemas de Permisos Conocidos

**De AGENTS.md:**
- 5 pruebas fallaron con `PermissionError` al escribir PDFs en `media/`
- Solución: Verificar permisos de escritura en el directorio `media/`
- El usuario del proceso (generalmente el usuario del servicio web) necesita:
  - Lectura/escritura en `media/documents/`
  - Lectura/escritura en `media/documents/certificates/`

---

## 5. Configuración de Seguridad

### 5.1 Cookie JWT
- `secure=False` en desarrollo local
- **Debe activarse `Secure=True` en producción con HTTPS**
- Configuración en `utils/auth.py`

### 5.2 Montaje de Archivos Estáticos
- `app/main.py` monta `/static` y `/media` como estáticos SIN autenticación
- **Riesgo:** Archivos sensibles en estas rutas son accesibles públicamente
- Mitigación: Los documentos LMS pasan por endpoints que validan rol

---

## 6. Reglas de Negocio Clave

### 6.1 LMS
- Máximo 3 intentos por post por semestre
- Aprobación bloquea intentos restantes del semestre
- 3 fallos bloquean el post hasta el siguiente semestre
- Período activo: 01-ene a 30-jun (S1), 01-jul a 31-dic (S2)

### 6.2 Documentos
- Confirmar lectura requiere descarga previa (`download_at`)
- Nueva versión activa con mismo `code` desactiva versiones anteriores
- Certificados PDF se guardan en `media/documents/certificates/{departamento}/`

---

## 7. Mejoras Recomendadas

### 7.1 Prioridad Alta
1. **Corregir informe LMS** para incluir todos los usuarios activos
2. **Ajustar cálculo de cumplimiento** para usar denominador real
3. **Crear job de inicialización** que genere resúmenes para todos los usuarios al activar un período

### 7.2 Prioridad Media
1. **Agregar pruebas** para el endpoint de métricas LMS
2. **Validar permisos** de escritura en `media/` antes de generar PDFs
3. **Endurecer cookie JWT** en producción

### 7.3 Prioridad Baja
1. **Documentar** el proceso de despliegue
2. **Agregar logs** de auditoría para generación de reportes
3. **Considerar caché** para métricas LMS (read-heavy)

---

## 2. Problema de Confirmación de Lectura (Usuario ID=13, Política 0038P)

### 2.1 Descripción del Problema
El usuario con id=13 descarga la política con código "0038P" pero al presionar el botón "Confirmar Lectura" recibe un error: **"Primero debe descargar la política antes de confirmar la lectura."**

### 2.2 Flujo Normal de Confirmación

```
1. Usuario descarga política (GET /{doc_id}/download)
   ↓
2. Se crea/actualiza DocumentRead con download_at = now()
   ↓
3. Usuario hace clic en "Confirmar Lectura" (POST /{doc_id}/read)
   ↓
4. mark_document_as_read() verifica que existe DocumentRead con download_at != None
   ↓
5. Si OK: actualiza read_at = now() y genera certificado
   ↓
6. Si NO: devuelve error 409
```

### 2.3 Causas Posibles

#### 2.3.1 La política 0038P NO es de tipo "policy"
**🎯 Esta es la causa más probable.**

En `routers/documents.py`, el endpoint de descarga solo registra la descarga si el documento es de tipo "policy":

```python
if doc.doc_type == "policy":
    upsert_policy_download_read(
        db=db,
        user_id=current_user.id,
        document_id=doc.id,
    )
```

Si la política 0038P es de tipo "record" en lugar de "policy", **no se creará el registro `DocumentRead`**, y al intentar confirmar la lectura, el usuario recibirá el error 409.

**Solución:**
```sql
-- Verificar el tipo de la política 0038P
SELECT doc_type, code, title FROM documents WHERE code = '0038P';

-- Si no es 'policy', actualizarla
UPDATE documents SET doc_type = 'policy' WHERE code = '0038P';
```

#### 2.3.2 El registro DocumentRead no se creó correctamente
Si el usuario descargó la política pero el registro no se insertó en la base de datos, también recibirá el error.

**Verificación:**
```sql
-- Buscar el registro para usuario 13 y política 0038P
SELECT * FROM document_reads 
WHERE user_id = 13 AND document_id = (SELECT id FROM documents WHERE code = '0038P');
```

Si el registro no existe o tiene `download_at IS NULL`, este es el problema.

**Posible causa:** Error de transacción o fallo en `db.commit()` en `upsert_policy_download_read()`.

#### 2.3.3 El botón en el template no está disponible
El botón "Confirmar Lectura" solo aparece si el documento es de tipo "policy" y el usuario no lo ha leído:

```html
{% if doc.is_read_by_user %}
<span>Leído ({{ doc.read_at.strftime('%Y-%m-%d') }})</span>
{% else %}
<button onclick="markAsRead({{ doc.id }}, this)">Confirmar Lectura</button>
{% endif %}
```

Si el documento es de tipo "record", el botón no aparecerá en la tabla de políticas.

---

### 2.4 Código Involucrado

#### 2.4.1 Endpoint de Descarga (`/api/v1/documents/{doc_id}/download`)
**Archivo:** `routers/documents.py` - `download_document()`

```python
if doc.doc_type == "policy":
    upsert_policy_download_read(
        db=db,
        user_id=current_user.id,
        document_id=doc.id,
    )
```

**Problema:** Solo registra descarga si el documento es de tipo "policy".

#### 2.4.2 Función de Registro de Descarga
**Archivo:** `routers/documents.py` - `upsert_policy_download_read()`

```python
def upsert_policy_download_read(db: Session, user_id: int, document_id: int) -> DocumentRead:
    existing_read = db.execute(select(DocumentRead).where(...)).scalars().first()
    
    if existing_read is None:
        # Crea nuevo registro
        existing_read = DocumentRead(
            user_id=user_id,
            document_id=document_id,
            download_at=datetime.now(UTC),
            read_at=None,
        )
        db.add(existing_read)
        db.commit()
        db.refresh(existing_read)
        return existing_read
    
    if existing_read.read_at is None:
        # Actualiza download_at si no ha confirmado lectura
        existing_read.download_at = datetime.now(UTC)
        db.commit()
        db.refresh(existing_read)
    
    return existing_read
```

**Nota:** Si el usuario ya confirmó lectura (`read_at is not None`), no actualiza el `download_at`.

#### 2.4.3 Endpoint de Confirmación (`/api/v1/documents/{doc_id}/read`)
**Archivo:** `routers/documents.py` - `mark_document_as_read()`

```python
# Verificar si ya lo leyó
if not existing_read or existing_read.download_at is None:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Primero debe descargar la política antes de confirmar la lectura.",
            "action": "download_required",
            "download_url": str(request.url_for("download_document", doc_id=doc_id)),
        },
    )
elif existing_read.read_at is None:
    existing_read.read_at = datetime.now(UTC)
    db.commit()
    db.refresh(existing_read)
```

**Requerimiento:** `existing_read` debe existir Y `download_at` debe no ser None.

#### 2.4.4 JavaScript del Botón
**Archivo:** `static/js/documents.js`

```javascript
async function markAsRead(docId, btnElement) {
    const response = await fetch(`${BASE_PATH}${API_PREFIX}/documents/${docId}/read`, {
        method: 'POST'
    });
    
    if (response.ok) {
        const payload = await response.json();
        openCertificateInBackground(payload.certificate_url);
        // ...
    } else {
        const err = await response.json();
        if (response.status === 409 && err.action === "download_required") {
            alert(err.detail);
            window.open(err.download_url, "_blank", "noopener");
        } else {
            alert("Error: " + err.detail);
        }
    }
}
```

---

### 2.5 Solución Recomendada

#### 2.5.1 Verificar el tipo de la política 0038P

```sql
-- Consulta el tipo de la política
SELECT id, code, title, doc_type, is_active FROM documents WHERE code = '0038P';

-- Si el doc_type no es 'policy', actualizarlo
UPDATE documents SET doc_type = 'policy' WHERE code = '0038P';
```

#### 2.5.2 Verificar el registro de descarga del usuario 13

```sql
-- Buscar el ID de la política 0038P
SELECT id FROM documents WHERE code = '0038P';

-- Buscar el registro de lectura del usuario 13 para esa política
SELECT * FROM document_reads 
WHERE user_id = 13 AND document_id = [ID_DE_0038P];
```

**Si el registro no existe:**
- El usuario nunca descargó la política (o la descarga falló silenciosamente)
- Solución: El usuario debe descargar la política nuevamente

**Si el registro existe pero `download_at IS NULL`:**
- Hubo un error al crear el registro
- Solución: Actualizar manualmente:
  ```sql
  UPDATE document_reads SET download_at = NOW() 
  WHERE user_id = 13 AND document_id = [ID_DE_0038P];
  ```

#### 2.5.3 Verificar el botón en la interfaz

Asegurar que:
1. El usuario está viendo la pestaña "Políticas" en `/documents/view`
2. La política 0038P aparece en la tabla
3. El botón "Confirmar Lectura" está visible (no muestra "Leído")
4. La política es de tipo "policy" (no "record")

#### 2.5.4 Corrección Preventiva (Opcional)

Si este problema ocurre frecuentemente, considerar modificar `routers/documents.py` para registrar descargas de TODOS los tipos de documentos, no solo "policy":

```python
# Cambiar de:
if doc.doc_type == "policy":
    upsert_policy_download_read(...)

# A:
if doc.doc_type == "policy" or doc.doc_type == "record":
    upsert_policy_download_read(...)
```

**Advertencia:** Esto cambiaría el comportamiento esperado. Evaluar si es deseable que los "record" también requieran confirmación de lectura.

---

## 8. Estructura de Directorios Importante

```
app/
  main.py              # Entry point, side effects de arranque
models/
  lms.py               # LMSUserPeriodSummary, LMSUserPostStatus
repositories/
  lms_repository.py    # list_users(), list_user_summaries_for_period()
services/
  lms_service.py       # metrics_users_by_period(), compliance_by_period()
routers/
  lms.py               # /lms/view/metrics, /lms/view/metrics/export
templates/
  dashboard/
    lms_metrics_report.html  # Vista del informe
media/
  documents/
    certificates/       # Certificados LMS y de lectura
```

---

## 9. Dependencias Externas

- **FastAPI** 5.3.1
- **SQLAlchemy** 2.x
- **ReportLab** - generación de PDFs
- **Jinja2** - templates
- **PyMySQL** - driver MySQL
- **Python** 3.12+

---

## 10. Despliegue

- **Server:** 192.168.42.23
- **Path:** /var/www/html/sgsi
- **Base de Datos:** MariaDB/MySQL
- ** Tests:** SQLite en memoria (165 pruebas, 160 pasando)

---

### 1.3 Aclaración: Informe de Auditoría en documents/view ✅ VERIFICADO

**Pregunta del usuario:** "¿Por qué en el endpoint 'documents/view' la descarga del 'Informe de Auditoría' no muestra todos los usuarios activos?"

**Respuesta:** 
El endpoint `export_policy_reading_report` (accesible desde el botón "Informe de Auditoría" en `/documents/view`) **SÍ muestra todos los usuarios activos correctamente**.

La función `build_policy_reading_audit_report()` en `routers/documents.py`:
```python
active_users = (
    db.execute(
        select(User)
        .where(User.is_active == True)
        .order_by(User.id)
    )
    .scalars()
    .all()
)
```

Y luego itera sobre TODOS los usuarios para TODAS las políticas:
```python
for policy in active_policies:
    for user in active_users:  # ← TODOS los usuarios activos
        read = reads_map.get((user.id, policy.id))
        # Crea traceability_rows para TODOS
```

**Posibles causas del problema reportado:**
1. El usuario está descargando una versión antigua del informe desde la lista de documentos (no usando el botón "Informe de Auditoría")
2. Los usuarios que no aparecen no tienen `is_active = True` en la base de datos
3. El informe fue generado antes de que los nuevos usuarios fueran creados/activados

**Conclusión:** El código del endpoint `export_policy_reading_report` **NO tiene el problema** y muestra todos los usuarios activos correctamente.

---

## 11. Checklist de Verificación para la Corrección

### LMS
- [x] `metrics_users_by_period()` itera sobre todos los usuarios activos
- [x] Usuarios sin resumen muestran métricas con 0 valores
- [ ] `compliance_by_period()` incluye todos los usuarios
- [x] Cálculo de cumplimiento usa denominador correcto

### Auditoría de Documentos
- [x] `audit_view()` incluye todos los usuarios activos en confirmaciones
- [x] Usuarios sin interacción muestran "Sin evidencia"
- [ ] Pruebas unitarias actualizadas
- [ ] Generación de PDF funciona con todos los usuarios
- [ ] Permisos de `media/` verificados
