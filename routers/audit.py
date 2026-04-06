from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from models.documents import Document, DocumentRead
from models.iso_controls import ISOControl
from models.iso_control_mappings import ISOControlMapping
from models.users import User
from utils.auth import (
    CurrentAuditorOrAdmin,
    get_current_admin,
    get_flash_messages,
)
from utils.database import get_db
from utils.stats import get_dashboard_stats


router = APIRouter()
templates = Jinja2Templates(directory="templates")
MAPPING_ALLOWED_STATUS = {"Implementado", "Parcial", "Pendiente", "No Aplica"}
MAPPING_SORT_FIELDS = {"control_iso", "status", "document", "responsible", "created_at"}
DEFAULT_PAGE_SIZE = 20
PAGE_SIZE_OPTIONS = [10, 20, 50, 100]


@dataclass
class AuditConfirmationRow:
    policy_code: str
    policy_title: str
    username: str
    department_name: str
    download_at: datetime | None
    read_at: datetime | None
    status: str


def _normalize_status(status_value: str | None) -> str:
    normalized_status = (status_value or "Pendiente").strip().title()
    if normalized_status not in MAPPING_ALLOWED_STATUS:
        return "Pendiente"
    return normalized_status


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned == "":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _normalize_sort_field(value: str | None) -> str:
    candidate = (value or "control_iso").strip().lower()
    if candidate not in MAPPING_SORT_FIELDS:
        return "control_iso"
    return candidate


def _normalize_sort_dir(value: str | None) -> str:
    return "desc" if (value or "").strip().lower() == "desc" else "asc"


def _normalize_page_size(value: int | None) -> int:
    if value in PAGE_SIZE_OPTIONS:
        return int(value)
    return DEFAULT_PAGE_SIZE


def _build_audit_redirect_url(
    request: Request,
    control_q: str = "",
    status_filter: str = "",
    responsible_filter: str = "",
    sort_by: str = "control_iso",
    sort_dir: str = "asc",
    page_size: int = DEFAULT_PAGE_SIZE,
    page: int = 1,
    doc_page_size: int = DEFAULT_PAGE_SIZE,
    doc_page: int = 1,
    confirm_page_size: int = DEFAULT_PAGE_SIZE,
    confirm_page: int = 1,
) -> str:
    params = {
        "control_q": control_q,
        "status_filter": status_filter,
        "responsible_filter": responsible_filter,
        "sort_by": _normalize_sort_field(sort_by),
        "sort_dir": _normalize_sort_dir(sort_dir),
        "page_size": _normalize_page_size(page_size),
        "page": max(1, page),
        "doc_page_size": _normalize_page_size(doc_page_size),
        "doc_page": max(1, doc_page),
        "confirm_page_size": _normalize_page_size(confirm_page_size),
        "confirm_page": max(1, confirm_page),
    }
    clean_params = {k: v for k, v in params.items() if v not in ("", None)}
    return f"{request.url_for('audit_view')}?{urlencode(clean_params)}"


