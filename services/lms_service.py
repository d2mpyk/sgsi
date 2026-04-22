"""Servicios de negocio para LMS SGSI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import io
import os
import re
import hashlib

from reportlab.lib.colors import black, blue
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.lms import (
    LMSPeriod,
    LMSPost,
    LMSQuiz,
    LMSQuizAttempt,
    LMSQuizAttemptAnswer,
    LMSQuizOption,
    LMSQuizQuestion,
    LMSUserPeriodSummary,
    LMSUserPostStatus,
)
from models.users import User
from repositories.lms_repository import LMSRepository
from schemas.lms import (
    LMSAttemptSubmitRequest,
    LMSMetricPostItem,
    LMSMetricUserItem,
    LMSPeriodCreate,
    LMSPostCreate,
    LMSPostUpdate,
)


@dataclass
class CanAnswerResult:
    can_answer: bool
    reason: str
    attempts_used: int
    attempts_remaining: int
    max_attempts: int
    is_passed: bool
    is_blocked: bool


def _build_lms_certificate_storage_paths(
    user: User,
    post: LMSPost,
    attempt: LMSQuizAttempt,
) -> tuple[str, str, str]:
    safe_department = re.sub(r"[^a-zA-Z0-9_.-]", "_", user.department_name)
    safe_username = re.sub(r"[^a-zA-Z0-9_.-]", "_", user.username)
    safe_slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", post.slug or str(post.id))
    status_label = "APROBADO" if attempt.is_passed else "NO_APROBADO"
    timestamp_suffix = attempt.submitted_at.strftime("%Y%m%d_%H%M%S")
    filename = (
        f"Certificado_Evaluacion_{safe_slug}_{status_label}_{safe_department}_{safe_username}_{timestamp_suffix}.pdf"
    )
    relative_path = os.path.join("documents", "certificates", safe_department, filename)
    file_path = os.path.join("media", relative_path)
    return relative_path.replace("\\", "/"), file_path, filename


def _generate_lms_attempt_certificate_pdf(
    user: User,
    post: LMSPost,
    quiz: LMSQuiz,
    period: LMSPeriod,
    attempt: LMSQuizAttempt,
    certificate_record_code: str,
    certificate_url: str,
) -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    _, height = letter

    score_hash = hashlib.sha256(
        f"{user.id}-{post.id}-{attempt.id}-{attempt.score_percentage}".encode()
    ).hexdigest()[:32]
    submitted_at = attempt.submitted_at.strftime("%Y-%m-%d %H:%M:%S")
    result_label = "APROBADO" if attempt.is_passed else "NO APROBADO"

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "CERTIFICADO DE CUMPLIMIENTO - EVALUACION LMS SGSI")
    c.setFont("Helvetica", 10)

    y = height - 80
    line_height = 14
    lines = [
        "________________________________________________________________________________",
        "1. INFORMACIÓN DEL DOCUMENTO",
        f"Codigo de certificado: {certificate_record_code}",
        f"Fecha de generacion: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}",
        "________________________________________________________________________________",
        "2. IDENTIFICACIÓN DEL COLABORADOR",
        f"Nombre del Colaborador: {user.username} (ID: {user.id})",
        f"Correo corporativo: {user.email}",
        f"Departamento: {user.department_name}",
        f"Rol Sistema: {user.role}",
        "________________________________________________________________________________",
        "3. INFORMACIÓN DEL POST",
        f"Post LMS: {post.title}",
        f"Slug: {post.slug}",
        f"Version del post: {attempt.version_post}",
        f"Quiz: {quiz.title}",
        f"Version del quiz: {attempt.version_quiz}",
        f"Periodo: {period.name} ({period.start_date} a {period.end_date})",
        "________________________________________________________________________________",
        "4. RESULTADO DE LA EVALUACIÓN",
        f"Resultado: {result_label}",
        f"Puntaje: {attempt.score_percentage}%",
        f"Minimo aprobacion: {post.porcentaje_aprobacion}%",
        f"Respuestas correctas: {attempt.correct_answers} de {attempt.total_questions}",
        f"Intento numero: {attempt.attempt_number}",
        "________________________________________________________________________________",
        "5. EVIDENCIA DE ACEPTACIÓN DIGITAL",
        "Método de autenticación: Token",
        f"Dirección IP: {attempt.ip_origen or 'No disponible'}",
        f"Dispositivo/navegador: {(attempt.user_agent or 'No disponible')[:42]}",
        f"Fecha de evaluación: {submitted_at}",
        "________________________________________________________________________________",
        "6. FIRMA ELECTRÓNICA Y VALIDACIÓN",
        f"Firma digital (hash): {score_hash}",
        "Algoritmo: SHA-256",
        "________________________________________________________________________________",
        "7. CONTROL DE INTEGRIDAD Y TRAZABILIDAD",
        "Este registro incluye:",
        "Hash del registro generado",
        f"Identificador único (UUID) del post leído: {post.id}",
        "Registro en base de datos SGSI",
        "Log de evento en sistema",
        "Cualquier modificación posterior invalidará la integridad del documento.",
        "________________________________________________________________________________",
        "8. CONTROL DE REGISTRO",
        "Este documento:",
        "* Es generado automáticamente por el SGSI",
        "* Se almacena en repositorio controlado",
        "* Mantiene trazabilidad con:",
        "   * Usuario",
        "   * Post",
        "   * Versión",
        f"   * Fecha de evaluación: {submitted_at}",
        "Cumple con:",         
        "* ISO/IEC 27001:2022 – Cláusula 4.4",       
        "* ISO/IEC 27001:2022 – Cláusula 7.2",
        "* ISO/IEC 27001:2022 – Cláusula 7.3",
        "* ISO/IEC 27001:2022 – Cláusula 7.5",
        "* Control A.6.3",
        "________________________________________________________________________________",
        "9. CONFIDENCIALIDAD DEL REGISTRO",
        "Este documento contiene información confidencial y será tratado conforme a ",
        "las políticas de seguridad de la información y protección de datos personales de la organización.",
        "________________________________________________________________________________",
        "10. VALIDACIÓN DE AUTENTICIDAD",
        "Este documento puede ser validado mediante:",
        "* Comparación del hash SHA-256 REGISTRO DIGITAL DE LECTURA Y TÓPICO PUBLICADO",
        f"Hash de evidencia (SHA-256): {score_hash}",
        "",
    ]

    for line in lines:
        c.drawString(50, y, line)
        y -= line_height
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 50

    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "URL del certificado:")
    link_label = " CERTIFICADO"
    prefix_width = c.stringWidth("URL del certificado:", "Helvetica-Bold", 10)
    c.setFillColor(blue)
    c.drawString(50 + prefix_width + 4, y, link_label)
    link_width = c.stringWidth(link_label, "Helvetica-Bold", 10)
    c.linkURL(
        certificate_url,
        (
            50 + prefix_width + 4,
            y - 2,
            50 + prefix_width + 4 + link_width,
            y + 10,
        ),
        relative=0,
    )
    c.setFillColor(black)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def _save_lms_certificate_pdf(file_path: str, pdf_bytes: bytes) -> str:
    certificates_dir = os.path.dirname(file_path)
    os.makedirs(certificates_dir, exist_ok=True)
    with open(file_path, "wb") as certificate_file:
        certificate_file.write(pdf_bytes)
    return file_path


def _slugify(value: str) -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9áéíóúñü\s-]", "", normalized)
    normalized = normalized.replace("á", "a").replace("é", "e").replace("í", "i")
    normalized = normalized.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    normalized = normalized.replace("ü", "u")
    normalized = re.sub(r"[\s_-]+", "-", normalized)
    return normalized.strip("-")


def _get_semester_bounds(target_date: date) -> tuple[int, int, date, date, str]:
    year = target_date.year
    if target_date.month <= 6:
        semester = 1
        start_date = date(year, 1, 1)
        end_date = date(year, 6, 30)
    else:
        semester = 2
        start_date = date(year, 7, 1)
        end_date = date(year, 12, 31)
    name = f"{year}-S{semester}"
    return year, semester, start_date, end_date, name


def get_active_period(db: Session) -> LMSPeriod:
    """Retorna el período activo, creándolo/activándolo por semestre si aplica."""
    repo = LMSRepository(db)
    today = date.today()
    year, semester, start_date, end_date, name = _get_semester_bounds(today)

    current_period = repo.get_period_by_year_semester(year=year, semester=semester)
    if current_period is None:
        current_period = repo.create_period(
            LMSPeriod(
                name=name,
                year=year,
                semester=semester,
                start_date=start_date,
                end_date=end_date,
                is_active=True,
                activated_at=datetime.now(UTC),
            )
        )
        return current_period

    active = repo.get_active_period()
    if active is None or active.id != current_period.id:
        current_period = repo.activate_period(current_period)
    return current_period


def create_post(db: Session, payload: LMSPostCreate, created_by_id: int | None = None) -> LMSPost:
    repo = LMSRepository(db)
    slug = _slugify(payload.slug or payload.title)
    if repo.get_post_by_slug(slug):
        raise HTTPException(status_code=409, detail="Ya existe un post con ese slug.")
    post = LMSPost(
        title=payload.title,
        slug=slug,
        category=payload.category,
        version=payload.version,
        status=payload.status,
        html_content=payload.html_content,
        porcentaje_aprobacion=payload.porcentaje_aprobacion,
        max_intentos=payload.max_intentos,
        created_by_id=created_by_id,
    )
    return repo.create_post(post)


def update_post(db: Session, post_id: int, payload: LMSPostUpdate) -> LMSPost:
    repo = LMSRepository(db)
    post = repo.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post no encontrado")

    update_data = payload.model_dump(exclude_unset=True)
    if "slug" in update_data:
        normalized_slug = _slugify(update_data["slug"] or post.title)
        existing = repo.get_post_by_slug(normalized_slug)
        if existing and existing.id != post.id:
            raise HTTPException(status_code=409, detail="El slug ya está en uso.")
        update_data["slug"] = normalized_slug

    for field_name, value in update_data.items():
        setattr(post, field_name, value)
    return repo.save_post(post)


def get_next_attempt_number(db: Session, user_id: int, post_id: int, period_id: int) -> int:
    repo = LMSRepository(db)
    return repo.count_attempts(user_id=user_id, post_id=post_id, period_id=period_id) + 1


def can_user_answer_post(
    db: Session, user_id: int, post: LMSPost, period: LMSPeriod
) -> CanAnswerResult:
    repo = LMSRepository(db)
    status_row = repo.get_user_post_status(user_id=user_id, post_id=post.id, period_id=period.id)
    attempts_used = status_row.attempts_used if status_row else 0
    max_attempts = status_row.max_attempts if status_row else post.max_intentos
    is_passed = status_row.is_passed if status_row else False
    is_blocked = status_row.is_blocked if status_row else False
    attempts_remaining = max(0, max_attempts - attempts_used)

    if is_passed:
        return CanAnswerResult(
            can_answer=False,
            reason="Ya aprobaste este post en el semestre activo.",
            attempts_used=attempts_used,
            attempts_remaining=attempts_remaining,
            max_attempts=max_attempts,
            is_passed=True,
            is_blocked=False,
        )

    if is_blocked or attempts_used >= max_attempts:
        return CanAnswerResult(
            can_answer=False,
            reason="Intentos agotados para este semestre. Se habilita de nuevo en el próximo semestre.",
            attempts_used=attempts_used,
            attempts_remaining=0,
            max_attempts=max_attempts,
            is_passed=False,
            is_blocked=True,
        )

    return CanAnswerResult(
        can_answer=True,
        reason="Puedes presentar la evaluación.",
        attempts_used=attempts_used,
        attempts_remaining=attempts_remaining,
        max_attempts=max_attempts,
        is_passed=False,
        is_blocked=False,
    )


def grade_quiz(quiz: LMSQuiz, answers: dict[int, int | None]) -> tuple[int, int, float, list[LMSQuizAttemptAnswer]]:
    """Evalúa un quiz y retorna aciertos, total, score y respuestas auditables."""
    total_questions = 0
    correct_answers = 0
    answer_rows: list[LMSQuizAttemptAnswer] = []

    for question in quiz.questions:
        if not question.is_active:
            continue
        total_questions += 1
        selected_option_id = answers.get(question.id)
        correct_option = next((opt for opt in question.options if opt.is_correct), None)
        is_correct = bool(correct_option and selected_option_id == correct_option.id)
        if is_correct:
            correct_answers += 1
        answer_rows.append(
            LMSQuizAttemptAnswer(
                attempt_id=0,
                question_id=question.id,
                selected_option_id=selected_option_id,
                is_correct=is_correct,
            )
        )

    score = round((correct_answers / total_questions) * 100, 2) if total_questions else 0.0
    return correct_answers, total_questions, score, answer_rows


def refresh_user_post_status(
    db: Session, user_id: int, post: LMSPost, period: LMSPeriod
) -> LMSUserPostStatus:
    repo = LMSRepository(db)
    attempts = repo.list_attempts_user_post_period(
        user_id=user_id, post_id=post.id, period_id=period.id
    )
    attempts_used = len(attempts)
    passed_attempt = next((attempt for attempt in attempts if attempt.is_passed), None)
    is_passed = passed_attempt is not None
    is_blocked = (not is_passed) and attempts_used >= post.max_intentos
    last_attempt = attempts[-1] if attempts else None

    row = repo.get_user_post_status(user_id=user_id, post_id=post.id, period_id=period.id)
    if row is None:
        row = LMSUserPostStatus(
            user_id=user_id,
            post_id=post.id,
            period_id=period.id,
            max_attempts=post.max_intentos,
        )

    row.max_attempts = post.max_intentos
    row.attempts_used = attempts_used
    row.is_passed = is_passed
    row.is_blocked = is_blocked
    row.last_attempt_at = last_attempt.submitted_at if last_attempt else None
    row.passed_at = passed_attempt.submitted_at if passed_attempt else None
    row.blocked_at = datetime.now(UTC) if is_blocked else None
    return repo.save_user_post_status(row)


def refresh_user_period_summary(
    db: Session, user_id: int, period: LMSPeriod
) -> LMSUserPeriodSummary:
    repo = LMSRepository(db)
    posts = repo.list_published_posts()
    total_posts = len(posts)

    status_rows: list[LMSUserPostStatus] = []
    for post in posts:
        current_status = repo.get_user_post_status(user_id=user_id, post_id=post.id, period_id=period.id)
        if current_status is None:
            current_status = refresh_user_post_status(db=db, user_id=user_id, post=post, period=period)
        status_rows.append(current_status)

    approved_posts = len([row for row in status_rows if row.is_passed])
    failed_posts = len([row for row in status_rows if row.is_blocked and not row.is_passed])
    completed_posts = len([row for row in status_rows if row.attempts_used > 0 or row.is_passed])
    pending_posts = max(total_posts - approved_posts, 0)
    compliance = round((approved_posts / total_posts) * 100, 2) if total_posts else 0.0
    approval = compliance
    avg_attempts = (
        round(sum(row.attempts_used for row in status_rows) / total_posts, 2) if total_posts else 0.0
    )

    summary = repo.get_user_period_summary(user_id=user_id, period_id=period.id)
    if summary is None:
        summary = LMSUserPeriodSummary(user_id=user_id, period_id=period.id)

    summary.total_posts = total_posts
    summary.completed_posts = completed_posts
    summary.approved_posts = approved_posts
    summary.pending_posts = pending_posts
    summary.failed_posts = failed_posts
    summary.compliance_percentage = compliance
    summary.approval_percentage = approval
    summary.avg_attempts = avg_attempts
    return repo.save_user_period_summary(summary)


def submit_quiz_attempt(
    db: Session,
    user: User,
    post_id: int,
    payload: LMSAttemptSubmitRequest,
    ip_origen: str | None,
    user_agent: str | None,
) -> LMSQuizAttempt:
    repo = LMSRepository(db)
    post = repo.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    if post.status != "published":
        raise HTTPException(status_code=400, detail="El post no está publicado.")

    period = get_active_period(db)
    access = can_user_answer_post(db=db, user_id=user.id, post=post, period=period)
    if not access.can_answer:
        raise HTTPException(status_code=409, detail=access.reason)

    quiz = repo.get_active_quiz_for_post(post_id=post.id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz no configurado para este post.")

    answer_map = {answer.question_id: answer.option_id for answer in payload.answers}
    correct_answers, total_questions, score, answer_rows = grade_quiz(quiz=quiz, answers=answer_map)
    is_passed = score >= post.porcentaje_aprobacion
    attempt_number = get_next_attempt_number(
        db=db, user_id=user.id, post_id=post.id, period_id=period.id
    )

    attempt = LMSQuizAttempt(
        user_id=user.id,
        post_id=post.id,
        quiz_id=quiz.id,
        period_id=period.id,
        attempt_number=attempt_number,
        total_questions=total_questions,
        correct_answers=correct_answers,
        score_percentage=score,
        is_passed=is_passed,
        ip_origen=ip_origen,
        user_agent=user_agent,
        version_post=post.version,
        version_quiz=quiz.version,
        started_at=datetime.now(UTC),
        submitted_at=datetime.now(UTC),
    )
    saved_attempt = repo.create_attempt(attempt=attempt, answers=answer_rows)
    refresh_user_post_status(db=db, user_id=user.id, post=post, period=period)
    refresh_user_period_summary(db=db, user_id=user.id, period=period)

    certificate_relative_path, certificate_path, certificate_filename = (
        _build_lms_certificate_storage_paths(user=user, post=post, attempt=saved_attempt)
    )
    certificate_url = f"/media/{certificate_relative_path}"
    certificate_record_code = (
        f"REG-LMS-{post.id}-{user.id}-{saved_attempt.id}-{int(saved_attempt.submitted_at.timestamp())}"
    )
    certificate_buffer = _generate_lms_attempt_certificate_pdf(
        user=user,
        post=post,
        quiz=quiz,
        period=period,
        attempt=saved_attempt,
        certificate_record_code=certificate_record_code,
        certificate_url=certificate_url,
    )
    _save_lms_certificate_pdf(
        file_path=certificate_path,
        pdf_bytes=certificate_buffer.getvalue(),
    )
    saved_attempt.certificate_filename = certificate_filename
    saved_attempt.certificate_relative_path = certificate_relative_path
    return saved_attempt


def dashboard_by_user(db: Session, user_id: int) -> dict:
    repo = LMSRepository(db)
    period = get_active_period(db)
    user = repo.db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    posts = repo.list_published_posts()
    items = []
    for post in posts:
        status_row = refresh_user_post_status(db=db, user_id=user_id, post=post, period=period)
        can_answer_result = can_user_answer_post(db=db, user_id=user_id, post=post, period=period)
        items.append(
            {
                "post_id": post.id,
                "slug": post.slug,
                "title": post.title,
                "category": post.category,
                "version": post.version,
                "status": post.status,
                "attempts_used": status_row.attempts_used,
                "attempts_remaining": can_answer_result.attempts_remaining,
                "is_passed": status_row.is_passed,
                "is_blocked": status_row.is_blocked,
                "can_answer": can_answer_result.can_answer,
                "reason": can_answer_result.reason,
            }
        )

    summary = refresh_user_period_summary(db=db, user_id=user_id, period=period)
    return {"period": period, "summary": summary, "posts": items}


def metrics_by_period(db: Session, period_id: int) -> dict:
    repo = LMSRepository(db)
    period = repo.get_period(period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Período no encontrado")

    attempts = repo.list_period_posts(period_id=period.id)
    status_rows = repo.list_statuses_for_period(period_id=period.id)
    users = repo.list_users()
    posts = repo.list_published_posts()

    total_users = len(users)
    total_posts = len(posts)
    total_attempts = len(attempts)
    approved_attempts = len([attempt for attempt in attempts if attempt.is_passed])
    cumplimiento = (
        round((len([row for row in status_rows if row.is_passed]) / (total_users * total_posts)) * 100, 2)
        if total_users and total_posts
        else 0.0
    )
    aprobacion = round((approved_attempts / total_attempts) * 100, 2) if total_attempts else 0.0
    promedio_intentos = (
        round(sum(attempt.attempt_number for attempt in attempts) / total_attempts, 2)
        if total_attempts
        else 0.0
    )

    first_pass = len([attempt for attempt in attempts if attempt.is_passed and attempt.attempt_number == 1])
    second_pass = len([attempt for attempt in attempts if attempt.is_passed and attempt.attempt_number == 2])
    third_pass = len([attempt for attempt in attempts if attempt.is_passed and attempt.attempt_number == 3])
    denom_pass = approved_attempts or 1

    users_pending = len([row for row in status_rows if not row.is_passed])
    return {
        "period": period,
        "kpis": {
            "period_id": period.id,
            "total_users": total_users,
            "total_posts": total_posts,
            "total_attempts": total_attempts,
            "total_approved_attempts": approved_attempts,
            "cumplimiento_porcentaje": cumplimiento,
            "aprobacion_porcentaje": aprobacion,
            "promedio_intentos": promedio_intentos,
            "aprobacion_primer_intento": round((first_pass / denom_pass) * 100, 2),
            "aprobacion_segundo_intento": round((second_pass / denom_pass) * 100, 2),
            "aprobacion_tercer_intento": round((third_pass / denom_pass) * 100, 2),
            "usuarios_pendientes": users_pending,
        },
    }


def metrics_posts_by_period(db: Session, period_id: int) -> list[LMSMetricPostItem]:
    repo = LMSRepository(db)
    attempts = repo.list_period_posts(period_id=period_id)
    posts = {post.id: post for post in repo.list_published_posts()}

    by_post: dict[int, list[LMSQuizAttempt]] = {}
    for attempt in attempts:
        by_post.setdefault(attempt.post_id, []).append(attempt)

    result: list[LMSMetricPostItem] = []
    for post_id, post_attempts in by_post.items():
        post = posts.get(post_id)
        if post is None:
            continue
        total_attempts = len(post_attempts)
        approved_attempts = len([attempt for attempt in post_attempts if attempt.is_passed])
        failed_attempts = total_attempts - approved_attempts
        approval_rate = round((approved_attempts / total_attempts) * 100, 2) if total_attempts else 0.0
        avg_attempt = (
            round(sum(attempt.attempt_number for attempt in post_attempts) / total_attempts, 2)
            if total_attempts
            else 0.0
        )
        difficulty = round(100 - approval_rate, 2)
        result.append(
            LMSMetricPostItem(
                post_id=post.id,
                slug=post.slug,
                title=post.title,
                total_attempts=total_attempts,
                approved_attempts=approved_attempts,
                failed_attempts=failed_attempts,
                approval_rate=approval_rate,
                avg_attempt_number=avg_attempt,
                difficulty_score=difficulty,
            )
        )
    return sorted(result, key=lambda item: item.difficulty_score, reverse=True)


def metrics_users_by_period(db: Session, period_id: int) -> list[LMSMetricUserItem]:
    repo = LMSRepository(db)
    users = {user.id: user for user in repo.list_users()}
    summaries = repo.list_user_summaries_for_period(period_id=period_id)
    result: list[LMSMetricUserItem] = []
    for summary in summaries:
        user = users.get(summary.user_id)
        if user is None:
            continue
        result.append(
            LMSMetricUserItem(
                user_id=user.id,
                username=user.username,
                total_posts=summary.total_posts,
                approved_posts=summary.approved_posts,
                pending_posts=summary.pending_posts,
                compliance_percentage=summary.compliance_percentage,
                approval_percentage=summary.approval_percentage,
            )
        )
    return sorted(result, key=lambda item: item.compliance_percentage, reverse=True)


def compliance_by_period(db: Session, period_id: int) -> list[dict]:
    repo = LMSRepository(db)
    period = repo.get_period(period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Período no encontrado")

    posts = repo.list_published_posts()
    users = repo.list_users()
    statuses = repo.list_statuses_for_period(period_id=period_id)
    total_users = len(users)

    by_post: dict[int, list[LMSUserPostStatus]] = {}
    for status_row in statuses:
        by_post.setdefault(status_row.post_id, []).append(status_row)

    result = []
    for post in posts:
        rows = by_post.get(post.id, [])
        approved = len([row for row in rows if row.is_passed])
        pending = max(total_users - approved, 0)
        compliance = round((approved / total_users) * 100, 2) if total_users else 0.0
        result.append(
            {
                "post_id": post.id,
                "slug": post.slug,
                "title": post.title,
                "users_expected": total_users,
                "users_approved": approved,
                "users_pending": pending,
                "compliance_percentage": compliance,
            }
        )
    return result


def create_or_activate_period(db: Session, payload: LMSPeriodCreate) -> LMSPeriod:
    repo = LMSRepository(db)
    existing = repo.get_period_by_year_semester(year=payload.year, semester=payload.semester)
    if existing:
        raise HTTPException(status_code=409, detail="El período ya existe.")
    period = repo.create_period(
        LMSPeriod(
            name=payload.name,
            year=payload.year,
            semester=payload.semester,
            start_date=payload.start_date,
            end_date=payload.end_date,
            is_active=False,
        )
    )
    if payload.is_active:
        period = repo.activate_period(period)
    return period


def activate_period(db: Session, period_id: int) -> LMSPeriod:
    repo = LMSRepository(db)
    period = repo.get_period(period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Período no encontrado")
    return repo.activate_period(period)


def activate_post(db: Session, post_id: int) -> LMSPost:
    repo = LMSRepository(db)
    post = repo.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    post.status = "published"
    return repo.save_post(post)


def activate_quiz(db: Session, quiz_id: int) -> LMSQuiz:
    repo = LMSRepository(db)
    quiz = repo.get_quiz_by_id(quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")
    return repo.activate_quiz(quiz)


def upsert_quiz(db: Session, post_id: int, title: str, instructions: str, version: str, is_active: bool, questions: list[dict]) -> LMSQuiz:
    repo = LMSRepository(db)
    post = repo.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post no encontrado")

    if is_active:
        repo.deactivate_quizzes_for_post(post_id=post_id)

    quiz = LMSQuiz(
        post_id=post_id,
        title=title,
        instructions=instructions,
        version=version,
        is_active=is_active,
    )

    for question_data in questions:
        question = LMSQuizQuestion(
            question_order=question_data["question_order"],
            statement=question_data["statement"],
            weight=question_data.get("weight", 1.0),
            is_active=True,
        )
        for option_data in question_data["options"]:
            question.options.append(
                LMSQuizOption(
                    option_order=option_data["option_order"],
                    option_text=option_data["option_text"],
                    is_correct=option_data["is_correct"],
                )
            )
        quiz.questions.append(question)

    saved = repo.create_quiz(quiz)
    return repo.get_active_quiz_for_post(post_id=post_id) if saved.is_active else saved
