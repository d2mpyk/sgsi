"""Router para la gestión de documentos del SGSI"""

import csv, io, os, shutil, uuid, hashlib, re, math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, List, Optional
from xml.sax.saxutils import escape

from markupsafe import Markup
from reportlab.lib import colors
from reportlab.lib.colors import blue, black
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.widgets.markers import makeMarker

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import (
    FileResponse,
    RedirectResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models.documents import Document, DocumentRead
from models.users import User
from schemas.documents import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    PolicyAuditByDepartment,
    PolicyAuditByPolicy,
    PolicyAuditSummary,
    PolicyAuditTraceabilityRow,
    PolicyAuditTrendPoint,
    DocumentReadResponse,
    DocumentWithReadStatus,
    DocumentComplianceStats,
)
from utils.auth import (
    CurrentUser,
    get_current_admin,
    get_flash_messages,
    get_current_user,
    security_logger,
)
from utils.database import get_db
from utils.stats import get_dashboard_stats
from utils.config import get_settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")
# Obtener las variables de entorno
settings = get_settings()


DOCUMENT_SORT_ORDER = (
    func.coalesce(Document.code, "ZZZZZZ"),
    Document.title,
)
READ_DUE_DAYS = 30
AUDIT_REPORT_DOC_CODE = "REP-AUD-LECT-POL"
AUDIT_REPORT_DOC_TITLE = "Informe Global de Confirmación de Lectura de Políticas"
DEFAULT_CERT_PAGE_SIZE = 20
CERT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100]


def _normalize_cert_page_size(value: int | None) -> int:
    if value in CERT_PAGE_SIZE_OPTIONS:
        return int(value)
    return DEFAULT_CERT_PAGE_SIZE


def _extract_certificate_id_from_filename(filename: str) -> int:
    """
    Extrae un ID estable de certificado desde el nombre de archivo.
    Prioriza sufijo timestamp YYYYMMDD_HHMMSS; fallback hash estable.
    """
    stem = Path(filename).stem
    match = re.search(r"(\d{8}_\d{6})$", stem)
    if match:
        return int(match.group(1).replace("_", ""))
    return abs(hash(stem)) % 10_000_000_000


def _load_generated_certificates() -> list[dict]:
    certificates_root = Path("media") / "documents" / "certificates"
    if not certificates_root.exists():
        return []

    rows: list[dict] = []
    media_root = Path("media")
    for file_path in certificates_root.rglob("*.pdf"):
        if not file_path.is_file():
            continue

        certificate_id = _extract_certificate_id_from_filename(file_path.name)
        if file_path.name.startswith("Certificado_Lectura_"):
            certificate_type = "Lectura de política"
        elif file_path.name.startswith("Certificado_Evaluacion_"):
            certificate_type = "Evaluación LMS"
        else:
            certificate_type = "General"

        rows.append(
            {
                "certificate_id": certificate_id,
                "filename": file_path.name,
                "department": file_path.parent.name,
                "certificate_type": certificate_type,
                "generated_at": datetime.fromtimestamp(file_path.stat().st_mtime),
                "relative_path": file_path.relative_to(media_root).as_posix(),
            }
        )

    rows.sort(key=lambda item: (item["certificate_id"], item["filename"].lower()))
    return rows


def extract_document_metadata_from_filename(
    filename: str, default_version: str = "1.0"
) -> tuple[str, str]:
    """
    Extrae un título limpio y la versión desde el nombre del archivo.
    Ejemplo: "Politica_Acceso_v2.3.pdf" -> ("Politica_Acceso", "2.3")
    Si no encuentra versión, conserva la versión por defecto.
    """
    filename_no_ext = os.path.splitext(filename)[0]
    version_match = re.search(r"(?:[-_\s]+)?[vV](\d+(?:\.\d+)+)", filename_no_ext)

    extracted_title = filename_no_ext
    extracted_version = default_version

    if version_match:
        extracted_version = version_match.group(1)
        clean_title = filename_no_ext[: version_match.start()].strip()
        if clean_title:
            extracted_title = clean_title

    return extracted_title, extracted_version


def build_document_description(
    original_filename: str,
    provided_description: Optional[str] = None,
) -> str:
    """
    Construye la descripción persistida asegurando que incluya
    el nombre original del archivo subido.
    """
    filename_note = original_filename
    clean_description = (provided_description or "").strip()

    if not clean_description:
        return filename_note

    if filename_note in clean_description:
        return clean_description

    return f"{clean_description}\n{filename_note}"


def upsert_policy_download_read(
    db: Session,
    user_id: int,
    document_id: int,
) -> DocumentRead:
    """
    Garantiza un registro en document_reads por usuario y política.
    - Si no existe, lo crea con download_at.
    - Si existe y no tiene read_at, refresca download_at.
    - Si ya tiene read_at, conserva download_at intacto.
    """
    existing_read = (
        db.execute(
            select(DocumentRead).where(
                DocumentRead.user_id == user_id,
                DocumentRead.document_id == document_id,
            )
        )
        .scalars()
        .first()
    )

    if existing_read is None:
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
        existing_read.download_at = datetime.now(UTC)
        db.commit()
        db.refresh(existing_read)

    return existing_read


def get_compliance_semaphore(percentage: float) -> str:
    """Determina el estado visual de cumplimiento."""
    if percentage >= 90:
        return "green"
    if percentage >= 70:
        return "yellow"
    return "red"