@router.post(
    "/mappings/create",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    include_in_schema=False,
    name="create_iso_control_mapping",
)
def create_iso_control_mapping(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
    control_iso: Annotated[str, Form(min_length=2, max_length=50)],
    document_id: Annotated[int, Form()],
    evidence: Annotated[str | None, Form()] = None,
    responsible_user_id: Annotated[str | None, Form()] = None,
    status_value: Annotated[str, Form(alias="status")] = "Pendiente",
    control_q: Annotated[str | None, Form()] = None,
    status_filter: Annotated[str | None, Form()] = None,
    responsible_filter: Annotated[str | None, Form()] = None,
    sort_by: Annotated[str | None, Form()] = None,
    sort_dir: Annotated[str | None, Form()] = None,
    page_size: Annotated[int | None, Form()] = None,
    page: Annotated[int | None, Form()] = None,
    doc_page_size: Annotated[int | None, Form()] = None,
    doc_page: Annotated[int | None, Form()] = None,
    confirm_page_size: Annotated[int | None, Form()] = None,
    confirm_page: Annotated[int | None, Form()] = None,
):
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    normalized_control = control_iso.strip().upper()
    normalized_status = _normalize_status(status_value)
    responsible_user_id_value = _parse_optional_int(responsible_user_id)

    document = db.get(Document, document_id)
    if not document or document.doc_type != "policy":
        response = RedirectResponse(
            url=_build_audit_redirect_url(
                request=request,
                control_q=control_q or "",
                status_filter=status_filter or "",
                responsible_filter=responsible_filter or "",
                sort_by=sort_by or "control_iso",
                sort_dir=sort_dir or "asc",
                page_size=page_size or DEFAULT_PAGE_SIZE,
                page=page or 1,
                doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
                doc_page=doc_page or 1,
                confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
                confirm_page=confirm_page or 1,
            ),
            status_code=303,
        )
        response.set_cookie(
            key="flash_message",
            value="Debe seleccionar una política válida para el mapeo ISO.",
            httponly=True,
        )
        response.set_cookie(key="flash_type", value="red", httponly=True)
        return response

    responsible = None
    if responsible_user_id_value:
        responsible = db.get(User, responsible_user_id_value)
        if responsible is None:
            response = RedirectResponse(
                url=_build_audit_redirect_url(
                    request=request,
                    control_q=control_q or "",
                    status_filter=status_filter or "",
                    responsible_filter=responsible_filter or "",
                    sort_by=sort_by or "control_iso",
                    sort_dir=sort_dir or "asc",
                    page_size=page_size or DEFAULT_PAGE_SIZE,
                    page=page or 1,
                    doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
                    doc_page=doc_page or 1,
                    confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
                    confirm_page=confirm_page or 1,
                ),
                status_code=303,
            )
            response.set_cookie(
                key="flash_message",
                value="El responsable seleccionado no existe.",
                httponly=True,
            )
            response.set_cookie(key="flash_type", value="red", httponly=True)
            return response

    existing = (
        db.execute(
            select(ISOControlMapping).where(
                ISOControlMapping.control_iso == normalized_control,
                ISOControlMapping.document_id == document_id,
            )
        )
        .scalars()
        .first()
    )

    if existing:
        existing.evidence = (evidence or "").strip() or existing.evidence
        existing.responsible_user_id = responsible.id if responsible else existing.responsible_user_id
        existing.status = normalized_status
    else:
        db.add(
            ISOControlMapping(
                control_iso=normalized_control,
                document_id=document_id,
                evidence=(evidence or "").strip() or None,
                responsible_user_id=responsible.id if responsible else None,
                status=normalized_status,
            )
        )

    db.commit()
    response = RedirectResponse(
        url=_build_audit_redirect_url(
            request=request,
            control_q=control_q or "",
            status_filter=status_filter or "",
            responsible_filter=responsible_filter or "",
            sort_by=sort_by or "control_iso",
            sort_dir=sort_dir or "asc",
            page_size=page_size or DEFAULT_PAGE_SIZE,
            page=page or 1,
            doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
            doc_page=doc_page or 1,
            confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
            confirm_page=confirm_page or 1,
        ),
        status_code=303,
    )
    response.set_cookie(
        key="flash_message",
        value="Control ISO mapeado correctamente.",
        httponly=True,
    )
    response.set_cookie(key="flash_type", value="green", httponly=True)
    return response


