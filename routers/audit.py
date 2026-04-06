from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.documents import Document, DocumentRead
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
MAPPING_ALLOWED_STATUS = {"Implementado", "Parcial", "Pendiente", "No aplica"}


@dataclass
class AuditConfirmationRow:
    policy_code: str
    policy_title: str
    username: str
    department_name: str
    download_at: datetime | None
    read_at: datetime | None
    status: str


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
    responsible_user_id: Annotated[int | None, Form()] = None,
    status_value: Annotated[str, Form(alias="status")] = "Pendiente",
):
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    normalized_control = control_iso.strip().upper()
    normalized_status = status_value.strip().title()
    if normalized_status not in MAPPING_ALLOWED_STATUS:
        normalized_status = "Pendiente"

    document = db.get(Document, document_id)
    if not document or document.doc_type != "policy":
        response = RedirectResponse(url=request.url_for("audit_view"), status_code=303)
        response.set_cookie(
            key="flash_message",
            value="Debe seleccionar una política válida para el mapeo ISO.",
            httponly=True,
        )
        response.set_cookie(key="flash_type", value="red", httponly=True)
        return response

    responsible = None
    if responsible_user_id:
        responsible = db.get(User, responsible_user_id)
        if responsible is None:
            response = RedirectResponse(url=request.url_for("audit_view"), status_code=303)
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
    response = RedirectResponse(url=request.url_for("audit_view"), status_code=303)
    response.set_cookie(
        key="flash_message",
        value="Control ISO mapeado correctamente.",
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
):
    if isinstance(admin_user, RedirectResponse):
        return admin_user

    mapping = db.get(ISOControlMapping, mapping_id)
    if mapping:
        db.delete(mapping)
        db.commit()

    response = RedirectResponse(url=request.url_for("audit_view"), status_code=303)
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
):
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    documents = db.execute(
        select(Document).order_by(Document.created_at.desc(), Document.id.desc())
    ).scalars().all()
    policy_documents = [doc for doc in documents if doc.doc_type == "policy"]
    active_policy_documents = [doc for doc in policy_documents if doc.is_active]
    policies_by_id = {doc.id: doc for doc in policy_documents}

    users = db.execute(select(User).order_by(User.id.asc())).scalars().all()
    users_by_id = {user.id: user for user in users}

    reads = db.execute(select(DocumentRead).order_by(DocumentRead.id.desc())).scalars().all()
    confirmation_rows: list[AuditConfirmationRow] = []
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

        confirmation_rows.append(
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

    mapping_rows = (
        db.execute(
            select(ISOControlMapping).order_by(
                ISOControlMapping.control_iso.asc(),
                ISOControlMapping.id.desc(),
            )
        )
        .scalars()
        .all()
    )

    mapped_rows = []
    for mapping in mapping_rows:
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
                "responsible": responsible_user.username if responsible_user else "Sin asignar",
                "status": mapping.status,
            }
        )

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
            "users": users,
            "policy_documents": policy_documents,
            "active_policy_documents": active_policy_documents,
            "confirmation_rows": confirmation_rows,
            "mapped_rows": mapped_rows,
            "mapping_allowed_status": sorted(MAPPING_ALLOWED_STATUS),
        },
    )
    if flash_message:
        response.delete_cookie("flash_message")
        response.delete_cookie("flash_type")

    return response
