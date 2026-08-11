"""Genera y migra los quizzes LMS V2 de forma idempotente y transaccional.

Uso:
    python scripts/migrate_lms_quizzes_v2.py --dry-run
    python scripts/migrate_lms_quizzes_v2.py --apply

La operación conserva V1, intentos, respuestas y certificados. Solo V2 se
activa y la migración se revierte completa si cualquier post no coincide.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.lms import LMSPost, LMSQuiz, LMSQuizOption, LMSQuizQuestion
from utils.database import SessionLocal


SOURCE = ROOT / "utils" / "bootstrap" / "lms_bootstrap_data.json"
CORRECT_POSITIONS = (5, 4, 3, 2, 1)


# Cada tupla contiene: enunciado, respuesta correcta y cuatro distractores.
QUESTION_BANK: dict[str, list[tuple[str, str, list[str]]]] = {
    "fundamentos-del-sgsi": [
        ("¿Qué resultado busca un SGSI bien implementado?", "Proteger la información mediante riesgos, controles y mejora continua", ["Eliminar toda actividad operativa", "Aplicar seguridad solo a servidores", "Cumplir auditorías sin medir riesgos", "Delegar la seguridad en un único cargo"]),
        ("¿Quién participa en la protección de la información?", "Todas las personas que crean, usan o administran información", ["Solo el equipo de tecnología", "Solo la alta dirección", "Solo quienes auditan", "Solo los administradores de servidores"]),
        ("¿Cuál es una conducta esperada de un colaborador?", "Reportar oportunamente incidentes o comportamientos sospechosos", ["Compartir credenciales ante una urgencia", "Guardar información sensible en canales personales", "Ignorar controles durante horas de alta demanda", "Evitar reportes para no generar trabajo"]),
        ("¿Qué elementos forman la triada CIA?", "Confidencialidad, integridad y disponibilidad", ["Cumplimiento, inspección y auditoría", "Control, implementación y administración", "Calidad, innovación y ahorro", "Continuidad, inventario y acceso"]),
        ("¿Qué puede provocar incumplir prácticas de seguridad?", "Exposición de información, interrupciones y pérdida de confianza", ["Eliminación automática de riesgos", "Reducción garantizada de incidentes", "Desaparición de obligaciones legales", "Ningún impacto si continúa la operación"]),
    ],
    "alcance-y-contexto-del-sgsi": [
        ("¿Qué delimita el alcance del SGSI?", "Procesos, activos, personas, ubicaciones y tecnologías cubiertos", ["Solo los equipos de tecnología", "Únicamente las actividades de recursos humanos", "Solo los contratos comerciales", "Exclusivamente los servidores internos"]),
        ("¿Qué beneficio aporta conocer el alcance?", "Aclara responsabilidades y facilita la aplicación de controles", ["Elimina todos los riesgos", "Reemplaza la gestión de riesgos", "Evita capacitar al personal", "Hace innecesarias las auditorías"]),
        ("¿Qué práctica es adecuada durante el trabajo remoto?", "Usar redes confiables y proteger física y lógicamente el equipo", ["Compartir el equipo con familiares", "Desactivar el bloqueo de pantalla", "Guardar claves en notas visibles", "Usar cualquier red pública sin protección"]),
        ("¿Cuándo puede considerarse crítico un activo?", "Cuando su compromiso afecta la operación, el cumplimiento o la reputación", ["Cuando lo usa una sola persona", "Cuando está en una carpeta compartida", "Cuando no tiene clasificación", "Cuando no contiene datos personales"]),
        ("¿Cómo ayuda el contexto del SGSI al trabajo diario?", "Permite seleccionar controles según el proceso y la información", ["Limita la seguridad al área técnica", "Evita clasificar la información", "Reemplaza las políticas", "Elimina la necesidad de reportar riesgos"]),
    ],
    "marco-legal-y-cumplimiento": [
        ("¿Qué es un dato personal?", "Información que identifica o puede identificar a una persona", ["Solo datos de servidores", "Cualquier dato público sin restricciones", "Solo números de tickets", "Únicamente información financiera"]),
        ("¿Cómo debe tratarse un dato personal?", "Solo para fines autorizados y con acceso protegido", ["Compartido por cualquier mensajería", "Copiado a dispositivos personales", "Usado para fines distintos sin aprobación", "Publicado para facilitar la operación"]),
        ("¿Qué hacer ante un incidente que involucre datos?", "Notificarlo por el flujo definido y conservar la evidencia", ["Esperar al cierre del semestre", "Resolverlo sin registrar información", "Compartirlo en un canal informal", "Eliminar los registros para evitar exposición"]),
        ("¿Por qué el cumplimiento legal involucra a todas las áreas?", "Porque muchas áreas recopilan, usan o custodian información personal", ["Porque solo el área jurídica responde", "Porque solo aplica a auditorías externas", "Porque excluye la atención al cliente", "Porque solo afecta a proveedores"]),
        ("¿Qué práctica reduce el riesgo legal sobre datos personales?", "Limitar el tratamiento al rol y propósito autorizado", ["Crear copias sin control", "Compartir bases por canales no autorizados", "Usar datos para cualquier finalidad", "Conservar información indefinidamente"]),
    ],
    "concientizacion-en-seguridad-a63": [
        ("¿Cuál es el objetivo de la concientización A.6.3?", "Fortalecer conductas seguras y reducir errores humanos", ["Sustituir todos los controles técnicos", "Capacitar únicamente a tecnología", "Delegar seguridad al proveedor", "Reducir la cantidad de reportes"]),
        ("¿Cuál es un error humano frecuente?", "Abrir enlaces o adjuntos maliciosos en mensajes de phishing", ["Bloquear la sesión al ausentarse", "Reportar una actividad sospechosa", "Usar autenticación corporativa", "Verificar un remitente por canal oficial"]),
        ("¿Qué conducta fortalece la cultura de seguridad?", "Seguir políticas, usar sistemas autorizados y reportar incidentes", ["Compartir contraseñas", "Desactivar controles", "Evitar reportes", "Usar aplicaciones personales sin aprobación"]),
        ("¿Qué hacer al detectar una situación sospechosa?", "Reportarla de inmediato mediante el canal oficial", ["Ignorarla si no hay impacto visible", "Publicarla en redes sociales", "Esperar confirmación de compañeros", "Borrar la evidencia"]),
        ("¿Qué resultado se espera de la concientización?", "Menos incidentes por error humano y mejor capacidad de respuesta", ["Eliminar controles técnicos", "Delegar todo en gerencia", "Reducir la capacitación", "Evitar medir el comportamiento"]),
    ],
    "roles-y-responsabilidades": [
        ("¿Qué responsabilidad tiene la alta dirección?", "Definir orientación de seguridad y asignar recursos", ["Administrar todas las contraseñas", "Resolver cada incidente operativo", "Aprobar únicamente infraestructura", "Reemplazar a los líderes de proceso"]),
        ("¿Qué función cumple el responsable del SGSI?", "Coordinar riesgos, controles, auditorías y seguimiento", ["Gestionar solo compras", "Autorizar vacaciones", "Reemplazar a todas las áreas", "Administrar únicamente servidores"]),
        ("¿Qué deben hacer los líderes de área?", "Aplicar controles y asegurar el cumplimiento en su proceso", ["Delegar toda la seguridad a TI", "Excluir al equipo de capacitación", "Usar canales informales", "Omitir controles en fechas de cierre"]),
        ("¿Qué se espera de cada colaborador?", "Cumplir políticas y reportar incidentes oportunamente", ["Compartir accesos", "Omitir controles con alta demanda", "Aplicar solo controles técnicos", "Delegar toda responsabilidad al jefe"]),
        ("¿Qué beneficio produce la claridad de roles?", "Coordinación, trazabilidad y cumplimiento sostenido", ["Duplicar tareas sin responsables", "Concentrar decisiones en una persona", "Reducir comunicación de incidentes", "Eliminar revisiones de cumplimiento"]),
    ],
    "proceso-sgsi-pdca": [
        ("¿Qué representa PDCA?", "Planificar, hacer, verificar y actuar para mejorar", ["Proteger, detectar, corregir y aislar", "Programar, diseñar, controlar y auditar", "Priorizar, delegar, comunicar y aprobar", "Prevenir, documentar, clasificar y archivar"]),
        ("¿Qué actividad corresponde a PLAN?", "Identificar activos, amenazas y riesgos", ["Cerrar hallazgos sin analizarlos", "Ejecutar recuperación en producción", "Publicar métricas finales", "Eliminar evidencias anteriores"]),
        ("¿Qué representa CHECK?", "Monitorear, medir y auditar el desempeño", ["Desactivar controles", "Crear puestos de trabajo", "Eliminar registros", "Cambiar políticas sin evidencia"]),
        ("¿Qué busca ACT?", "Aplicar acciones correctivas y preventivas", ["Repetir el ciclo sin cambios", "Cerrar el SGSI", "Suspender la gestión de riesgos", "Eliminar la medición"]),
        ("¿Qué evidencia muestra que PDCA funciona?", "Mejoras implementadas a partir de métricas y hallazgos", ["Ausencia de registros", "Controles nunca revisados", "Cambios sin evaluación", "Políticas sin responsables"]),
    ],
    "riesgos-de-seguridad": [
        ("¿Cuál es un riesgo frecuente del teletrabajo?", "Acceso no autorizado por sesiones abiertas o equipos compartidos", ["Usar MFA", "Bloquear automáticamente la pantalla", "Actualizar el router", "Usar contraseñas robustas"]),
        ("¿Qué mejora la seguridad de una red doméstica?", "Usar WPA2/WPA3 y cambiar credenciales predeterminadas", ["Conservar la clave de fábrica", "Usar cualquier red pública", "Desactivar el cifrado", "Compartir la clave con terceros"]),
        ("¿Cuál es una señal de phishing?", "Urgencia inusual, enlace sospechoso o remitente no esperado", ["Canal interno verificado", "Aviso oficial autenticado", "Recordatorio del LMS", "Correo esperado sin enlaces"]),
        ("¿Cómo se reduce una fuga de información?", "Aplicando clasificación y canales autorizados", ["Usando cuentas personales", "Compartiendo accesos", "Evitando registrar incidentes", "Enviando archivos sin cifrado"]),
        ("¿Qué reduce el acceso no autorizado?", "Bloquear el equipo y cerrar sesión al ausentarse", ["Mantener la sesión abierta", "Compartir el usuario", "Guardar claves en texto plano", "Desactivar el bloqueo"]),
    ],
    "controles-de-seguridad-soa": [
        ("¿Qué es la SoA?", "La declaración de aplicabilidad de los controles seleccionados", ["Un inventario físico", "Un plan de vacaciones", "Un listado de incidentes", "Un registro de proveedores"]),
        ("¿Qué busca una política de seguridad?", "Definir reglas, responsabilidades y orientación organizacional", ["Eliminar la capacitación", "Aplicar controles solo a proveedores", "Reemplazar auditorías", "Limitar controles al área técnica"]),
        ("¿Qué implica gestionar seguridad con proveedores?", "Evaluar riesgos de terceros y establecer acuerdos de seguridad", ["Confiar sin evaluar", "Compartir datos sin controles", "Excluir el seguimiento", "Delegar toda responsabilidad"]),
        ("¿Qué busca la continuidad del negocio?", "Mantener y recuperar la operación ante interrupciones", ["Suspender servicios menores", "Limitar controles al horario laboral", "Evitar pruebas", "Eliminar planes alternos"]),
        ("¿Por qué la SoA ayuda en auditoría?", "Justifica qué controles aplican y cómo se implementan", ["Reemplaza las políticas", "Elimina evidencias", "Solo inventaría incidentes", "Evita medir controles"]),
    ],
    "uso-de-plataformas-sgsi": [
        ("¿Cuál es el propósito del LMS?", "Capacitar, evaluar y registrar el cumplimiento", ["Reemplazar políticas", "Gestionar solo perfiles técnicos", "Eliminar auditorías", "Sustituir controles de acceso"]),
        ("¿Qué evidencia produce la lectura de una política?", "Registro trazable de lectura y cumplimiento por usuario", ["Un correo sin auditoría", "Un archivo local sin fecha", "Una confirmación verbal", "Un registro sin identidad"]),
        ("¿Por qué es importante la trazabilidad?", "Permite demostrar seguimiento histórico y auditoría", ["Evita documentar actividades", "Reemplaza controles de acceso", "Solo aplica a gerencia", "Elimina la necesidad de reportes"]),
        ("¿Qué uso de la plataforma es correcto?", "Consultar políticas vigentes y completar actividades obligatorias", ["Compartir cuentas", "Registrar cumplimiento sin leer", "Usar plataformas no autorizadas", "Omitir confirmaciones"]),
        ("¿Qué conducta preserva mejor la evidencia?", "Completar actividades con la cuenta propia y conservar registros", ["Usar cuentas compartidas", "Omitir confirmaciones", "Registrar sin revisar", "Borrar certificados"]),
    ],
    "cumplimiento-y-auditoria": [
        ("¿Para qué sirven los KPI del SGSI?", "Medir cumplimiento y efectividad para tomar decisiones", ["Reemplazar auditorías", "Evaluar solo ventas", "Evitar registrar incidentes", "Medir únicamente reuniones"]),
        ("¿Qué indicador mide capacitación?", "Porcentaje de colaboradores que completan y aprueban actividades", ["Cantidad de publicaciones", "Costo de mobiliario", "Horas de reuniones", "Número de correos enviados"]),
        ("¿Qué es evidencia válida para auditoría?", "Registros de capacitación, incidentes y revisiones documentadas", ["Comentarios verbales", "Archivos sin fecha", "Mensajes eliminados", "Opiniones sin responsable"]),
        ("¿Qué puede causar incumplir políticas?", "No conformidades, mayor riesgo e impactos reputacionales", ["Mejora automática", "Reducción total de incidentes", "Eliminación de auditorías", "Menor necesidad de controles"]),
        ("¿Cómo apoyan los KPI la mejora continua?", "Permiten identificar brechas y priorizar acciones", ["Reemplazan el análisis de incidentes", "Solo se revisan al certificar", "No tienen relación con auditorías", "Eliminan la evaluación de impacto"]),
    ],
}


def build_questions(slug: str) -> list[dict]:
    rows = QUESTION_BANK[slug]
    if len(rows) != 5:
        raise ValueError(f"{slug}: se esperaban 5 preguntas")
    result = []
    for order, (statement, correct, distractors) in enumerate(rows, start=1):
        if len(distractors) != 4:
            raise ValueError(f"{slug} pregunta {order}: se esperaban 4 distractores")
        correct_position = CORRECT_POSITIONS[order - 1]
        answers = iter(distractors)
        options = []
        for option_order in range(1, 6):
            is_correct = option_order == correct_position
            options.append({
                "option_order": option_order,
                "option_text": correct if is_correct else next(answers),
                "is_correct": is_correct,
            })
        result.append({"question_order": order, "statement": statement, "weight": 1.0, "options": options})
    return result


def load_payload() -> dict:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    quiz_by_slug = {item["post_slug"]: item for item in payload["quizzes"]}
    if set(quiz_by_slug) != set(QUESTION_BANK):
        raise ValueError("Los slugs del banco V2 no coinciden con el snapshot actual")
    quizzes = []
    for slug, questions in QUESTION_BANK.items():
        old = quiz_by_slug[slug]
        quizzes.append({
            "post_slug": slug,
            "title": old.get("title", f"Evaluación - {slug}"),
            "instructions": old.get("instructions", ""),
            "version": "2.0",
            "is_active": True,
            "questions": build_questions(slug),
        })
    return {"source": str(SOURCE.relative_to(ROOT)), "quizzes": quizzes}


def validate_payload(payload: dict) -> None:
    if len(payload["quizzes"]) != 10:
        raise ValueError("V2 debe contener 10 quizzes")
    for quiz in payload["quizzes"]:
        if quiz["version"] != "2.0" or len(quiz["questions"]) != 5:
            raise ValueError(f"Quiz inválido: {quiz['post_slug']}")
        for index, question in enumerate(quiz["questions"]):
            options = question["options"]
            correct = [option["option_order"] for option in options if option["is_correct"]]
            if len(options) != 5 or correct != [CORRECT_POSITIONS[index]]:
                raise ValueError(f"Opciones inválidas: {quiz['post_slug']} pregunta {index + 1}")


def migrate(payload: dict, apply: bool) -> None:
    with SessionLocal.begin() as db:
        posts = {post.slug: post for post in db.scalars(select(LMSPost)).all()}
        if set(posts) & set(QUESTION_BANK) != set(QUESTION_BANK):
            missing = sorted(set(QUESTION_BANK) - set(posts))
            raise RuntimeError(f"Faltan posts requeridos: {', '.join(missing)}")
        for item in payload["quizzes"]:
            post = posts[item["post_slug"]]
            existing = db.scalar(select(LMSQuiz).where(LMSQuiz.post_id == post.id, LMSQuiz.version == "2.0"))
            if existing is None:
                if not apply:
                    print(f"CREAR V2: {post.slug}")
                    continue
                for active in db.scalars(select(LMSQuiz).where(LMSQuiz.post_id == post.id, LMSQuiz.is_active.is_(True))).all():
                    active.is_active = False
                quiz = LMSQuiz(post_id=post.id, title=item["title"], instructions=item["instructions"], version="2.0", is_active=True)
                for question_data in item["questions"]:
                    question = LMSQuizQuestion(question_order=question_data["question_order"], statement=question_data["statement"], weight=1.0, is_active=True)
                    question.options = [LMSQuizOption(**option) for option in question_data["options"]]
                    quiz.questions.append(question)
                db.add(quiz)
                print(f"CREADO V2: {post.slug}")
            elif apply and not existing.is_active:
                for active in db.scalars(select(LMSQuiz).where(LMSQuiz.post_id == post.id, LMSQuiz.is_active.is_(True))).all():
                    active.is_active = False
                existing.is_active = True
                print(f"ACTIVADO V2 EXISTENTE: {post.slug}")
            else:
                print(f"OMITIDO V2 EXISTENTE: {post.slug}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica la migración a la base configurada")
    args = parser.parse_args()
    payload = load_payload()
    validate_payload(payload)
    print("Dataset V2 válido: 10 quizzes, 50 preguntas, 250 opciones")
    migrate(payload, apply=args.apply)
    if not args.apply:
        print("DRY-RUN: no se modificó la base de datos. Use --apply para ejecutar.")


if __name__ == "__main__":
    main()
