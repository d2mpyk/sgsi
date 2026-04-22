"""Router de LMS SGSI."""
from __future__ import annotations

import io
from datetime import UTC, datetime
import json
import os
import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.documents import Document
from repositories.lms_repository import LMSRepository
from schemas.lms import (
    LMSAttemptResponse,
    LMSAttemptSubmitRequest,
    LMSComplianceItem,
    LMSPeriodCreate,
    LMSPeriodMetrics,
    LMSPeriodResponse,
    LMSPostCreate,
    LMSPostResponse,
    LMSPostUpdate,
    LMSQuizCreate,
    LMSQuizResponse,
    LMSUserDashboardResponse,
    LMSUserPostStatusResponse,
)
from services import lms_service
from utils.auth import CurrentAdmin, CurrentAuditorOrAdmin, CurrentUser
from utils.config import get_settings
from utils.database import get_db
from utils.stats import get_dashboard_stats

router = APIRouter(prefix="/lms", tags=["LMS"])
templates = Jinja2Templates(directory="templates")
settings = get_settings()

LMS_METRICS_REPORT_DOC_CODE = "REP-AUD-LMS"
LMS_METRICS_REPORT_DOC_TITLE = "Informe de Estado de Cumplimiento de Evaluaciones SGSI"


def _build_lms_metrics_context(db: Session, responsible_username: str) -> dict:
    period = lms_service.get_active_period(db)
    metrics_payload = lms_service.metrics_by_period(db=db, period_id=period.id)
    kpis = metrics_payload["kpis"]
    post_rows = lms_service.metrics_posts_by_period(db=db, period_id=period.id)
    user_rows = lms_service.metrics_users_by_period(db=db, period_id=period.id)
    compliance_rows = lms_service.compliance_by_period(db=db, period_id=period.id)
    hardest_posts = post_rows[:5]
    users_pending = sorted(user_rows, key=lambda row: row.pending_posts, reverse=True)[:5]
    generated_at = datetime.now(UTC)
    return {
        "period": period,
        "kpis": kpis,
        "post_rows": post_rows,
        "user_rows": user_rows,
        "compliance_rows": compliance_rows,
        "hardest_posts": hardest_posts,
        "users_pending": users_pending,
        "generated_at": generated_at,
        "company_name": settings.COMPANY_NAME.get_secret_value(),
        "project_name": settings.PROJECT_NAME.get_secret_value(),
        "responsible_username": responsible_username,
    }


def _calculate_next_lms_report_version(db: Session) -> str:
    previous_docs = (
        db.execute(
            select(Document)
            .where(Document.code == LMS_METRICS_REPORT_DOC_CODE)
            .order_by(Document.created_at.desc(), Document.id.desc())
        )
        .scalars()
        .all()
    )
    if not previous_docs:
        return "1.0"

    max_version = 0
    for existing in previous_docs:
        match = re.match(r"^(\d+)(?:\.(\d+))?$", existing.version or "")
        if not match:
            continue
        major = int(match.group(1))
        max_version = max(max_version, major)
    return f"{(max_version or len(previous_docs)) + 1}.0"