@router.post(
    "/mappings/{mapping_id}/update",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    include_in_schema=False,
    name="update_iso_control_mapping",
)
def update_iso_control_mapping(
    request: Request,
    mapping_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
    control_iso: Annotated[str, Form(min_length=2, max_length=50)],
    evidence: Annotated[str | None, Form()] = None,
    responsible_user_id: Annotated[str | None, Form()] = None,
    status_value: Annotated[str, Form(alias="status")] = "Pendiente",
    control_q: Annotated[str | None, Form()] = None,
    status_filter: Annotated[str | None, Form()] = None,
    responsible_filter: Annotated[str | None, Form()] = None,
    sort_by: Annotated[str | None, Form()] = None,
    sort_dir: Annotated[str | None, Form()] = None,
    page_size: Annotated[int | None, Form()] = None,
    page: Annotated[int | None, Form()] = None,
    doc_page_size: Annotated[int | None, Form()] = None,
    doc_page: Annotated[int | None, Form()] = None,
    confirm_page_size: Annotated[int | None, Form()] = None,
    confirm_page: Annotated[int | None, Form()] = None,
):
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    mapping = db.get(ISOControlMapping, mapping_id)
    if mapping is None:
        response = RedirectResponse(
            url=_build_audit_redirect_url(
                request=request,
                control_q=control_q or "",
                status_filter=status_filter or "",
                responsible_filter=responsible_filter or "",
                sort_by=sort_by or "control_iso",
                sort_dir=sort_dir or "asc",
                page_size=page_size or DEFAULT_PAGE_SIZE,
                page=page or 1,
                doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
                doc_page=doc_page or 1,
                confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
                confirm_page=confirm_page or 1,
            ),
            status_code=303,
        )
        response.set_cookie(
            key="flash_message",
            value="Mapeo ISO no encontrado.",
            httponly=True,
        )
        response.set_cookie(key="flash_type", value="red", httponly=True)
        return response

    normalized_control = control_iso.strip().upper()
    normalized_status = _normalize_status(status_value)
    responsible_user_id_value = _parse_optional_int(responsible_user_id)

    duplicate = (
        db.execute(
            select(ISOControlMapping).where(
                ISOControlMapping.document_id == mapping.document_id,
                ISOControlMapping.control_iso == normalized_control,
                ISOControlMapping.id != mapping.id,
            )
        )
        .scalars()
        .first()
    )
    if duplicate:
        response = RedirectResponse(
            url=_build_audit_redirect_url(
                request=request,
                control_q=control_q or "",
                status_filter=status_filter or "",
                responsible_filter=responsible_filter or "",
                sort_by=sort_by or "control_iso",
                sort_dir=sort_dir or "asc",
                page_size=page_size or DEFAULT_PAGE_SIZE,
                page=page or 1,
                doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
                doc_page=doc_page or 1,
                confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
                confirm_page=confirm_page or 1,
            ),
            status_code=303,
        )
        response.set_cookie(
            key="flash_message",
            value="Ya existe ese Control ISO para el mismo documento.",
            httponly=True,
        )
        response.set_cookie(key="flash_type", value="red", httponly=True)
        return response

    if responsible_user_id_value:
        responsible = db.get(User, responsible_user_id_value)
        if responsible is None:
            response = RedirectResponse(
                url=_build_audit_redirect_url(
                    request=request,
                    control_q=control_q or "",
                    status_filter=status_filter or "",
                    responsible_filter=responsible_filter or "",
                    sort_by=sort_by or "control_iso",
                    sort_dir=sort_dir or "asc",
                    page_size=page_size or DEFAULT_PAGE_SIZE,
                    page=page or 1,
                    doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
                    doc_page=doc_page or 1,
                    confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
                    confirm_page=confirm_page or 1,
                ),
                status_code=303,
            )
            response.set_cookie(
                key="flash_message",
                value="El responsable seleccionado no existe.",
                httponly=True,
            )
            response.set_cookie(key="flash_type", value="red", httponly=True)
            return response

    mapping.control_iso = normalized_control
    mapping.evidence = (evidence or "").strip() or None
    mapping.responsible_user_id = responsible_user_id_value
    mapping.status = normalized_status
    db.commit()

    response = RedirectResponse(
        url=_build_audit_redirect_url(
            request=request,
            control_q=control_q or "",
            status_filter=status_filter or "",
            responsible_filter=responsible_filter or "",
            sort_by=sort_by or "control_iso",
            sort_dir=sort_dir or "asc",
            page_size=page_size or DEFAULT_PAGE_SIZE,
            page=page or 1,
            doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
            doc_page=doc_page or 1,
            confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
            confirm_page=confirm_page or 1,
        ),
        status_code=303,
    )
    response.set_cookie(
        key="flash_message",
        value="Mapeo ISO actualizado correctamente.",
        httponly=True,
    )
    response.set_cookie(key="flash_type", value="green", httponly=True)
    return response


