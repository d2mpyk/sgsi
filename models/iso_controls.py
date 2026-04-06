"""Catálogo base de controles ISO 27001:2022 (Anexo A)."""
from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from utils.database import Base


class ISOControl(Base):
    __tablename__ = "iso_controls"
    __table_args__ = (
        UniqueConstraint("control", name="uq_iso_controls_control"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tema: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    control: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
