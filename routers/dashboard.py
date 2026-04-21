from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    status,
)

from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

# Import's Locales
from models.documents import Document, DocumentRead
from models.lms import LMSPost, LMSQuiz, LMSQuizAttempt
from services import lms_service
from utils.auth import CurrentUser
from utils.database import get_db
from utils.stats import get_dashboard_stats


# Instancia de las rutas
router = APIRouter()
# Configurar motor de plantillas
templates = Jinja2Templates(directory="templates")


# ----------------------------------------------------------------------
# Muestra el Dashboard
@router.get(
    "/",
    name="dashboard",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    tags=["Dashboard"],
    include_in_schema=False,
)
def dashboard(
    request: Request,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    data = get_dashboard_stats(db, current_user=current_user)

    # --- Calcular Lecturas Pendientes ---
    # 1. Obtener todas las políticas activas
    policies = (
        db.execute(
            select(Document).where(
                Document.doc_type == "policy", Document.is_active == True
            )
        )
        .scalars()
        .all()
    )

    # 2. Obtener IDs de documentos ya leídos por el usuario
    user_reads = (
        db.execute(
            select(DocumentRead.document_id).where(
                DocumentRead.user_id == current_user.id,
                DocumentRead.read_at.is_not(None),
            )
        )
        .scalars()
        .all()
    )

    # 3. Filtrar: Políticas Activas - Leídas = Pendientes
    pending_documents = [doc for doc in policies if doc.id not in user_reads]

    # --- Calcular Evaluaciones Pendientes ---
    active_period = lms_service.get_active_period(db)
    evaluable_posts = (
        db.execute(
            select(LMSPost)
            .join(LMSQuiz, LMSQuiz.post_id == LMSPost.id)
            .where(
                LMSPost.status == "published",
                LMSQuiz.is_active == True,
            )
            .distinct()
            .order_by(LMSPost.id.asc())
        )
        .scalars()
        .all()
    )
    approved_post_ids = set(
        db.execute(
            select(LMSQuizAttempt.post_id)
            .where(
                LMSQuizAttempt.user_id == current_user.id,
                LMSQuizAttempt.period_id == active_period.id,
                LMSQuizAttempt.is_passed == True,
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    pending_evaluations = [
        post for post in evaluable_posts if post.id not in approved_post_ids
    ]

    return templates.TemplateResponse(
        request,
        "dashboard/dashboard.html",
        {
            "user": current_user,
            "data": data,
            "pending_documents": pending_documents,
            "pending_evaluations": pending_evaluations,
        },
    )
