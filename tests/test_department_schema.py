from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from schemas.department import DepartmentBase, DepartmentResponse


def test_department_base_validates_name_length():
    department = DepartmentBase(departamento="Infraestructura")

    assert department.departamento == "Infraestructura"


def test_department_base_rejects_empty_name():
    with pytest.raises(ValidationError):
        DepartmentBase(departamento="")


def test_department_response_can_be_built_from_attributes():
    source = SimpleNamespace(
        id=7,
        departamento="Talento Humano",
        created_at=datetime(2026, 3, 28, tzinfo=UTC),
    )

    response = DepartmentResponse.model_validate(source)

    assert response.id == 7
    assert response.departamento == "Talento Humano"
