"""Esquemas para la gestión de documentos y políticas"""
from __future__ import annotations
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Constantes de Validación de Archivos ---
# Centralizamos esto aquí para usarlo en los routers
ALLOWED_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", # .docx
    "application/msword", # .doc
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", # .xlsx
    "application/vnd.ms-excel" # .xls
]
MAX_FILE_SIZE_MB = 21
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# --- Base Schemas ---

class DocumentBase(BaseModel):
    """Datos básicos compartidos para creación y lectura"""
    title: str = Field(min_length=3, max_length=150, description="Título del documento")
    description: str | None = Field(default=None, description="Resumen del contenido")
    version: str = Field(default="1.0", max_length=10, description="Versión del documento (ej: 1.0)")
    code: str | None = Field(default=None, max_length=20, description="Código interno (ej: POL-001)")
    doc_type: Literal["policy", "record"] = Field(
        default="record", 
        description="'policy' requiere lectura, 'record' es evidencia general"
    )

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str | None) -> str | None:
        """Fuerza el código a mayúsculas si existe"""
        if v:
            return v.upper()
        return v


class DocumentCreate(DocumentBase):
    """
    Schema para recibir los metadatos en la creación.
    NOTA: El archivo binario (UploadFile) se gestiona en el router vía Form/File,
    no directamente dentro de este modelo Pydantic.
    """
    pass


class DocumentUpdate(BaseModel):
    """Schema para actualizaciones parciales"""
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = None
    version: str | None = Field(default=None, max_length=10)
    code: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str | None) -> str | None:
        if v:
            return v.upper()
        return v


# --- Response Schemas ---

class DocumentResponse(DocumentBase):
    """Respuesta estándar de un documento (para administradores/listados generales)"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    uploaded_by_id: int
    created_at: datetime
    is_active: bool

    @property
    def download_url(self) -> str:
        """Helper para construir la URL en el frontend si es necesario"""
        return f"/api/v1/media/documents/{self.filename}"


class DocumentWithReadStatus(DocumentResponse):
    """
    Respuesta enriquecida para el usuario final (Colaborador).
    Incluye si el usuario actual ya leyó el documento.
    """
    is_read_by_user: bool = False
    read_at: datetime | None = None


# --- Read Confirmation Schemas ---

class DocumentReadResponse(BaseModel):
    """Respuesta al confirmar la lectura"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    document_id: int
    download_at: datetime | None = None
    read_at: datetime | None = None


class DocumentComplianceStats(BaseModel):
    """Estadísticas de cumplimiento para reportes"""
    id: int
    title: str
    code: str | None
    version: str
    total_users: int
    read_count: int
    compliance_percentage: float


class PolicyAuditSummary(BaseModel):
    generated_at: datetime
    report_version: str
    responsible: str
    global_compliance_percentage: float
    collaborators_confirmed_percentage: float
    pending_reads: int
    overdue_reads: int
    total_active_users: int
    total_active_policies: int
    total_assignments: int
    completed_assignments: int


class PolicyAuditByPolicy(BaseModel):
    policy_id: int
    code: str
    title: str
    total_collaborators: int
    confirmations: int
    compliance_percentage: float
    overdue_reads: int
    semaphore: str


class PolicyAuditByDepartment(BaseModel):
    department_id: int
    department_name: str
    total_collaborators: int
    total_assignments: int
    confirmations: int
    compliance_percentage: float
    pending_reads: int
    overdue_reads: int
    semaphore: str


class PolicyAuditTrendPoint(BaseModel):
    period_label: str
    compliance_percentage: float
    confirmed_assignments: int
    total_assignments: int


class PolicyAuditTraceabilityRow(BaseModel):
    user_id: int
    username: str
    department_name: str
    policy_code: str
    policy_title: str
    status: str
    created_at: datetime
    download_at: datetime | None
    read_at: datetime | None
    overdue: bool