def _persist_lms_report_as_document(
    db: Session,
    generated_by_id: int,
    pdf_bytes: bytes,
    report_version: str,
) -> Document:
    upload_dir = "media/documents"
    os.makedirs(upload_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "Informe_Cumplimiento_Evaluaciones_SGSI"
    stored_filename = f"{uuid.uuid4()}.pdf"
    stored_path = os.path.join(upload_dir, stored_filename)

    with open(stored_path, "wb") as report_file:
        report_file.write(pdf_bytes)

    active_docs = (
        db.execute(
            select(Document).where(
                Document.code == LMS_METRICS_REPORT_DOC_CODE,
                Document.is_active == True,
            )
        )
        .scalars()
        .all()
    )
    for doc in active_docs:
        doc.is_active = False

    new_doc = Document(
        title=LMS_METRICS_REPORT_DOC_TITLE,
        description=(
            "Informe LMS generado automáticamente desde la vista de métricas.\n"
            f"{safe_title}_{timestamp}.pdf"
        ),
        version=report_version,
        code=LMS_METRICS_REPORT_DOC_CODE,
        doc_type="record",
        filename=stored_filename,
        content_type="application/pdf",
        uploaded_by_id=generated_by_id,
        is_active=True,
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    return new_doc


def _generate_lms_metrics_report_pdf(report_context: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=32,
        rightMargin=32,
        topMargin=32,
        bottomMargin=32,
        title=LMS_METRICS_REPORT_DOC_TITLE,
        author=report_context["responsible_username"],
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LmsTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0f2742"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "LmsSection",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#1e4c89"),
        spaceBefore=10,
        spaceAfter=6,
    )

    def p(value: object) -> Paragraph:
        return Paragraph(str(value), styles["BodyText"])

    story: list = [
        Paragraph(LMS_METRICS_REPORT_DOC_TITLE, title_style),
        p(f"Organización: {report_context['company_name']}"),
        p(f"Proyecto: {report_context['project_name']}"),
        p(f"Período: {report_context['period'].name} ({report_context['period'].start_date} a {report_context['period'].end_date})"),
        p(f"Fecha de emisión: {report_context['generated_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}"),
        p(f"Responsable: {report_context['responsible_username']}"),
        Spacer(1, 8),
        Paragraph("KPIs del Período", section_style),
    ]

    kpis = report_context["kpis"]
    kpi_table = Table(
        [
            ["Cumplimiento", "Aprobación", "Intentos", "Usuarios", "Posts", "Pendientes"],
            [
                f"{kpis['cumplimiento_porcentaje']}%",
                f"{kpis['aprobacion_porcentaje']}%",
                str(kpis["total_attempts"]),
                str(kpis["total_users"]),
                str(kpis["total_posts"]),
                str(kpis["usuarios_pendientes"]),
            ],
        ]
    )
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf1f8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d2dbe7")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.extend([kpi_table, Spacer(1, 8), Paragraph("Detalle por Post", section_style)])

    post_rows = [["Post", "Intentos", "Aprobados", "Fallidos", "% Aprob.", "Prom. Intento", "Dificultad"]]
    for row in report_context["post_rows"]:
        post_rows.append(
            [
                row.title,
                str(row.total_attempts),
                str(row.approved_attempts),
                str(row.failed_attempts),
                f"{row.approval_rate}%",
                str(row.avg_attempt_number),
                f"{row.difficulty_score}%",
            ]
        )
    post_table = Table(post_rows, repeatRows=1, colWidths=[180, 52, 56, 52, 56, 62, 58])
    post_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf1f8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d2dbe7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([post_table, Spacer(1, 8), Paragraph("Detalle por Usuario", section_style)])

    user_rows = [["Usuario", "Posts", "Aprobados", "Pendientes", "% Cumpl.", "% Aprob."]]
    for row in report_context["user_rows"]:
        user_rows.append(
            [
                row.username,
                str(row.total_posts),
                str(row.approved_posts),
                str(row.pending_posts),
                f"{row.compliance_percentage}%",
                f"{row.approval_percentage}%",
            ]
        )
    user_table = Table(user_rows, repeatRows=1, colWidths=[190, 55, 60, 65, 70, 70])
    user_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf1f8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d2dbe7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([user_table, Spacer(1, 8), Paragraph("Hallazgos Operativos", section_style)])

    hardest = report_context["hardest_posts"]
    if hardest:
        story.append(p("<b>Posts más difíciles:</b>"))
        for row in hardest:
            story.append(p(f"• {row.title} - dificultad {row.difficulty_score}%"))
    pending_users = report_context["users_pending"]
    if pending_users:
        story.append(Spacer(1, 4))
        story.append(p("<b>Usuarios con más pendientes:</b>"))
        for row in pending_users:
            story.append(p(f"• {row.username} - {row.pending_posts} pendientes"))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _resolve_post_html_tokens(request: Request, html_content: str) -> str:
    """Reemplaza placeholders de navegación LMS dentro del HTML del post."""
    lms_posts_url = str(request.url_for("lms_posts_view"))
    replacements = {
        "[[LMS_POSTS_URL]]": lms_posts_url,
    }
    resolved = html_content or ""
    for token, target in replacements.items():
        resolved = resolved.replace(token, target)

    # Compatibilidad hacia atrás: contenido guardado con sintaxis Jinja literal.
    resolved = re.sub(
        r"\{\{\s*url_for\(\s*['\"]lms_posts_view['\"]\s*\)\s*\}\}",
        lms_posts_url,
        resolved,
        flags=re.IGNORECASE,
    )
    return resolved


def _next_quiz_version(current_version: str, existing_versions: set[str]) -> str:
    """Calcula una versión incremental simple evitando colisiones."""
    version = (current_version or "1.0").strip()
    match = re.match(r"^(\d+)(?:\.(\d+))?$", version)
    if not match:
        base = version or "1.0"
        candidate = f"{base}-rev2"
        while candidate in existing_versions:
            candidate = f"{candidate}-x"
        return candidate

    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    candidate = f"{major}.{minor + 1}"
    while candidate in existing_versions:
        minor += 1
        candidate = f"{major}.{minor + 1}"
    return candidate


@router.get("/posts",
    include_in_schema=False,
    response_model=list[LMSPostResponse],
    )
def get_posts(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    repo = LMSRepository(db)
    if current_user.role in {"admin", "auditor"}:
        return repo.list_posts()
    return repo.list_published_posts()


@router.get("/posts/{slug}",
    include_in_schema=False,
    response_model=LMSPostResponse,
    )
def get_post(slug: str, current_user: CurrentUser, db: Session = Depends(get_db)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    repo = LMSRepository(db)
    post = repo.get_post_by_slug(slug)
    if post is None:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    if current_user.role not in {"admin", "auditor"} and post.status != "published":
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return post


@router.post(
    "/posts",
    response_model=LMSPostResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_post(payload: LMSPostCreate, admin: CurrentAdmin, db: Session = Depends(get_db)):
    if isinstance(admin, RedirectResponse):
        return admin
    return lms_service.create_post(db=db, payload=payload, created_by_id=admin.id)


@router.patch("/posts/{post_id}", response_model=LMSPostResponse, include_in_schema=False)
def patch_post(
    post_id: int,
    payload: LMSPostUpdate,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    return lms_service.update_post(db=db, post_id=post_id, payload=payload)


@router.get("/posts/{post_id}/quiz", response_model=LMSQuizResponse, include_in_schema=False)
def get_post_quiz(post_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    repo = LMSRepository(db)
    quiz = repo.get_active_quiz_for_post(post_id=post_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz no configurado")
    return quiz


@router.post(
    "/posts/{post_id}/quiz",
    response_model=LMSQuizResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_post_quiz(
    post_id: int,
    payload: LMSQuizCreate,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    return lms_service.upsert_quiz(
        db=db,
        post_id=post_id,
        title=payload.title,
        instructions=payload.instructions,
        version=payload.version,
        is_active=payload.is_active,
        questions=[question.model_dump() for question in payload.questions],
    )


@router.post("/posts/{post_id}/attempt", response_model=LMSAttemptResponse, include_in_schema=False)
def submit_post_attempt(
    post_id: int,
    payload: LMSAttemptSubmitRequest,
    request: Request,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    ip_origen = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    attempt = lms_service.submit_quiz_attempt(
        db=db,
        user=current_user,
        post_id=post_id,
        payload=payload,
        ip_origen=ip_origen,
        user_agent=user_agent,
    )
    response_payload = LMSAttemptResponse.model_validate(attempt).model_dump()
    certificate_relative_path = getattr(attempt, "certificate_relative_path", None)
    if certificate_relative_path:
        response_payload["certificate_url"] = str(
            request.url_for("media", path=certificate_relative_path)
        )
    response_payload["certificate_filename"] = getattr(
        attempt,
        "certificate_filename",
        None,
    )
    return response_payload


@router.get(
    "/posts/{post_id}/status",
    response_model=LMSUserPostStatusResponse,
    include_in_schema=False,
)
def get_post_status(post_id: int, current_user: CurrentUser, db: Session = Depends(get_db)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    repo = LMSRepository(db)
    period = lms_service.get_active_period(db)
    post = repo.get_post_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    status_row = lms_service.refresh_user_post_status(
        db=db,
        user_id=current_user.id,
        post=post,
        period=period,
    )
    access = lms_service.can_user_answer_post(db=db, user_id=current_user.id, post=post, period=period)
    return LMSUserPostStatusResponse(
        **status_row.__dict__,
        attempts_remaining=access.attempts_remaining,
        can_answer=access.can_answer,
        reason=access.reason,
    )


@router.get(
    "/users/{user_id}/attempts",
    response_model=list[LMSAttemptResponse],
    include_in_schema=False,
)
def get_user_attempts(
    user_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if current_user.role == "user" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    repo = LMSRepository(db)
    return repo.list_attempts_by_user(user_id=user_id)


@router.get(
    "/users/{user_id}/dashboard",
    response_model=LMSUserDashboardResponse,
    include_in_schema=False,
)
def get_user_dashboard(
    user_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if current_user.role == "user" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    dashboard = lms_service.dashboard_by_user(db=db, user_id=user_id)
    return {
        "user_id": user_id,
        "period": dashboard["period"],
        "summary": dashboard["summary"],
        "posts": dashboard["posts"],
    }


@router.get(
    "/periods/active",
    response_model=LMSPeriodResponse,
    include_in_schema=False,
)
def get_period_active(current_user: CurrentUser, db: Session = Depends(get_db)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return lms_service.get_active_period(db)


@router.post(
    "/periods",
    response_model=LMSPeriodResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_period(
    payload: LMSPeriodCreate,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    return lms_service.create_or_activate_period(db=db, payload=payload)


@router.post(
    "/periods/activate/{period_id}",
    response_model=LMSPeriodResponse,
    include_in_schema=False,
)
def activate_period(
    period_id: int,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    return lms_service.activate_period(db=db, period_id=period_id)


@router.get(
    "/metrics/period/{period_id}",
    response_model=LMSPeriodMetrics,
    include_in_schema=False,
)
def get_period_metrics(
    period_id: int,
    auditor_or_admin: CurrentAuditorOrAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(auditor_or_admin, RedirectResponse):
        return auditor_or_admin
    return lms_service.metrics_by_period(db=db, period_id=period_id)["kpis"]


@router.get("/metrics/period/{period_id}/posts", include_in_schema=False)
def get_period_metrics_posts(
    period_id: int,
    auditor_or_admin: CurrentAuditorOrAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(auditor_or_admin, RedirectResponse):
        return auditor_or_admin
    return lms_service.metrics_posts_by_period(db=db, period_id=period_id)


@router.get("/metrics/period/{period_id}/users", include_in_schema=False)
def get_period_metrics_users(
    period_id: int,
    auditor_or_admin: CurrentAuditorOrAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(auditor_or_admin, RedirectResponse):
        return auditor_or_admin
    return lms_service.metrics_users_by_period(db=db, period_id=period_id)


@router.get(
    "/metrics/period/{period_id}/compliance",
    response_model=list[LMSComplianceItem],
    include_in_schema=False,
)
def get_period_compliance(
    period_id: int,
    auditor_or_admin: CurrentAuditorOrAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(auditor_or_admin, RedirectResponse):
        return auditor_or_admin
    return lms_service.compliance_by_period(db=db, period_id=period_id)


# Vistas HTML LMS
@router.get("/view/posts", response_class=HTMLResponse, include_in_schema=False, name="lms_posts_view")
def lms_posts_view(
    request: Request,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    repo = LMSRepository(db)
    period = lms_service.get_active_period(db)
    posts = sorted(repo.list_published_posts(), key=lambda post: post.id)
    post_statuses: dict[int, dict] = {}
    for post in posts:
        quiz = repo.get_active_quiz_for_post(post_id=post.id)
        if quiz is None:
            post_statuses[post.id] = {
                "label": "Sin quiz",
                "badge_class": "audit-status-muted",
                "detail": "Aún no configurado",
            }
            continue

        status_row = lms_service.refresh_user_post_status(
            db=db, user_id=current_user.id, post=post, period=period
        )
        access = lms_service.can_user_answer_post(
            db=db, user_id=current_user.id, post=post, period=period
        )

        if status_row.is_passed:
            post_statuses[post.id] = {
                "label": "Aprobado",
                "badge_class": "audit-status-ok",
                "detail": "Completado",
            }
        elif status_row.is_blocked:
            post_statuses[post.id] = {
                "label": "Bloqueado",
                "badge_class": "audit-status-warn",
                "detail": "Intentos agotados",
            }
        else:
            post_statuses[post.id] = {
                "label": "Pendiente",
                "badge_class": "audit-status-muted",
                "detail": f"{access.attempts_remaining} intentos disponibles",
            }

    return templates.TemplateResponse(
        request=request,
        name="dashboard/lms_posts.html",
        context={
            "title": "Capacitación SGSI",
            "user": current_user,
            "data": get_dashboard_stats(db, current_user=current_user),
            "posts": posts,
            "post_statuses": post_statuses,
        },
    )


@router.get(
    "/view/metrics",
    response_class=HTMLResponse,
    include_in_schema=False,
    name="lms_metrics_view",
)
def lms_metrics_view(
    request: Request,
    auditor_or_admin: CurrentAuditorOrAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(auditor_or_admin, RedirectResponse):
        return auditor_or_admin

    report_context = _build_lms_metrics_context(
        db=db,
        responsible_username=auditor_or_admin.username,
    )

    return templates.TemplateResponse(
        request=request,
        name="dashboard/lms_metrics_report.html",
        context={
            "title": "Métricas LMS",
            "user": auditor_or_admin,
            "data": get_dashboard_stats(db, current_user=auditor_or_admin),
            **report_context,
        },
    )


@router.get(
    "/view/metrics/export",
    response_class=StreamingResponse,
    include_in_schema=False,
    name="lms_metrics_export_pdf",
)
def lms_metrics_export_pdf(
    auditor_or_admin: CurrentAuditorOrAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(auditor_or_admin, RedirectResponse):
        return auditor_or_admin

    report_context = _build_lms_metrics_context(
        db=db,
        responsible_username=auditor_or_admin.username,
    )
    pdf_buffer = _generate_lms_metrics_report_pdf(report_context=report_context)
    pdf_bytes = pdf_buffer.getvalue()

    report_version = _calculate_next_lms_report_version(db=db)
    _persist_lms_report_as_document(
        db=db,
        generated_by_id=auditor_or_admin.id,
        pdf_bytes=pdf_bytes,
        report_version=report_version,
    )

    filename = f"Informe_Cumplimiento_Evaluaciones_SGSI_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
        media_type="application/pdf",
    )


@router.get(
    "/view/config",
    response_class=HTMLResponse,
    include_in_schema=False,
    name="lms_config_view",
)
def lms_config_view(
    request: Request,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    repo = LMSRepository(db)
    periods = repo.list_periods()
    posts = sorted(repo.list_posts(), key=lambda post: post.id)
    posts_by_id = {post.id: post for post in posts}
    quizzes = sorted(repo.list_quizzes(), key=lambda quiz: (quiz.post_id, quiz.id))
    quiz_rows = []
    for quiz in quizzes:
        post = posts_by_id.get(quiz.post_id)
        quiz_rows.append(
            {
                "id": quiz.id,
                "post_id": quiz.post_id,
                "post_title": post.title if post else f"Post #{quiz.post_id}",
                "version": quiz.version,
                "is_active": quiz.is_active,
                "title": quiz.title,
                "instructions": quiz.instructions or "",
                "questions_payload": [
                    {
                        "question_order": question.question_order,
                        "statement": question.statement,
                        "weight": float(question.weight),
                        "options": [
                            {
                                "option_order": option.option_order,
                                "option_text": option.option_text,
                                "is_correct": bool(option.is_correct),
                            }
                            for option in sorted(question.options, key=lambda row: row.option_order)
                        ],
                    }
                    for question in sorted(quiz.questions, key=lambda row: row.question_order)
                ],
            }
        )
    return templates.TemplateResponse(
        request=request,
        name="dashboard/lms_config.html",
        context={
            "title": "Configuración LMS",
            "user": admin,
            "data": get_dashboard_stats(db, current_user=admin),
            "periods": periods,
            "posts": posts,
            "quizzes": quiz_rows,
        },
    )


@router.post(
    "/view/config/posts/edit/{post_id}",
    include_in_schema=False,
    name="lms_config_edit_post_html",
)
def lms_config_edit_post_html(
    request: Request,
    post_id: int,
    admin: CurrentAdmin,
    html_content: str = Form(""),
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    payload = LMSPostUpdate(html_content=html_content)
    lms_service.update_post(db=db, post_id=post_id, payload=payload)
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.post("/view/config/periods/create", include_in_schema=False, name="lms_config_create_period")
def lms_config_create_period(
    request: Request,
    admin: CurrentAdmin,
    year: int = Form(...),
    semester: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    name: str = Form(...),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    payload = LMSPeriodCreate(
        year=year,
        semester=semester,
        start_date=start_date,
        end_date=end_date,
        name=name,
        is_active=is_active,
    )
    lms_service.create_or_activate_period(db=db, payload=payload)
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.post(
    "/view/config/periods/activate/{period_id}",
    include_in_schema=False,
    name="lms_config_activate_period",
)
def lms_config_activate_period(
    request: Request,
    period_id: int,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    lms_service.activate_period(db=db, period_id=period_id)
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.post("/view/config/posts/create", include_in_schema=False, name="lms_config_create_post")
def lms_config_create_post(
    request: Request,
    admin: CurrentAdmin,
    title: str = Form(...),
    category: str = Form(...),
    version: str = Form(...),
    slug: str = Form(...),
    status_post: str = Form(...),
    html_content: str = Form(""),
    porcentaje_aprobacion: float = Form(...),
    max_intentos: int = Form(...),
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    payload = LMSPostCreate(
        title=title,
        category=category,
        version=version,
        slug=slug,
        status=status_post,
        html_content=html_content,
        porcentaje_aprobacion=porcentaje_aprobacion,
        max_intentos=max_intentos,
    )
    lms_service.create_post(db=db, payload=payload, created_by_id=admin.id)
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.post(
    "/view/config/posts/activate/{post_id}",
    include_in_schema=False,
    name="lms_config_activate_post",
)
def lms_config_activate_post(
    request: Request,
    post_id: int,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    lms_service.activate_post(db=db, post_id=post_id)
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.post("/view/config/quizzes/create", include_in_schema=False, name="lms_config_create_quiz")
def lms_config_create_quiz(
    request: Request,
    admin: CurrentAdmin,
    post_id: int = Form(...),
    title: str = Form(...),
    instructions: str = Form(""),
    version: str = Form(...),
    questions_json: str = Form(...),
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    try:
        questions = json.loads(questions_json)
        if not isinstance(questions, list) or not questions:
            raise ValueError("Formato inválido")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="questions_json debe ser un arreglo JSON con preguntas y opciones",
        )

    lms_service.upsert_quiz(
        db=db,
        post_id=post_id,
        title=title,
        instructions=instructions,
        version=version,
        is_active=True,
        questions=questions,
    )
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.post(
    "/view/config/quizzes/edit/{quiz_id}",
    include_in_schema=False,
    name="lms_config_edit_quiz",
)
def lms_config_edit_quiz(
    request: Request,
    quiz_id: int,
    admin: CurrentAdmin,
    title: str = Form(...),
    instructions: str = Form(""),
    version: str = Form(""),
    questions_json: str = Form(...),
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin

    repo = LMSRepository(db)
    quiz = repo.get_quiz_by_id(quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz no encontrado")

    try:
        questions = json.loads(questions_json)
        if not isinstance(questions, list) or not questions:
            raise ValueError("Formato inválido")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="questions_json debe ser un arreglo JSON con preguntas y opciones",
        )

    existing_versions = {
        row.version
        for row in repo.list_quizzes()
        if row.post_id == quiz.post_id and row.id != quiz.id
    }
    requested_version = (version or quiz.version).strip()
    if not requested_version or requested_version == quiz.version or requested_version in existing_versions:
        requested_version = _next_quiz_version(quiz.version, existing_versions)

    lms_service.upsert_quiz(
        db=db,
        post_id=quiz.post_id,
        title=title.strip() or quiz.title,
        instructions=instructions,
        version=requested_version,
        is_active=True,
        questions=questions,
    )
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.post(
    "/view/config/quizzes/activate/{quiz_id}",
    include_in_schema=False,
    name="lms_config_activate_quiz",
)
def lms_config_activate_quiz(
    request: Request,
    quiz_id: int,
    admin: CurrentAdmin,
    db: Session = Depends(get_db),
):
    if isinstance(admin, RedirectResponse):
        return admin
    lms_service.activate_quiz(db=db, quiz_id=quiz_id)
    return RedirectResponse(url=request.url_for("lms_config_view"), status_code=303)


@router.get(
    "/view/posts/{slug}",
    response_class=HTMLResponse,
    include_in_schema=False,
    name="lms_post_view",
)
def lms_post_detail_view(
    slug: str,
    request: Request,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    repo = LMSRepository(db)
    post = repo.get_post_by_slug(slug)
    if post is None or post.status != "published":
        raise HTTPException(status_code=404, detail="Post no encontrado")
    quiz = repo.get_active_quiz_for_post(post_id=post.id)
    period = lms_service.get_active_period(db)
    status_row = lms_service.refresh_user_post_status(
        db=db, user_id=current_user.id, post=post, period=period
    )
    access = lms_service.can_user_answer_post(
        db=db, user_id=current_user.id, post=post, period=period
    )
    rendered_html = _resolve_post_html_tokens(request=request, html_content=post.html_content)
    return templates.TemplateResponse(
        request=request,
        name="dashboard/lms_post_detail.html",
        context={
            "title": "Capacitación SGSI",
            "user": current_user,
            "data": get_dashboard_stats(db, current_user=current_user),
            "post": post,
            "rendered_post_html": rendered_html,
            "quiz": quiz,
            "status_row": status_row,
            "can_answer": access.can_answer,
            "reason": access.reason,
            "attempts_remaining": access.attempts_remaining,
        },
    )
