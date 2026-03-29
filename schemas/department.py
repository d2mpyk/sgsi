"""Relacionado a los Schemas del catálogo de departamentos."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBase(BaseModel):
    departamento: str = Field(min_length=1, max_length=100)


class DepartmentResponse(DepartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
