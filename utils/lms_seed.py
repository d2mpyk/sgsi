"""Seed idempotente del catálogo base de temas LMS SGSI."""
from __future__ import annotations

from datetime import UTC, datetime
import re

from sqlalchemy.orm import Session

from models.lms import LMSPost
from utils.database import SessionLocal


TOPICS = [
    "FUNDAMENTOS DEL SGSI",
    "ALCANCE Y CONTEXTO DEL SGSI",
    "MARCO LEGAL Y CUMPLIMIENTO",
    "CONCIENTIZACIÓN EN SEGURIDAD (A.6.3)",
    "ROLES Y RESPONSABILIDADES",
    "PROCESO SGSI (PDCA)",
    "RIESGOS DE SEGURIDAD",
    "CONTROLES DE SEGURIDAD (SoA)",
    "USO DE PLATAFORMAS SGSI",
    "CUMPLIMIENTO Y AUDITORÍA",
]


def _slugify(value: str) -> str:
    normalized = value.lower().strip()
    normalized = normalized.replace("á", "a").replace("é", "e").replace("í", "i")
    normalized = normalized.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    normalized = re.sub(r"[^a-z0-9\s-]", "", normalized)
    normalized = re.sub(r"[\s_-]+", "-", normalized)
    return normalized.strip("-")


def seed_lms_catalog_db(db: Session) -> int:
    created = 0
    for title in TOPICS:
        slug = _slugify(title)
        exists = db.query(LMSPost).filter(LMSPost.slug == slug).first()
        if exists:
            continue
        db.add(
            LMSPost(
                title=title,
                slug=slug,
                category="Capacitación SGSI",
                version="1.0",
                status="published",
                html_content="",
                porcentaje_aprobacion=80.0,
                max_intentos=3,
                created_by_id=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        created += 1
    if created:
        db.commit()
    return created


def seed_lms_catalog() -> None:
    db = SessionLocal()
    try:
        seed_lms_catalog_db(db)
    finally:
        db.close()
