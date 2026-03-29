"""Modelos para la gestión documental del SGSI"""
from __future__ import annotations
from datetime import UTC, datetime
from sqlalchemy import ForeignKey, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from utils.database import Base

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    # Metadatos del Documento
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Control de Versiones (Vital para SGSI)
    version: Mapped[str] = mapped_column(String(10), default="1.0", nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True) # Ej: POL-001
    
    # Clasificación
    # 'policy': Requiere lectura obligatoria. 'record': Evidencia/Documento general.
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False, default="record") 
    
    # Archivo físico
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False) # pdf, docx, etc.

    # Auditoría de carga
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC)
    )
    
    # Estado (Para retención documental, no borrar, solo obsolescencia)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    reads: Mapped[list["DocumentRead"]] = relationship("DocumentRead", back_populates="document")


class DocumentRead(Base):
    """Tabla pivote para registrar descarga y confirmación de lectura por política"""
    __tablename__ = "document_reads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    
    # Fecha de descarga del documento, si existe evidencia de acceso
    download_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # La evidencia legal del momento de la confirmación de lectura
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Relaciones para facilitar consultas
    document: Mapped["Document"] = relationship("Document", back_populates="reads")
    # user: Mapped["User"]... (Se definiría si se agrega back_populates en User)