def normalize_datetime(value: datetime | None) -> datetime | None:
    """Homologa datetimes naive/aware para comparaciones consistentes."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def svg_bar_chart(items: list[tuple[str, float]], width: int = 760, height: int = 260) -> Markup:
    """Genera un gráfico de barras horizontal en SVG para el reporte."""
    if not items:
        return Markup("<p>No hay datos suficientes para construir el gráfico por área.</p>")

    left_margin = 180
    top_margin = 20
    row_height = 32
    chart_width = width - left_margin - 60
    svg_height = max(height, top_margin + row_height * len(items) + 30)
    bars = []

    for index, (label, value) in enumerate(items):
        y = top_margin + index * row_height
        bar_width = max(0, min(chart_width, chart_width * (value / 100)))
        color = "#2f855a" if value >= 90 else "#d69e2e" if value >= 70 else "#c53030"
        bars.append(
            f'<text x="10" y="{y + 18}" font-size="12" fill="#334155">{label}</text>'
            f'<rect x="{left_margin}" y="{y + 4}" width="{chart_width}" height="16" rx="8" fill="#e2e8f0"></rect>'
            f'<rect x="{left_margin}" y="{y + 4}" width="{bar_width}" height="16" rx="8" fill="{color}"></rect>'
            f'<text x="{left_margin + chart_width + 10}" y="{y + 18}" font-size="12" fill="#0f172a">{value:.1f}%</text>'
        )

    svg = (
        f'<svg width="100%" viewBox="0 0 {width} {svg_height}" role="img" aria-label="Cumplimiento por área">'
        + "".join(bars)
        + "</svg>"
    )
    return Markup(svg)


def svg_pie_chart(read_percentage: float, pending_percentage: float) -> Markup:
    """Genera un gráfico tipo pastel/donut en SVG para el estado global."""
    radius = 70
    circumference = 2 * math.pi * radius
    read_dash = circumference * (read_percentage / 100)
    pending_dash = max(circumference - read_dash, 0)

    svg = f"""
    <svg width="100%" viewBox="0 0 260 280" role="img" aria-label="Estado global de lectura">
        <circle cx="130" cy="102" r="{radius}" fill="none" stroke="#e2e8f0" stroke-width="22"></circle>
        <circle cx="130" cy="102" r="{radius}" fill="none" stroke="#2b6cb0" stroke-width="22"
            stroke-dasharray="{read_dash} {pending_dash}" stroke-linecap="round"
            transform="rotate(-90 130 102)"></circle>
        <circle cx="130" cy="102" r="42" fill="#ffffff"></circle>
        <text x="130" y="97" text-anchor="middle" font-size="24" fill="#0f172a" font-weight="700">{read_percentage:.1f}%</text>
        <text x="130" y="117" text-anchor="middle" font-size="12" fill="#64748b">Leído</text>

        <rect x="70" y="210" width="14" height="14" rx="3" fill="#2b6cb0"></rect>
        <text x="92" y="221" font-size="12" fill="#334155">Leído {read_percentage:.1f}%</text>
        <rect x="70" y="236" width="14" height="14" rx="3" fill="#e2e8f0"></rect>
        <text x="92" y="247" font-size="12" fill="#334155">Pendiente {pending_percentage:.1f}%</text>
    </svg>
    """
    return Markup(svg)


def svg_trend_chart(points: list[PolicyAuditTrendPoint], width: int = 760, height: int = 260) -> Markup:
    """Genera un gráfico de tendencia en SVG."""
    if not points:
        return Markup("<p>No hay datos suficientes para construir la tendencia histórica.</p>")

    padding_x = 55
    padding_y = 25
    chart_width = width - (padding_x * 2)
    chart_height = height - (padding_y * 2)
    max_value = 100
    step_x = chart_width / max(len(points) - 1, 1)

    coords = []
    labels = []
    for index, point in enumerate(points):
        x = padding_x + (index * step_x)
        y = padding_y + chart_height - ((point.compliance_percentage / max_value) * chart_height)
        coords.append((x, y, point))
        labels.append(
            f'<text x="{x}" y="{height - 8}" text-anchor="middle" font-size="11" fill="#64748b">{point.period_label}</text>'
        )

    polyline = " ".join(f"{x},{y}" for x, y, _ in coords)
    circles = "".join(
        f'<circle cx="{x}" cy="{y}" r="4" fill="#1d4ed8"></circle>'
        f'<text x="{x}" y="{y - 10}" text-anchor="middle" font-size="11" fill="#0f172a">{point.compliance_percentage:.1f}%</text>'
        for x, y, point in coords
    )
    grid = "".join(
        f'<line x1="{padding_x}" y1="{padding_y + (chart_height * idx / 4)}" '
        f'x2="{width - padding_x}" y2="{padding_y + (chart_height * idx / 4)}" stroke="#e2e8f0" stroke-width="1"></line>'
        for idx in range(5)
    )

    svg = (
        f'<svg width="100%" viewBox="0 0 {width} {height}" role="img" aria-label="Tendencia de cumplimiento">'
        f'{grid}'
        f'<polyline fill="none" stroke="#1d4ed8" stroke-width="3" points="{polyline}"></polyline>'
        f'{circles}'
        f'{"".join(labels)}'
        "</svg>"
    )
    return Markup(svg)


def build_policy_reading_audit_report(
    db: Session,
    responsible_username: str,
) -> dict:
    """Construye el informe global de confirmación de lectura listo para auditoría."""
    generated_at = datetime.now(UTC)
    due_limit = generated_at - timedelta(days=READ_DUE_DAYS)

    active_users = (
        db.execute(
            select(User)
            .where(User.is_active == True)
            .order_by(User.id)
        )
        .scalars()
        .all()
    )
    active_policies = (
        db.execute(
            select(Document)
            .where(Document.doc_type == "policy", Document.is_active == True)
            .order_by(*DOCUMENT_SORT_ORDER)
        )
        .scalars()
        .all()
    )
    reads = (
        db.execute(
            select(DocumentRead)
            .join(Document, DocumentRead.document_id == Document.id)
            .where(Document.doc_type == "policy", Document.is_active == True)
        )
        .scalars()
        .all()
    )
    reads_map = {(read.user_id, read.document_id): read for read in reads}

    total_active_users = len(active_users)
    total_active_policies = len(active_policies)
    total_assignments = total_active_users * total_active_policies
    completed_assignments = 0
    pending_reads = 0
    overdue_reads = 0
    confirmed_users = set()
    policy_rows: list[PolicyAuditByPolicy] = []
    department_totals: dict[int, dict] = {}
    traceability_rows: list[PolicyAuditTraceabilityRow] = []

    for user in active_users:
        if user.department_id not in department_totals:
            department_totals[user.department_id] = {
                "department_id": user.department_id,
                "department_name": user.department_name,
                "total_collaborators": 0,
                "total_assignments": 0,
                "confirmations": 0,
                "pending_reads": 0,
                "overdue_reads": 0,
            }
        department_totals[user.department_id]["total_collaborators"] += 1

    for policy in active_policies:
        policy_confirmations = 0
        policy_overdue = 0

        for user in active_users:
            read = reads_map.get((user.id, policy.id))
            normalized_policy_created_at = normalize_datetime(policy.created_at)
            normalized_read_at = normalize_datetime(read.read_at) if read else None
            normalized_download_at = normalize_datetime(read.download_at) if read else None
            is_confirmed = bool(read and normalized_read_at is not None)
            is_overdue = bool(normalized_policy_created_at and normalized_policy_created_at <= due_limit and not is_confirmed)

            department_bucket = department_totals[user.department_id]
            department_bucket["total_assignments"] += 1

            if is_confirmed:
                completed_assignments += 1
                policy_confirmations += 1
                department_bucket["confirmations"] += 1
                confirmed_users.add(user.id)
                status_value = "leido"
            else:
                pending_reads += 1
                department_bucket["pending_reads"] += 1
                status_value = "pendiente"
                if is_overdue:
                    overdue_reads += 1
                    policy_overdue += 1
                    department_bucket["overdue_reads"] += 1
                    status_value = "fuera_de_plazo"

            traceability_rows.append(
                PolicyAuditTraceabilityRow(
                    user_id=user.id,
                    username=user.username,
                    department_name=user.department_name,
                    policy_code=policy.code or f"POL-{policy.id}",
                    policy_title=policy.title,
                    status=status_value,
                    created_at=normalized_policy_created_at or policy.created_at,
                    download_at=normalized_download_at,
                    read_at=normalized_read_at,
                    overdue=is_overdue,
                )
            )

        policy_percentage = round(
            (policy_confirmations / total_active_users) * 100, 1
        ) if total_active_users else 0.0
        policy_rows.append(
            PolicyAuditByPolicy(
                policy_id=policy.id,
                code=policy.code or f"POL-{policy.id}",
                title=policy.title,
                total_collaborators=total_active_users,
                confirmations=policy_confirmations,
                compliance_percentage=policy_percentage,
                overdue_reads=policy_overdue,
                semaphore=get_compliance_semaphore(policy_percentage),
            )
        )

    department_rows = []
    for department_data in sorted(department_totals.values(), key=lambda item: item["department_name"]):
        compliance = round(
            (department_data["confirmations"] / department_data["total_assignments"]) * 100, 1
        ) if department_data["total_assignments"] else 0.0
        department_rows.append(
            PolicyAuditByDepartment(
                department_id=department_data["department_id"],
                department_name=department_data["department_name"],
                total_collaborators=department_data["total_collaborators"],
                total_assignments=department_data["total_assignments"],
                confirmations=department_data["confirmations"],
                compliance_percentage=compliance,
                pending_reads=department_data["pending_reads"],
                overdue_reads=department_data["overdue_reads"],
                semaphore=get_compliance_semaphore(compliance),
            )
        )

    global_compliance_percentage = round(
        (completed_assignments / total_assignments) * 100, 1
    ) if total_assignments else 0.0
    collaborators_confirmed_percentage = round(
        (len(confirmed_users) / total_active_users) * 100, 1
    ) if total_active_users else 0.0

    summary = PolicyAuditSummary(
        generated_at=generated_at,
        report_version="1.0",
        responsible=responsible_username,
        global_compliance_percentage=global_compliance_percentage,
        collaborators_confirmed_percentage=collaborators_confirmed_percentage,
        pending_reads=pending_reads,
        overdue_reads=overdue_reads,
        total_active_users=total_active_users,
        total_active_policies=total_active_policies,
        total_assignments=total_assignments,
        completed_assignments=completed_assignments,
    )

    monthly_points = []
    for offset in range(5, -1, -1):
        reference = generated_at - timedelta(days=30 * offset)
        month_start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        month_end = next_month - timedelta(microseconds=1)

        policies_available = [
            policy
            for policy in active_policies
            if normalize_datetime(policy.created_at) and normalize_datetime(policy.created_at) <= month_end
        ]
        assignments_available = total_active_users * len(policies_available)
        confirmed_assignments = 0

        if assignments_available:
            for policy in policies_available:
                for user in active_users:
                    read = reads_map.get((user.id, policy.id))
                    normalized_read_at = normalize_datetime(read.read_at) if read else None
                    if normalized_read_at and normalized_read_at <= month_end:
                        confirmed_assignments += 1

        monthly_percentage = round(
            (confirmed_assignments / assignments_available) * 100, 1
        ) if assignments_available else 0.0
        monthly_points.append(
            PolicyAuditTrendPoint(
                period_label=month_start.strftime("%b %Y"),
                compliance_percentage=monthly_percentage,
                confirmed_assignments=confirmed_assignments,
                total_assignments=assignments_available,
            )
        )

    global_pie_chart = svg_pie_chart(
        global_compliance_percentage,
        max(0.0, round(100 - global_compliance_percentage, 1)),
    )
    department_bar_chart = svg_bar_chart(
        [(row.department_name, row.compliance_percentage) for row in department_rows]
    )
    trend_chart = svg_trend_chart(monthly_points)

    risks = []
    if overdue_reads > 0:
        risks.append(
            "Existen lecturas fuera de plazo que debilitan la evidencia de concienciación oportuna del SGSI."
        )
    if global_compliance_percentage < 90:
        risks.append(
            "El nivel de cumplimiento global es inferior al objetivo recomendado de control operacional."
        )
    if not risks:
        risks.append(
            "No se identifican incumplimientos críticos en la fecha de emisión; se recomienda mantener el seguimiento periódico."
        )

    recommendations = [
        "Reforzar recordatorios automáticos para políticas con más de 15 días sin confirmación.",
        "Priorizar seguimiento a departamentos con semáforo amarillo o rojo hasta recuperar el nivel objetivo.",
        "Incluir revisión mensual del reporte en comité SGSI como evidencia de monitoreo continuo.",
    ]

    return {
        "summary": summary,
        "policy_rows": policy_rows,
        "department_rows": department_rows,
        "traceability_rows": traceability_rows,
        "trend_points": monthly_points,
        "global_pie_chart": global_pie_chart,
        "department_bar_chart": department_bar_chart,
        "trend_chart": trend_chart,
        "scope_text": (
            "El informe cubre todas las políticas activas del SGSI vigentes en el sistema y la población de colaboradores activos con acceso al portal."
        ),
        "methodology_text": (
            f"Se considera lectura confirmada cuando existe un registro con fecha `read_at`; pendiente cuando no existe confirmación; y fuera de plazo cuando la política supera {READ_DUE_DAYS} días desde su publicación sin confirmación."
        ),
        "evidence_text": (
            "La confirmación se soporta en registros del sistema SGSI almacenados en `document_reads`, vinculados con usuario, política, fecha de descarga y fecha de aceptación."
        ),
        "risks": risks,
        "recommendations": recommendations,
    }


def render_policy_reading_audit_report_html(
    db: Session,
    responsible_username: str,
    report_stylesheet_href: str = "/static/css/policy_reading_audit_report.css",
) -> str:
    """Renderiza el HTML del informe global de auditoría."""
    report_context = build_policy_reading_audit_report(
        db=db,
        responsible_username=responsible_username,
    )
    return templates.get_template(
        "dashboard/policy_reading_audit_report.html"
    ).render(
        company_name=settings.COMPANY_NAME.get_secret_value(),
        project_name=settings.PROJECT_NAME.get_secret_value(),
        report_due_days=READ_DUE_DAYS,
        report_stylesheet_href=report_stylesheet_href,
        **report_context,
    )


def generate_policy_reading_audit_report_pdf(report_context: dict) -> io.BytesIO:
    """Genera el informe PDF con estética cercana al HTML y tablas sin solapamientos."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
        title=AUDIT_REPORT_DOC_TITLE,
    )
    content_width = doc.width

    styles = getSampleStyleSheet()
    kicker_style = ParagraphStyle(
        "AuditKicker",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#1d4ed8"),
    )
    title_style = ParagraphStyle(
        "AuditTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "AuditSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "AuditBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    table_head_style = ParagraphStyle(
        "AuditTableHead",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e3a8a"),
    )
    table_cell_style = ParagraphStyle(
        "AuditTableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=9.2,
        textColor=colors.HexColor("#1f2937"),
        wordWrap="CJK",
    )
    small_style = ParagraphStyle(
        "AuditSmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#475569"),
    )

    def p(value: str | int | float | None, style: ParagraphStyle = table_cell_style) -> Paragraph:
        return Paragraph(escape("" if value is None else str(value)), style)

    def pct_widths(weights: list[float]) -> list[float]:
        total = sum(weights)
        return [content_width * (w / total) for w in weights]

    def apply_table_style(table: Table, zebra: bool = True) -> None:
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eff6ff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe4f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if zebra:
            style_cmds.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]))
        table.setStyle(TableStyle(style_cmds))

    def build_global_donut(summary_obj: PolicyAuditSummary) -> Drawing:
        read_pct = max(0.0, min(float(summary_obj.global_compliance_percentage), 100.0))
        pending_pct = max(0.0, 100.0 - read_pct)

        drawing = Drawing(content_width * 0.46, 196)
        pie = Pie()
        pie.x = 38
        pie.y = 46
        pie.width = 120
        pie.height = 120
        pie.data = [read_pct, pending_pct]
        pie.labels = ["", ""]
        pie.sideLabels = False
        pie.simpleLabels = True
        pie.innerRadiusFraction = 0.56
        pie.slices.strokeWidth = 0.4
        pie.slices[0].fillColor = colors.HexColor("#2b6cb0")
        pie.slices[1].fillColor = colors.HexColor("#e2e8f0")
        drawing.add(pie)
        drawing.add(
            String(
                89,
                111,
                f"{read_pct:.1f}%",
                fontName="Helvetica-Bold",
                fontSize=13,
                fillColor=colors.HexColor("#0f172a"),
                textAnchor="middle",
            )
        )
        drawing.add(
            String(
                89,
                97,
                "Cumplimiento",
                fontName="Helvetica",
                fontSize=7.5,
                fillColor=colors.HexColor("#64748b"),
                textAnchor="middle",
            )
        )
        legend_y = 20
        drawing.add(
            String(
                44,
                legend_y,
                "■",
                fontName="Helvetica-Bold",
                fontSize=11,
                fillColor=colors.HexColor("#2b6cb0"),
            )
        )
        drawing.add(
            String(
                57,
                legend_y + 1,
                f"Leído {read_pct:.1f}%",
                fontName="Helvetica",
                fontSize=7.2,
                fillColor=colors.HexColor("#334155"),
            )
        )
        drawing.add(
            String(
                117,
                legend_y,
                "■",
                fontName="Helvetica-Bold",
                fontSize=11,
                fillColor=colors.HexColor("#cbd5e1"),
            )
        )
        drawing.add(
            String(
                129,
                legend_y + 1,
                f"Pendiente {pending_pct:.1f}%",
                fontName="Helvetica",
                fontSize=7.2,
                fillColor=colors.HexColor("#334155"),
            )
        )
        return drawing

    def build_department_bars(rows: list[PolicyAuditByDepartment]) -> Drawing:
        sorted_rows = sorted(rows, key=lambda r: r.compliance_percentage, reverse=True)[:8]
        labels = [r.department_name[:18] for r in sorted_rows] or ["Sin datos"]
        values = [float(r.compliance_percentage) for r in sorted_rows] or [0.0]
        chart_height = max(106, len(labels) * 15)

        drawing = Drawing(content_width * 0.46, chart_height + 46)
        bars = HorizontalBarChart()
        bars.x = 66
        bars.y = 16
        bars.width = (content_width * 0.46) - 84
        bars.height = chart_height
        bars.data = [values]
        bars.categoryAxis.categoryNames = labels
        bars.categoryAxis.labels.fontSize = 7
        bars.categoryAxis.labels.fillColor = colors.HexColor("#334155")
        bars.valueAxis.valueMin = 0
        bars.valueAxis.valueMax = 100
        bars.valueAxis.valueStep = 20
        bars.valueAxis.labels.fontSize = 7
        bars.valueAxis.labels.fillColor = colors.HexColor("#64748b")
        bars.valueAxis.strokeColor = colors.HexColor("#cbd5e1")
        bars.bars[0].fillColor = colors.HexColor("#2563eb")
        bars.bars[0].strokeColor = colors.HexColor("#1d4ed8")
        drawing.add(bars)
        drawing.add(
            String(
                0,
                chart_height + 28,
                "Cumplimiento por área (%)",
                fontName="Helvetica-Bold",
                fontSize=8,
                fillColor=colors.HexColor("#1e3a8a"),
            )
        )
        return drawing

    def build_trend_line(points: list[PolicyAuditTrendPoint]) -> Drawing:
        selected_points = points[-6:] if len(points) > 6 else points
        if not selected_points:
            selected_points = [PolicyAuditTrendPoint(period_label="N/A", compliance_percentage=0.0)]

        labels = [point.period_label for point in selected_points]
        values = [float(point.compliance_percentage) for point in selected_points]

        drawing = Drawing(content_width, 210)
        line = HorizontalLineChart()
        line.x = 48
        line.y = 40
        line.width = content_width - 82
        line.height = 132
        line.data = [values]
        line.categoryAxis.categoryNames = labels
        line.categoryAxis.labels.fontSize = 7
        line.categoryAxis.labels.fillColor = colors.HexColor("#64748b")
        line.valueAxis.valueMin = 0
        line.valueAxis.valueMax = 100
        line.valueAxis.valueStep = 20
        line.valueAxis.labels.fontSize = 7
        line.valueAxis.labels.fillColor = colors.HexColor("#64748b")
        line.lines[0].strokeColor = colors.HexColor("#1d4ed8")
        line.lines[0].strokeWidth = 2
        line.lines[0].symbol = makeMarker("FilledCircle")
        line.lines[0].symbol.size = 4
        line.lines[0].symbol.fillColor = colors.HexColor("#1d4ed8")
        drawing.add(line)
        drawing.add(
            String(
                0,
                188,
                "Tendencia de cumplimiento (%)",
                fontName="Helvetica-Bold",
                fontSize=8,
                fillColor=colors.HexColor("#1e3a8a"),
            )
        )
        return drawing

    summary = report_context["summary"]
    story: list = []

    cover_band = Table(
        [[p("EVIDENCIA DE AUDITORÍA SGSI", kicker_style)]],
        colWidths=[content_width],
    )
    cover_band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#dbeafe")),
                ("BOX", (0, 0), (0, 0), 0.6, colors.HexColor("#bfdbfe")),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("TOPPADDING", (0, 0), (0, 0), 6),
                ("BOTTOMPADDING", (0, 0), (0, 0), 6),
            ]
        )
    )
    story.extend(
        [
            cover_band,
            Spacer(1, 8),
            Paragraph(AUDIT_REPORT_DOC_TITLE, title_style),
            Paragraph(
                "Documento estructurado para auditorías internas y externas del SGSI, con trazabilidad de cumplimiento, niveles de avance e identificación de desviaciones.",
                body_style,
            ),
            Spacer(1, 8),
        ]
    )

    cover_rows = [
        [p("Organización", table_head_style), p(report_context["company_name"])],
        [p("Proyecto", table_head_style), p(report_context["project_name"])],
        [p("Fecha de emisión", table_head_style), p(summary.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC"))],
        [p("Versión del informe", table_head_style), p(summary.report_version)],
        [p("Responsable", table_head_style), p(summary.responsible)],
    ]
    cover_table = Table(cover_rows, colWidths=pct_widths([28, 72]))
    cover_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe4f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([cover_table, Spacer(1, 10), Paragraph("Resumen Ejecutivo", section_style)])

    metric_rows = [
        [p("Cumplimiento Global", table_head_style), p(f"{summary.global_compliance_percentage}%", table_head_style)],
        [p("Colaboradores Activos"), p(summary.total_active_users)],
        [p("Políticas Activas"), p(summary.total_active_policies)],
        [p("Confirmaciones"), p(f"{summary.completed_assignments}/{summary.total_assignments}")],
        [p("Lecturas Pendientes"), p(summary.pending_reads)],
        [p("Lecturas Fuera de Plazo"), p(summary.overdue_reads)],
    ]
    metric_table = Table(metric_rows, colWidths=pct_widths([70, 30]))
    metric_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend(
        [
            Paragraph(report_context["scope_text"], body_style),
            Paragraph(report_context["methodology_text"], body_style),
            Spacer(1, 6),
            metric_table,
            Spacer(1, 10),
            Paragraph("Detalle por Política", section_style),
        ]
    )

    policy_rows = [
        [
            p("ID Política", table_head_style),
            p("Código", table_head_style),
            p("Nombre", table_head_style),
            p("Colaboradores", table_head_style),
            p("Confirmaciones", table_head_style),
            p("% Cumplimiento", table_head_style),
            p("Semáforo", table_head_style),
            p("Fuera de plazo", table_head_style),
        ]
    ]
    for row in report_context["policy_rows"]:
        policy_rows.append(
            [
                p(row.policy_id),
                p(row.code),
                p(row.title),
                p(row.total_collaborators),
                p(row.confirmations),
                p(f"{row.compliance_percentage}%"),
                p(row.semaphore.upper()),
                p(row.overdue_reads),
            ]
        )
    policy_table = Table(
        policy_rows,
        repeatRows=1,
        colWidths=pct_widths([9, 10, 28, 12, 12, 12, 9, 8]),
    )
    apply_table_style(policy_table)
    story.extend([policy_table, Spacer(1, 10), Paragraph("Detalle por Área / Departamento", section_style)])

    dep_rows = [
        [
            p("Área", table_head_style),
            p("Colaboradores", table_head_style),
            p("Asignaciones", table_head_style),
            p("Confirmaciones", table_head_style),
            p("% Cumplimiento", table_head_style),
            p("Pendientes", table_head_style),
            p("Fuera de plazo", table_head_style),
            p("Semáforo", table_head_style),
        ]
    ]
    for row in report_context["department_rows"]:
        dep_rows.append(
            [
                p(row.department_name),
                p(row.total_collaborators),
                p(row.total_assignments),
                p(row.confirmations),
                p(f"{row.compliance_percentage}%"),
                p(row.pending_reads),
                p(row.overdue_reads),
                p(row.semaphore.upper()),
            ]
        )
    dep_table = Table(
        dep_rows,
        repeatRows=1,
        colWidths=pct_widths([25, 10, 11, 12, 12, 10, 11, 9]),
    )
    apply_table_style(dep_table)
    story.extend(
        [
            dep_table,
            Spacer(1, 10),
            Paragraph("Gráficos Requeridos", section_style),
            Paragraph("Visualización gráfica embebida para replicar la sección visual del informe HTML.", small_style),
            Spacer(1, 6),
        ]
    )
    charts_row = Table(
        [[build_global_donut(summary), build_department_bars(report_context["department_rows"])]],
        colWidths=pct_widths([50, 50]),
    )
    charts_row.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe4f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend(
        [
            charts_row,
            Spacer(1, 8),
        ]
    )
    trend_card = Table(
        [[build_trend_line(report_context["trend_points"])]],
        colWidths=[content_width],
    )
    trend_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dbe4f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend(
        [
            trend_card,
            Spacer(1, 10),
            Paragraph("Evidencia de Auditoría", section_style),
            Paragraph(report_context["evidence_text"], body_style),
            Spacer(1, 4),
            Paragraph("<b>Riesgos</b>", body_style),
        ]
    )
    for risk in report_context["risks"]:
        story.append(Paragraph(f"• {escape(risk)}", body_style))
    story.extend([Spacer(1, 3), Paragraph("<b>Recomendaciones</b>", body_style)])
    for recommendation in report_context["recommendations"]:
        story.append(Paragraph(f"• {escape(recommendation)}", body_style))

    story.extend([Spacer(1, 10), Paragraph("Trazabilidad Detallada", section_style)])
    trace_rows = [
        [
            p("Usuario", table_head_style),
            p("Área", table_head_style),
            p("Política", table_head_style),
            p("Estado", table_head_style),
            p("Fecha Política", table_head_style),
            p("Descarga", table_head_style),
            p("Confirmación", table_head_style),
            p("Vencida", table_head_style),
        ]
    ]
    for row in report_context["traceability_rows"]:
        trace_rows.append(
            [
                p(f"{row.username} ({row.user_id})"),
                p(row.department_name),
                p(f"{row.policy_code} - {row.policy_title}"),
                p(row.status),
                p(row.created_at.strftime("%Y-%m-%d")),
                p(row.download_at.strftime("%Y-%m-%d %H:%M") if row.download_at else "N/A"),
                p(row.read_at.strftime("%Y-%m-%d %H:%M") if row.read_at else "N/A"),
                p("Sí" if row.overdue else "No"),
            ]
        )
    trace_table = Table(
        trace_rows,
        repeatRows=1,
        colWidths=pct_widths([15, 12, 25, 10, 10, 10, 11, 7]),
    )
    apply_table_style(trace_table, zebra=False)
    story.extend(
        [
            trace_table,
            Spacer(1, 12),
            Paragraph(
                "Informe emitido automáticamente por el SGSI. Preparado para impresión y evidencia de auditoría formal.",
                small_style,
            ),
        ]
    )

    doc.build(story)
    buffer.seek(0)
    return buffer


def calculate_next_report_version(db: Session, report_code: str) -> str:
    """Calcula la siguiente versión secuencial del reporte (1.0, 2.0, ...)."""
    previous_docs = (
        db.execute(
            select(Document)
            .where(Document.code == report_code)
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

    if max_version == 0:
        return f"{len(previous_docs) + 1}.0"
    return f"{max_version + 1}.0"


def persist_audit_report_as_document(
    db: Session,
    admin_user: User,
    pdf_bytes: bytes,
    report_version: str,
) -> Document:
    """Guarda el PDF generado como Documento SGSI versionado."""
    upload_dir = "media/documents"
    os.makedirs(upload_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = "Informe_Global_Lectura_Politicas"
    stored_filename = f"{uuid.uuid4()}.pdf"
    stored_path = os.path.join(upload_dir, stored_filename)

    with open(stored_path, "wb") as report_file:
        report_file.write(pdf_bytes)

    active_docs = (
        db.execute(
            select(Document).where(
                Document.code == AUDIT_REPORT_DOC_CODE,
                Document.is_active == True,
            )
        )
        .scalars()
        .all()
    )
    for doc in active_docs:
        doc.is_active = False

    new_doc = Document(
        title=AUDIT_REPORT_DOC_TITLE,
        description=(
            "Informe global de auditoría generado automáticamente desde Administración y Métricas.\n"
            f"{safe_title}_{timestamp}.pdf"
        ),
        version=report_version,
        code=AUDIT_REPORT_DOC_CODE,
        doc_type="record",
        filename=stored_filename,
        content_type="application/pdf",
        uploaded_by_id=admin_user.id,
        is_active=True,
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    return new_doc


@router.get(
    "/reports/policies-reading-preview",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    name="preview_policy_reading_report",
)
def preview_policy_reading_report(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
):
    """Renderiza una vista previa HTML del informe global sin descargarlo."""
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    html_content = render_policy_reading_audit_report_html(
        db=db,
        responsible_username=admin_user.username,
        report_stylesheet_href=str(
            request.url_for("static", path="css/policy_reading_audit_report.css")
        ),
    )
    return HTMLResponse(content=html_content, media_type="text/html")


# ----------------------------------------------------------------------
# Vista HTML de Documentos (Listado + Stats)
@router.get(
    "/view",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    name="documents_view",
)
def documents_view(
    request: Request,
    user_or_redirect: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    cert_page: int = 1,
    cert_page_size: int = DEFAULT_CERT_PAGE_SIZE,
):
    """
    Renderiza la página principal de gestión documental.
    Pre-carga los documentos para enviarlos al template (SSR).
    """
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    # -- Lógica de obtención de documentos (reutilizada del endpoint API) --
    if current_user.role == "admin":
        stmt = (
            select(Document)
            .where(Document.is_active == True)
            .order_by(*DOCUMENT_SORT_ORDER)
        )
    else:
        stmt = (
            select(Document)
            .where(Document.doc_type == "policy", Document.is_active == True)
            .order_by(*DOCUMENT_SORT_ORDER)
        )

    documents = db.execute(stmt).scalars().all()

    # Mapa de lecturas del usuario actual
    reads_stmt = select(DocumentRead).where(DocumentRead.user_id == current_user.id)
    user_reads = db.execute(reads_stmt).scalars().all()
    read_map = {
        r.document_id: r.read_at for r in user_reads if r.read_at is not None
    }

    # Prepara la lista enriquecida para Jinja
    docs_context = []
    for doc in documents:
        # Convertimos a dict para fácil acceso en Jinja
        d_dict = {
            "id": doc.id,
            "title": doc.title,
            "description": doc.description,
            "version": doc.version,
            "code": doc.code,
            "doc_type": doc.doc_type,
            "filename": doc.filename,
            "is_active": doc.is_active,
            "created_at": doc.created_at,
            "is_read_by_user": False,
            "read_at": None,
        }
        if doc.id in read_map:
            d_dict["is_read_by_user"] = True
            d_dict["read_at"] = read_map[doc.id]
        docs_context.append(d_dict)

    flash_message, flash_type = get_flash_messages(request)
    generated_certificates_all = (
        _load_generated_certificates() if current_user.role == "admin" else []
    )
    normalized_cert_page_size = _normalize_cert_page_size(cert_page_size)
    current_cert_page = max(1, int(cert_page))
    cert_total = len(generated_certificates_all)
    cert_total_pages = max(1, (cert_total + normalized_cert_page_size - 1) // normalized_cert_page_size)
    current_cert_page = min(current_cert_page, cert_total_pages)
    cert_start_idx = (current_cert_page - 1) * normalized_cert_page_size
    generated_certificates = generated_certificates_all[
        cert_start_idx: cert_start_idx + normalized_cert_page_size
    ]

    def build_cert_url(page: int) -> str:
        return (
            f"{request.url_for('documents_view')}?"
            f"cert_page_size={normalized_cert_page_size}&cert_page={page}&tab=Certificates"
        )

    cert_pagination = {
        "page": current_cert_page,
        "page_size": normalized_cert_page_size,
        "total_items": cert_total,
        "total_pages": cert_total_pages,
        "has_prev": current_cert_page > 1,
        "has_next": current_cert_page < cert_total_pages,
        "prev_url": build_cert_url(current_cert_page - 1) if current_cert_page > 1 else "",
        "next_url": build_cert_url(current_cert_page + 1) if current_cert_page < cert_total_pages else "",
        "first_url": build_cert_url(1),
        "last_url": build_cert_url(cert_total_pages),
        "window_start": ((current_cert_page - 1) * normalized_cert_page_size) + 1 if cert_total else 0,
        "window_end": min(current_cert_page * normalized_cert_page_size, cert_total),
    }

    response = templates.TemplateResponse(
        request=request,
        name="dashboard/documents.html",
        context={
            "user": current_user,
            "data": get_dashboard_stats(db, current_user=current_user),
            "documents": docs_context,
            "title": "Gestión Documental",
            "flash_message": flash_message,
            "flash_type": flash_type,
            "generated_certificates": generated_certificates,
            "cert_page_size_options": CERT_PAGE_SIZE_OPTIONS,
            "cert_filters": {
                "cert_page": current_cert_page,
                "cert_page_size": normalized_cert_page_size,
            },
            "cert_pagination": cert_pagination,
        },
    )
    if flash_message:
        response.delete_cookie("flash_message")
        response.delete_cookie("flash_type")

    return response


# ----------------------------------------------------------------------
# Reporte CSV global de lectura de políticas (Admin)
@router.get(
    "/reports/policies-reading-status",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    name="export_policy_reading_report",
)
def export_policy_reading_report(
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
):
    """Genera el informe global en PDF, lo descarga y lo registra como documento SGSI versionado."""
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    report_context = build_policy_reading_audit_report(
        db=db,
        responsible_username=admin_user.username,
    )
    report_context["company_name"] = settings.COMPANY_NAME.get_secret_value()
    report_context["project_name"] = settings.PROJECT_NAME.get_secret_value()

    pdf_buffer = generate_policy_reading_audit_report_pdf(report_context=report_context)
    pdf_bytes = pdf_buffer.getvalue()

    report_version = calculate_next_report_version(db=db, report_code=AUDIT_REPORT_DOC_CODE)
    persist_audit_report_as_document(
        db=db,
        admin_user=admin_user,
        pdf_bytes=pdf_bytes,
        report_version=report_version,
    )

    filename = f"Informe_Global_Lectura_Politicas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
        media_type="application/pdf",
    )


# ----------------------------------------------------------------------
# Listar Documentos (Lógica diferenciada por Rol)
@router.get(
    "/",
    response_model=List[DocumentWithReadStatus],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_documents(
    user_or_redirect: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Lista los documentos disponibles.
    - Admins: Ven todos los documentos (activos e inactivos, policies y records).
    - Usuarios: Ven solo 'policy' que estén activas (is_active=True).
    Incluye el estado de lectura (is_read_by_user) para el usuario actual.
    """
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    # 1. Definir la consulta según el rol
    if current_user.role == "admin":
        # Admin ve todo, ordenado por fecha de creación descendente
        stmt = select(Document).order_by(*DOCUMENT_SORT_ORDER)
    else:
        # Usuario normal ve solo Políticas Activas
        stmt = (
            select(Document)
            .where(Document.doc_type == "policy", Document.is_active == True)
            .order_by(*DOCUMENT_SORT_ORDER)
        )

    documents = db.execute(stmt).scalars().all()

    # 2. Obtener lecturas del usuario actual para mapear estado
    # Traemos solo los IDs y fechas de lectura de este usuario
    reads_stmt = select(DocumentRead).where(DocumentRead.user_id == current_user.id)
    user_reads = db.execute(reads_stmt).scalars().all()

    # Crear un diccionario {doc_id: read_at} para búsqueda rápida
    read_map = {
        r.document_id: r.read_at for r in user_reads if r.read_at is not None
    }

    # 3. Construir respuesta enriquecida
    results = []
    for doc in documents:
        # Convertimos el modelo SQLAlchemy al esquema Pydantic
        # DocumentWithReadStatus tiene defaults False/None para los campos extra
        doc_response = DocumentWithReadStatus.model_validate(doc)

        # Si existe en el mapa de lecturas, actualizamos el estado
        if doc.id in read_map:
            doc_response.is_read_by_user = True
            doc_response.read_at = read_map[doc.id]

        results.append(doc_response)

    return results


# ----------------------------------------------------------------------
# Estadísticas de Cumplimiento (Admin)
@router.get(
    "/stats",
    response_model=List[DocumentComplianceStats],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_compliance_stats(
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
):
    """
    Obtiene estadísticas de cumplimiento de lectura para cada política activa.
    Asigna 40% por descarga y 100% por confirmación de lectura.
    """
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    # 1. Total de usuarios activos (Base para el porcentaje)
    total_users = (
        db.scalar(select(func.count(User.id)).where(User.is_active == True)) or 0
    )

    # 2. Obtener todas las políticas activas
    policies = (
        db.execute(
            select(Document)
            .where(Document.doc_type == "policy", Document.is_active == True)
            .order_by(Document.title)
        )
        .scalars()
        .all()
    )

    stats = []
    for doc in policies:
        reads = (
            db.execute(
                select(DocumentRead)
                .join(User, DocumentRead.user_id == User.id)
                .where(
                    DocumentRead.document_id == doc.id,
                    User.is_active == True,
                )
            )
            .scalars()
            .all()
        )

        read_count = sum(1 for read in reads if read.read_at is not None)
        compliance_points = 0

        for read in reads:
            if read.read_at is not None:
                compliance_points += 100
            elif read.download_at is not None:
                compliance_points += 40

        percentage = 0.0
        if total_users > 0:
            percentage = round(compliance_points / total_users, 1)

        stats.append(
            DocumentComplianceStats(
                id=doc.id,
                title=doc.title,
                code=doc.code,
                version=doc.version,
                total_users=total_users,
                read_count=read_count,
                compliance_percentage=percentage,
            )
        )

    return stats


# ----------------------------------------------------------------------
# Subir Documento (Solo Admin)
@router.post(
    "/upload",
    status_code=status.HTTP_303_SEE_OTHER,
    include_in_schema=False,
)
async def upload_document(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=3, max_length=150)],
    doc_type: Annotated[
        str, Form(pattern="^(policy|record)$")
    ],  # Regex simple para validar enum
    description: Annotated[Optional[str], Form()] = None,
    version: Annotated[str, Form(max_length=10)] = "1.0",
    code: Annotated[Optional[str], Form(max_length=20)] = None,
):
    """
    Sube un nuevo documento al sistema.
    Valida extensión y tamaño del archivo.
    """
    if isinstance(admin_user, RedirectResponse):
        return admin_user  # Should not happen due to Depends, but safe typing

    # --- 1. Validaciones de Archivo ---

    # Validar Content-Type (MIME)
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido: {file.content_type}. Solo PDF, Word o Excel.",
        )

    # Validar Tamaño
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)  # Reset cursor

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo excede el tamaño máximo permitido ({MAX_FILE_SIZE_BYTES / 1024 / 1024} MB).",
        )

    # --- 2. Guardar en Disco ---

    upload_dir = "media/documents"
    os.makedirs(upload_dir, exist_ok=True)

    # Generar nombre seguro y único
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(upload_dir, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar el archivo en disco: {str(e)}",
        )

    # --- 3. Guardar en Base de Datos ---

    # Normalizar código a mayúsculas si existe
    final_code = code.upper() if code else None

    # Si hay código, desactivar versiones anteriores activas (Control de Versiones)
    if final_code:
        active_docs = db.execute(
            select(Document).where(
                Document.code == final_code,
                Document.is_active == True
            )
        ).scalars().all()
        for doc in active_docs:
            doc.is_active = False

    _, inferred_version = extract_document_metadata_from_filename(
        file.filename,
        default_version=version,
    )

    new_doc = Document(
        title=title,
        description=build_document_description(file.filename, description),
        version=inferred_version,
        code=final_code,
        doc_type=doc_type,
        filename=unique_filename,
        content_type=file.content_type,
        uploaded_by_id=admin_user.id,
        is_active=True,
    )

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    response = RedirectResponse(
        url=request.url_for("documents_view"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        key="flash_message",
        value="Documento agregado satisfactoriamente",
        httponly=True,
    )
    response.set_cookie(key="flash_type", value="green", httponly=True)
    return response


# ----------------------------------------------------------------------
# Subir Documentos por Lotes (Batch Upload)
@router.post(
    "/upload/batch",
    status_code=status.HTTP_303_SEE_OTHER,
    include_in_schema=False,
    name="upload_documents_batch",
)
async def upload_documents_batch(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
    files: List[UploadFile] = File(...),
    doc_type: Annotated[str, Form(pattern="^(policy|record)$")] = "record",
):
    """
    Sube múltiples documentos a la vez.
    Usa el nombre del archivo como título y asigna versión 1.0 por defecto.
    """
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    upload_dir = "media/documents"
    os.makedirs(upload_dir, exist_ok=True)

    processed_count = 0
    errors = []

    for file in files:
        # 1. Validaciones básicas por archivo
        if file.content_type not in ALLOWED_MIME_TYPES:
            errors.append(f"{file.filename}: Tipo no permitido")
            continue

        # Nombre único
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(upload_dir, unique_filename)

        try:
            # Guardar en disco
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Guardar en BD
            doc_title, doc_version = extract_document_metadata_from_filename(
                file.filename,
                default_version="1.0",
            )

            new_doc = Document(
                title=doc_title,
                description=build_document_description(
                    file.filename,
                    "Carga automática por lotes",
                ),
                version=doc_version,
                code=None,
                doc_type=doc_type,
                filename=unique_filename,
                content_type=file.content_type,
                uploaded_by_id=admin_user.id,
                is_active=True,
            )
            db.add(new_doc)
            processed_count += 1

        except Exception as e:
            errors.append(f"{file.filename}: Error interno ({str(e)})")

    db.commit()

    response = RedirectResponse(url=request.url_for("documents_view"), status_code=303)

    if errors:
        msg = f"Se subieron {processed_count} archivos. Errores: {'; '.join(errors)}"
        response.set_cookie(
            key="flash_message", value=msg[:400], httponly=True
        )  # Truncar si es muy largo
        response.set_cookie(key="flash_type", value="orange", httponly=True)
    else:
        response.set_cookie(
            key="flash_message",
            value=f"Éxito: {processed_count} documentos subidos correctamente.",
            httponly=True,
        )
        response.set_cookie(key="flash_type", value="green", httponly=True)

    return response


# ----------------------------------------------------------------------
# Eliminar documentos por código (Solo Admin)
@router.delete(
    "/by-code/{code}",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def delete_documents_by_code(
    request: Request,
    code: str,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
):
    """
    Elimina lógicamente documentos por código documental.
    Para conservar trazabilidad SGSI, se marca `is_active=False`.
    """
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    normalized_code = code.strip().upper()
    if not normalized_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código documental es obligatorio.",
        )

    documents = (
        db.execute(select(Document).where(Document.code == normalized_code))
        .scalars()
        .all()
    )

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontraron documentos con código '{normalized_code}'.",
        )

    for doc in documents:
        doc.is_active = False

    db.commit()

    client_ip = request.client.host if request.client else "Unknown"
    security_logger.warning(
        f"BAJA DOCUMENTAL POR CÓDIGO | Admin: {admin_user.username} (ID: {admin_user.id}) | "
        f"Código: {normalized_code} | Registros afectados: {len(documents)} | IP: {client_ip}"
    )

    return {
        "detail": f"Documentos con código '{normalized_code}' desactivados correctamente.",
        "code": normalized_code,
        "affected": len(documents),
    }


# ----------------------------------------------------------------------
# Descargar Documento
@router.get("/{doc_id}/download", include_in_schema=False)
def download_document(
    request: Request,
    doc_id: int,
    user_or_redirect: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Descarga el archivo físico. Verifica permisos:
    - User solo puede descargar si es 'policy'.
    - Admin puede descargar todo.
    """
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Verificación de permisos
    if current_user.role != "admin" and doc.doc_type != "policy":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para descargar este documento interno.",
        )

    if doc.doc_type == "policy" and not doc.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El documento ya no está vigente.",
        )

    if doc.doc_type == "policy":
        upsert_policy_download_read(
            db=db,
            user_id=current_user.id,
            document_id=doc.id,
        )

    # --- Middleware Log de Auditoría de Descarga ---
    client_ip = request.client.host if request.client else "Unknown"
    security_logger.info(
        f"DESCARGA SENSIBLE | Usuario: {current_user.username} (ID: {current_user.id}) | "
        f"Archivo: {doc.filename} (ID: {doc.id}) | IP: {client_ip}"
    )

    file_path = os.path.join("media/documents", doc.filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, detail="Archivo físico no encontrado en el servidor."
        )

    # content_disposition="attachment" fuerza la descarga en vez de abrirlo en el navegador
    return FileResponse(
        path=file_path,
        filename=f"{doc.title}{os.path.splitext(doc.filename)[1]}",
        media_type=doc.content_type,
    )


# ----------------------------------------------------------------------
# Helper: Generar Certificado PDF
def generate_certificate_pdf(
    user: User,
    doc: Document,
    read_record: DocumentRead,
    ip_address: str = "No disponible",
    user_agent: str = "No disponible",
    certificate_record_code: str = "No disponible",
    certificate_url: str = "No disponible",
) -> io.BytesIO:
    """
    Genera un certificado PDF basado en la plantilla example.md usando ReportLab.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    _, height = letter

    # Datos calculados
    timestamp_iso = datetime.now().isoformat()
    doc_hash = hashlib.sha256(f"{doc.title}{doc.version}".encode()).hexdigest()[:16]
    record_hash = hashlib.sha256(
        f"{user.id}{doc.id}{read_record.read_at}".encode()
    ).hexdigest()
    read_date_str = (
        read_record.read_at.strftime("%Y-%m-%d %H:%M:%S")
        if read_record.read_at
        else "No disponible"
    )
    download_date_str = (
        read_record.download_at.strftime("%Y-%m-%d %H:%M:%S")
        if read_record.download_at
        else "No disponible"
    )

    company_name = settings.COMPANY_NAME.get_secret_value()
    certificate_record_code = (
        certificate_record_code
        if certificate_record_code != "No disponible"
        else f"REG-SGSI-{doc.code or 'NA'}-{user.id}-{int(datetime.now().timestamp())}"
    )

    # Configuración de fuente
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "REGISTRO DIGITAL DE LECTURA Y COMPROMISO SGSI")

    c.setFont("Helvetica", 10)
    y = height - 80
    line_height = 14

    # Texto del certificado (Simulando la estructura del example.md)
    lines = [
        "________________________________________________________________________________",
        "1. INFORMACIÓN DEL DOCUMENTO",
        f"* Código del registro: {certificate_record_code}",
        "* Versión: 1.1",
        f"* Fecha de generación: {timestamp_iso}",
        f"* Generado por: Sistema SGSI {company_name}",
        "________________________________________________________________________________",
        "2. IDENTIFICACIÓN DEL COLABORADOR",
        f"* Nombre de usuario: {user.username}",
        f"* ID Usuario: {user.id}",
        f"* Correo corporativo: {user.email}",
        f"* Departamento: {user.department_name}",
        f"* Rol Sistema: {user.role}",
        "________________________________________________________________________________",
        "3. INFORMACIÓN DE LA POLÍTICA",
        f"* Código: {doc.code or 'N/A'}",
        f"* Nombre: {doc.title or 'N/A'}",
        f"* Descripción: {doc.description or 'N/A'}",
        f"* Versión: {doc.version}",
        f"* Hash parcial Doc: {doc_hash}",
        f"* Fecha de descarga: {download_date_str}",
        f"* Fecha de confirmación de lectura: {read_date_str}",
        "________________________________________________________________________________",
        "4. DECLARACIÓN DE LECTURA Y COMPROMISO",
        f"Yo, {user.username}, identificado en el sistema con ID {user.id}, declaro que:",
        "1. He accedido, descargado y revisado la política indicada en este registro.",
        "2. He leído y comprendido íntegramente su contenido.",
        "3. Entiendo las responsabilidades, obligaciones y lineamientos establecidos.",
        "4. Me comprometo a cumplir con todas las disposiciones de seguridad de esta información.",
        "5. Reconozco que esta aceptación forma parte del SGSI y constituye evidencia digital auditada.",
        "________________________________________________________________________________",
        "5. EVIDENCIA DE ACEPTACIÓN DIGITAL",
        "* Método de autenticación: Token",
        f"* Dirección IP: {ip_address}",
        f"* Dispositivo/navegador: {user_agent[:42]}",
        f"* Fecha de aceptación: {read_date_str}",
        f"* Código del registro del certificado: {certificate_record_code}",
        "________________________________________________________________________________",
        "6. FIRMA ELECTRÓNICA Y VALIDACIÓN",
        f"* Firma digital (hash): {record_hash}",
        "* Algoritmo: SHA-256",
        "________________________________________________________________________________",
        "7. CONTROL DE INTEGRIDAD Y TRAZABILIDAD",
        "Este registro incluye:",
        "* Hash parcial del documento de política aceptada",
        "* Hash del registro generado",
        f"* Identificador único (UUID) del documento aceptado: {doc.id}",
        "* Registro en base de datos SGSI",
        "* Log de evento en sistema",
        "* Cualquier modificación posterior invalidará la integridad del documento.",
        "________________________________________________________________________________",
        "8. CONTROL DE REGISTRO",
        "Este documento:",
        "* Es generado automáticamente por el SGSI",
        "* Se almacena en repositorio controlado",
        "* Mantiene trazabilidad con:",
        "   * Usuario",
        "   * Política",
        "   * Versión",
        f"   * Fecha de aceptación: {read_date_str}",
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
        "* Comparación del hash SHA-256 REGISTRO DIGITAL DE LECTURA Y COMPROMISO DE POLÍTICAS SGSI",
    ]

    for line in lines:
        if (
            line.startswith("___")
            or line.startswith("1.")
            or line.startswith("2.")
            or line.startswith("3.")
            or line.startswith("4.")
            or line.startswith("5.")
        ):
            c.setFont("Helvetica-Bold", 10)
        else:
            c.setFont("Helvetica", 10)

        c.drawString(50, y, line)
        y -= line_height

        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 50

    # Enlace corto y clickeable para evitar desbordar la URL completa en el certificado.
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "URL del certificado:")
    link_label = " CERTIFICADO"
    prefix_width = c.stringWidth("URL del certificado:", "Helvetica-Bold", 10)
    c.setFont("Helvetica-Bold", 10)
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


# ----------------------------------------------------------------------
# Helper: Guardar Certificado PDF
def save_certificate_pdf(
    user: User, doc: Document, read_record: DocumentRead, pdf_bytes: bytes
) -> str:
    """
    Guarda el certificado de lectura en disco bajo:
    media/documents/certificates/<username>/
    """
    _, certificate_path, _ = build_certificate_storage_paths(user, doc, read_record)
    certificates_dir = os.path.dirname(certificate_path)
    os.makedirs(certificates_dir, exist_ok=True)

    with open(certificate_path, "wb") as certificate_file:
        certificate_file.write(pdf_bytes)

    return certificate_path


def build_certificate_storage_paths(
    user: User,
    doc: Document,
    read_record: DocumentRead,
) -> tuple[str, str, str]:
    """
    Construye la ruta relativa web, la ruta física y el nombre del certificado.
    """
    safe_department = re.sub(r"[^a-zA-Z0-9_.-]", "_", user.department_name)
    safe_username = re.sub(r"[^a-zA-Z0-9_.-]", "_", user.username)
    timestamp_suffix = read_record.read_at.strftime("%Y%m%d_%H%M%S")
    filename = (
        f"Certificado_Lectura_{doc.code or doc.id}_{safe_department}_{safe_username}_{timestamp_suffix}.pdf"
    )
    relative_path = os.path.join("documents", "certificates", safe_department, filename)
    file_path = os.path.join("media", relative_path)
    return relative_path.replace("\\", "/"), file_path, filename


# ----------------------------------------------------------------------
# Confirmar Lectura (Marcar como leído) y generar certificado
@router.post(
    "/{doc_id}/read",
    # response_model omitido: retorna JSON con metadata/URL del certificado
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def mark_document_as_read(
    request: Request,
    doc_id: int,
    user_or_redirect: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """
    El usuario confirma que ha leído y comprendido una política.
    Genera y guarda el certificado PDF en servidor, y retorna la URL
    para abrirlo en una nueva pestaña desde frontend.
    """
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if doc.doc_type != "policy":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se requiere confirmación de lectura para las Políticas.",
        )

    # Verificar si ya lo leyó
    existing_read = (
        db.execute(
            select(DocumentRead).where(
                DocumentRead.user_id == current_user.id,
                DocumentRead.document_id == doc_id,
            )
        )
        .scalars()
        .first()
    )

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

    client_ip = request.client.host if request.client and request.client.host else "No disponible"
    client_user_agent = request.headers.get("user-agent", "No disponible")
    certificate_relative_path, _, certificate_filename = build_certificate_storage_paths(
        current_user,
        doc,
        existing_read,
    )
    certificate_record_code = (
        f"REG-SGSI-{doc.code or 'NA'}-{current_user.id}-{int(existing_read.read_at.timestamp())}"
    )
    certificate_url = str(
        request.url_for("media", path=certificate_relative_path)
    )

    # Generar Certificado PDF
    pdf_buffer = generate_certificate_pdf(
        current_user,
        doc,
        existing_read,
        ip_address=client_ip,
        user_agent=client_user_agent,
        certificate_record_code=certificate_record_code,
        certificate_url=certificate_url,
    )
    pdf_bytes = pdf_buffer.getvalue()

    # Guardar copia del certificado en el servidor para auditoría
    save_certificate_pdf(current_user, doc, existing_read, pdf_bytes)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "detail": "Lectura confirmada y certificado generado.",
            "action": "certificate_generated",
            "certificate_filename": certificate_filename,
            "certificate_url": certificate_url,
        },
    )
