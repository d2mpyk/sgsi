from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.documents import Document, DocumentRead
from models.users import User
from utils.auth import (
    CurrentAuditorOrAdmin,
    get_flash_messages,
)
from utils.database import get_db
from utils.stats import get_dashboard_stats


router = APIRouter()
templates = Jinja2Templates(directory="templates")
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


def _normalize_page_size(value: int | None) -> int:
    if value in PAGE_SIZE_OPTIONS:
        return int(value)
    return DEFAULT_PAGE_SIZE


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

    users_by_id = {
        user.id: user for user in db.execute(select(User).order_by(User.id.asc())).scalars().all()
    }

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

    normalized_doc_page_size = _normalize_page_size(doc_page_size)
    current_doc_page = max(1, int(doc_page))
    normalized_confirm_page_size = _normalize_page_size(confirm_page_size)
    current_confirm_page = max(1, int(confirm_page))

    global_query_state: dict[str, int] = {
        "doc_page_size": normalized_doc_page_size,
        "doc_page": current_doc_page,
        "confirm_page_size": normalized_confirm_page_size,
        "confirm_page": current_confirm_page,
    }

    def build_query_url(**updates: int) -> str:
        params = {**global_query_state, **updates}
        return (
            f"{request.url_for('audit_view')}?"
            f"doc_page_size={params['doc_page_size']}&doc_page={params['doc_page']}"
            f"&confirm_page_size={params['confirm_page_size']}&confirm_page={params['confirm_page']}"
        )

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
            "policy_documents": policy_documents,
            "active_policy_documents": active_policy_documents,
            "confirmation_rows": confirmation_rows,
            "confirmation_total": confirmations_total,
            "page_size_options": PAGE_SIZE_OPTIONS,
            "filters": {
                "doc_page_size": normalized_doc_page_size,
                "doc_page": current_doc_page,
                "confirm_page_size": normalized_confirm_page_size,
                "confirm_page": current_confirm_page,
            },
            "docs_pagination": docs_pagination,
            "confirm_pagination": confirm_pagination,
        },
    )
    if flash_message:
        response.delete_cookie("flash_message")
        response.delete_cookie("flash_type")

    return response