@router.post(
    "/mappings/{mapping_id}/delete",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    include_in_schema=False,
    name="delete_iso_control_mapping",
)
def delete_iso_control_mapping(
    request: Request,
    mapping_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(get_current_admin)],
    control_q: Annotated[str | None, Form()] = None,
    status_filter: Annotated[str | None, Form()] = None,
    responsible_filter: Annotated[str | None, Form()] = None,
    sort_by: Annotated[str | None, Form()] = None,
    sort_dir: Annotated[str | None, Form()] = None,
    page_size: Annotated[int | None, Form()] = None,
    page: Annotated[int | None, Form()] = None,
    doc_page_size: Annotated[int | None, Form()] = None,
    doc_page: Annotated[int | None, Form()] = None,
    confirm_page_size: Annotated[int | None, Form()] = None,
    confirm_page: Annotated[int | None, Form()] = None,
):
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    mapping = db.get(ISOControlMapping, mapping_id)
    if mapping:
        db.delete(mapping)
        db.commit()

    response = RedirectResponse(
        url=_build_audit_redirect_url(
            request=request,
            control_q=control_q or "",
            status_filter=status_filter or "",
            responsible_filter=responsible_filter or "",
            sort_by=sort_by or "control_iso",
            sort_dir=sort_dir or "asc",
            page_size=page_size or DEFAULT_PAGE_SIZE,
            page=page or 1,
            doc_page_size=doc_page_size or DEFAULT_PAGE_SIZE,
            doc_page=doc_page or 1,
            confirm_page_size=confirm_page_size or DEFAULT_PAGE_SIZE,
            confirm_page=confirm_page or 1,
        ),
        status_code=303,
    )
    response.set_cookie(
        key="flash_message",
        value="Mapeo ISO eliminado.",
        httponly=True,
    )
    response.set_cookie(key="flash_type", value="green", httponly=True)
    return response


