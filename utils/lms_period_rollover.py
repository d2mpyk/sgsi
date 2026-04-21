"""Proceso de rollover semestral para LMS (enero/julio)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.lms_service import get_active_period
from utils.database import SessionLocal


def ensure_lms_period_rollover_db(db: Session):
    """
    Garantiza que exista y quede activo el periodo correspondiente a la fecha actual.
    Es idempotente: puede ejecutarse en cada arranque sin duplicar periodos.
    """
    return get_active_period(db)


def ensure_lms_period_rollover() -> None:
    """Ejecuta el rollover usando una sesión local de base de datos."""
    db = SessionLocal()
    try:
        ensure_lms_period_rollover_db(db)
    finally:
        db.close()
