from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import Department, UserRole, _normalize_email, _normalize_name


def normalize_full_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized or len(normalized) > 101:
        raise ValueError("full name must contain 2 to 101 characters")
    for part in normalized.split(" ", 1):
        _normalize_name(part)
    return normalized


class AdminUserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=101)
    email: str
    department: Department

    _name = field_validator("full_name")(normalize_full_name)
    _email = field_validator("email")(_normalize_email)


class AdminUserUpdate(BaseModel):
    revision: int = Field(ge=1)
    full_name: str | None = Field(default=None, min_length=2, max_length=101)
    email: str | None = None
    department: Department | None = None
    role: UserRole | None = None
    is_active: bool | None = None

    _name = field_validator("full_name")(lambda value: normalize_full_name(value) if value is not None else value)
    _email = field_validator("email")(lambda value: _normalize_email(value) if value is not None else value)


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    department: Department
    role: UserRole
    is_active: bool
    status: Literal["active", "disabled"]
    must_change_password: bool
    revision: int
    created_at: datetime
    last_login_at: datetime | None


class TemporaryCredentialRead(BaseModel):
    user: AdminUserRead
    temporary_password: str