@router.get(
    "/view",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    name="audit_view",
)
def audit_view(
    request: Request,
    user_or_redirect: CurrentAuditorOrAdmin,
    db: Annotated[Session, Depends(get_db)],
    control_q: str = "",
    status_filter: str = "",
    responsible_filter: int | None = None,
    sort_by: str = "control_iso",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    doc_page: int = 1,
    doc_page_size: int = DEFAULT_PAGE_SIZE,
    confirm_page: int = 1,
    confirm_page_size: int = DEFAULT_PAGE_SIZE,
):
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    documents_all = db.execute(
        select(Document).order_by(Document.created_at.desc(), Document.id.desc())
    ).scalars().all()
    policy_documents = [doc for doc in documents_all if doc.doc_type == "policy"]
    active_policy_documents = [doc for doc in policy_documents if doc.is_active]
    policies_by_id = {doc.id: doc for doc in policy_documents}

    users = db.execute(select(User).order_by(User.id.asc())).scalars().all()
    users_by_id = {user.id: user for user in users}
    iso_controls = db.execute(
        select(ISOControl).order_by(ISOControl.control.asc())
    ).scalars().all()

    controls_by_theme: dict[str, list[ISOControl]] = {}
    for control in iso_controls:
        controls_by_theme.setdefault(control.tema, []).append(control)
    iso_control_options = [
        {
            "tema": control.tema,
            "control": control.control,
            "nombre": control.nombre,
        }
        for control in iso_controls
    ]

    reads = db.execute(select(DocumentRead).order_by(DocumentRead.id.desc())).scalars().all()
    confirmation_rows_all: list[AuditConfirmationRow] = []
    for read in reads:
        policy = policies_by_id.get(read.document_id)
        user = users_by_id.get(read.user_id)
        if policy is None or user is None:
            continue

        if read.read_at is not None:
            status_value = "Confirmado"
        elif read.download_at is not None:
            status_value = "Descargado - pendiente"
        else:
            status_value = "Sin evidencia"

        confirmation_rows_all.append(
            AuditConfirmationRow(
                policy_code=policy.code or f"POL-{policy.id}",
                policy_title=policy.title,
                username=user.username,
                department_name=user.department_name,
                download_at=read.download_at,
                read_at=read.read_at,
                status=status_value,
            )
        )

    normalized_sort_by = _normalize_sort_field(sort_by)
    normalized_sort_dir = _normalize_sort_dir(sort_dir)
    normalized_page_size = _normalize_page_size(page_size)
    current_page = max(1, int(page))
    normalized_doc_page_size = _normalize_page_size(doc_page_size)
    current_doc_page = max(1, int(doc_page))
    normalized_confirm_page_size = _normalize_page_size(confirm_page_size)
    current_confirm_page = max(1, int(confirm_page))

    global_query_state = {
        "control_q": control_q,
        "status_filter": status_filter.strip().title() if status_filter else "",
        "responsible_filter": responsible_filter or "",
        "sort_by": normalized_sort_by,
        "sort_dir": normalized_sort_dir,
        "page_size": normalized_page_size,
        "page": current_page,
        "doc_page_size": normalized_doc_page_size,
        "doc_page": current_doc_page,
        "confirm_page_size": normalized_confirm_page_size,
        "confirm_page": current_confirm_page,
    }

    def build_query_url(**updates: int | str) -> str:
        params = {**global_query_state, **updates}
        clean_params = {k: v for k, v in params.items() if v not in ("", None)}
        return f"{request.url_for('audit_view')}?{urlencode(clean_params)}"

    mapping_base_stmt = (
        select(ISOControlMapping, Document.title.label("document_title"), User.username.label("responsible_username"))
        .join(Document, Document.id == ISOControlMapping.document_id)
        .outerjoin(User, User.id == ISOControlMapping.responsible_user_id)
        .where(Document.doc_type == "policy")
    )

    if control_q.strip():
        mapping_base_stmt = mapping_base_stmt.where(
            ISOControlMapping.control_iso.ilike(f"%{control_q.strip()}%")
        )
    if status_filter.strip():
        mapping_base_stmt = mapping_base_stmt.where(
            ISOControlMapping.status == status_filter.strip().title()
        )
    if responsible_filter:
        mapping_base_stmt = mapping_base_stmt.where(
            ISOControlMapping.responsible_user_id == responsible_filter
        )

    count_stmt = select(func.count(ISOControlMapping.id)).select_from(
        ISOControlMapping
    ).join(Document, Document.id == ISOControlMapping.document_id).where(Document.doc_type == "policy")
    if control_q.strip():
        count_stmt = count_stmt.where(
            ISOControlMapping.control_iso.ilike(f"%{control_q.strip()}%")
        )
    if status_filter.strip():
        count_stmt = count_stmt.where(
            ISOControlMapping.status == status_filter.strip().title()
        )
    if responsible_filter:
        count_stmt = count_stmt.where(
            ISOControlMapping.responsible_user_id == responsible_filter
        )

    total_items = db.execute(count_stmt).scalar() or 0
    total_pages = max(1, (total_items + normalized_page_size - 1) // normalized_page_size)
    current_page = min(current_page, total_pages)

    sort_field_map = {
        "control_iso": ISOControlMapping.control_iso,
        "status": ISOControlMapping.status,
        "document": Document.title,
        "responsible": User.username,
        "created_at": ISOControlMapping.created_at,
    }
    sort_column = sort_field_map[normalized_sort_by]
    sort_expression = desc(sort_column) if normalized_sort_dir == "desc" else asc(sort_column)

    mapping_rows = db.execute(
        mapping_base_stmt
        .order_by(sort_expression, ISOControlMapping.id.desc())
        .offset((current_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()

    def build_page_url(target_page: int) -> str:
        return build_query_url(page=target_page)

    mapped_rows = []
    for mapping, _, responsible_username in mapping_rows:
        document = policies_by_id.get(mapping.document_id)
        if document is None:
            continue

        responsible_user = users_by_id.get(mapping.responsible_user_id) if mapping.responsible_user_id else None
        mapped_rows.append(
            {
                "id": mapping.id,
                "control_iso": mapping.control_iso,
                "document_name": f"{document.title} v{document.version}",
                "evidence": mapping.evidence or "Sin evidencia registrada",
                "responsible": responsible_user.username if responsible_user else (responsible_username or "Sin asignar"),
                "responsible_user_id": mapping.responsible_user_id,
                "status": mapping.status,
            }
        )

    pagination = {
        "page": current_page,
        "page_size": normalized_page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_url": build_page_url(current_page - 1) if current_page > 1 else "",
        "next_url": build_page_url(current_page + 1) if current_page < total_pages else "",
        "first_url": build_page_url(1),
        "last_url": build_page_url(total_pages),
        "window_start": ((current_page - 1) * normalized_page_size) + 1 if total_items else 0,
        "window_end": min(current_page * normalized_page_size, total_items),
    }

    documents_total = len(documents_all)
    docs_total_pages = max(1, (documents_total + normalized_doc_page_size - 1) // normalized_doc_page_size)
    current_doc_page = min(current_doc_page, docs_total_pages)
    docs_start_idx = (current_doc_page - 1) * normalized_doc_page_size
    documents = documents_all[docs_start_idx: docs_start_idx + normalized_doc_page_size]
    docs_pagination = {
        "page": current_doc_page,
        "page_size": normalized_doc_page_size,
        "total_items": documents_total,
        "total_pages": docs_total_pages,
        "has_prev": current_doc_page > 1,
        "has_next": current_doc_page < docs_total_pages,
        "prev_url": build_query_url(doc_page=current_doc_page - 1) if current_doc_page > 1 else "",
        "next_url": build_query_url(doc_page=current_doc_page + 1) if current_doc_page < docs_total_pages else "",
        "first_url": build_query_url(doc_page=1),
        "last_url": build_query_url(doc_page=docs_total_pages),
        "window_start": ((current_doc_page - 1) * normalized_doc_page_size) + 1 if documents_total else 0,
        "window_end": min(current_doc_page * normalized_doc_page_size, documents_total),
    }

    confirmations_total = len(confirmation_rows_all)
    confirmations_total_pages = max(1, (confirmations_total + normalized_confirm_page_size - 1) // normalized_confirm_page_size)
    current_confirm_page = min(current_confirm_page, confirmations_total_pages)
    confirms_start_idx = (current_confirm_page - 1) * normalized_confirm_page_size
    confirmation_rows = confirmation_rows_all[confirms_start_idx: confirms_start_idx + normalized_confirm_page_size]
    confirm_pagination = {
        "page": current_confirm_page,
        "page_size": normalized_confirm_page_size,
        "total_items": confirmations_total,
        "total_pages": confirmations_total_pages,
        "has_prev": current_confirm_page > 1,
        "has_next": current_confirm_page < confirmations_total_pages,
        "prev_url": build_query_url(confirm_page=current_confirm_page - 1) if current_confirm_page > 1 else "",
        "next_url": build_query_url(confirm_page=current_confirm_page + 1) if current_confirm_page < confirmations_total_pages else "",
        "first_url": build_query_url(confirm_page=1),
        "last_url": build_query_url(confirm_page=confirmations_total_pages),
        "window_start": ((current_confirm_page - 1) * normalized_confirm_page_size) + 1 if confirmations_total else 0,
        "window_end": min(current_confirm_page * normalized_confirm_page_size, confirmations_total),
    }

    sort_fields = [
        {"value": "control_iso", "label": "Control ISO"},
        {"value": "status", "label": "Estado"},
        {"value": "document", "label": "Documento"},
        {"value": "responsible", "label": "Responsable"},
        {"value": "created_at", "label": "Fecha creación"},
    ]

    sort_directions = [
        {"value": "asc", "label": "Ascendente"},
        {"value": "desc", "label": "Descendente"},
    ]

    flash_message, flash_type = get_flash_messages(request)
    response = templates.TemplateResponse(
        request=request,
        name="dashboard/audit.html",
        context={
            "user": current_user,
            "data": get_dashboard_stats(db, current_user=current_user),
            "title": "Auditoría",
            "flash_message": flash_message,
            "flash_type": flash_type,
            "documents": documents,
            "documents_total": documents_total,
            "users": users,
            "policy_documents": policy_documents,
            "active_policy_documents": active_policy_documents,
            "confirmation_rows": confirmation_rows,
            "confirmation_total": confirmations_total,
            "mapped_rows": mapped_rows,
            "mapping_allowed_status": sorted(MAPPING_ALLOWED_STATUS),
            "page_size_options": PAGE_SIZE_OPTIONS,
            "filters": {
                "control_q": control_q,
                "status_filter": status_filter.strip().title() if status_filter else "",
                "responsible_filter": responsible_filter,
                "sort_by": normalized_sort_by,
                "sort_dir": normalized_sort_dir,
                "page_size": normalized_page_size,
                "doc_page_size": normalized_doc_page_size,
                "doc_page": current_doc_page,
                "confirm_page_size": normalized_confirm_page_size,
                "confirm_page": current_confirm_page,
            },
            "pagination": pagination,
            "docs_pagination": docs_pagination,
            "confirm_pagination": confirm_pagination,
            "sort_fields": sort_fields,
            "sort_directions": sort_directions,
            "controls_by_theme": controls_by_theme,
            "iso_control_options": iso_control_options,
        },
    )
    if flash_message:
        response.delete_cookie("flash_message")
        response.delete_cookie("flash_type")

    return response
