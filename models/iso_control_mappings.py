"""Modelo de mapeo ISO 27001 <-> documentación SGSI."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from utils.database import Base


class ISOControlMapping(Base):
    __tablename__ = "iso_control_mappings"
    __table_args__ = (
        UniqueConstraint("control_iso", "document_id", name="uq_iso_control_document"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    control_iso: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Pendiente")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
