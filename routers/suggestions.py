from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.suggestions import Suggestion
from models.users import User
from utils.auth import CurrentUser, get_flash_messages
from utils.database import get_db
from utils.stats import get_dashboard_stats


router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get(
    "/view",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    name="suggestions_view",
)
def suggestions_view(
    request: Request,
    user_or_redirect: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    stmt = (
        select(Suggestion, User.username)
        .join(User, Suggestion.id_user == User.id)
        .order_by(Suggestion.created_at.desc())
    )
    if current_user.role != "admin":
        stmt = stmt.where(Suggestion.id_user == current_user.id)

    suggestion_rows = db.execute(stmt).all()
    suggestions = [
        {
            "id": suggestion.id,
            "id_user": suggestion.id_user,
            "username": username,
            "suggestion": suggestion.suggestion,
            "created_at": suggestion.created_at,
        }
        for suggestion, username in suggestion_rows
    ]

    flash_message, flash_type = get_flash_messages(request)
    is_admin_view = current_user.role == "admin"

    response = templates.TemplateResponse(
        request=request,
        name="dashboard/suggestions.html",
        context={
            "user": current_user,
            "data": get_dashboard_stats(db, current_user=current_user),
            "suggestions": suggestions,
            "title": "Sugerencias",
            "is_admin_view": is_admin_view,
            "flash_message": flash_message,
            "flash_type": flash_type,
        },
    )
    if flash_message:
        response.delete_cookie("flash_message")
        response.delete_cookie("flash_type")

    return response


@router.post(
    "/create",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    include_in_schema=False,
    name="create_suggestion",
)
def create_suggestion(
    request: Request,
    user_or_redirect: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    suggestion: Annotated[str, Form(min_length=10)],
):
    if isinstance(user_or_redirect, RedirectResponse):
        return user_or_redirect
    current_user = user_or_redirect

    new_suggestion = Suggestion(
        id_user=current_user.id,
        suggestion=suggestion.strip(),
    )
    db.add(new_suggestion)
    db.commit()

    response = RedirectResponse(
        url=request.url_for("suggestions_view"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        key="flash_message",
        value="Sugerencia enviada correctamente.",
        httponly=True,
    )
    response.set_cookie(key="flash_type", value="green", httponly=True)
    return response
