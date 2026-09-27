from datetime import datetime
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Department = Literal["it", "sales", "marketing", "finance", "hr", "operations", "other"]
UserRole = Literal["employee", "operator", "admin"]
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def _normalize_name(value: str) -> str:
    if any(char.isspace() and char != " " for char in value):
        raise ValueError("name contains unsupported whitespace")
    normalized = " ".join(value.strip().split())
    if not 2 <= len(normalized) <= 50:
        raise ValueError("name must contain 2 to 50 characters")
    if any(not (unicodedata.category(char).startswith("L") or char in " -'") for char in normalized):
        raise ValueError("name contains unsupported characters")
    if not any(unicodedata.category(char).startswith("L") for char in normalized):
        raise ValueError("name must contain letters")
    return normalized


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 254 or not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("invalid email")
    return normalized


class RegistrationBase(BaseModel):
    first_name: str
    last_name: str
    email: str
    department: Department
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_name(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if any(char.isspace() for char in value):
            raise ValueError("password must not contain whitespace")
        if not any(char.islower() for char in value):
            raise ValueError("password must contain a lowercase letter")
        if not any(char.isupper() for char in value):
            raise ValueError("password must contain an uppercase letter")
        if not any(char.isdigit() for char in value):
            raise ValueError("password must contain a digit")
        return value

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("passwords do not match")
        return self


class EmployeeRegister(RegistrationBase):
    accepted_terms: bool

    @field_validator("accepted_terms")
    @classmethod
    def terms_are_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("terms must be accepted")
        return value


class OperatorRegister(RegistrationBase):
    invite_token: str = Field(min_length=20, max_length=512)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False

    _email = field_validator("email")(_normalize_email)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class VerifyEmailRequest(BaseModel):
    email: str
    code: str = Field(pattern=r"^\d{6}$")

    _email = field_validator("email")(_normalize_email)


class ForgotPasswordRequest(BaseModel):
    email: str

    _email = field_validator("email")(_normalize_email)


class ResetPasswordRequest(TokenRequest):
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str

    _password = field_validator("password")(RegistrationBase.validate_password.__func__)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("passwords do not match")
        return self


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    email: str
    department: Department
    role: UserRole
    email_verified_at: datetime | None
    must_change_password: bool = False
    revision: int = 1


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str

    _password = field_validator("password")(RegistrationBase.validate_password.__func__)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("passwords do not match")
        return self


class ApiErrorBody(BaseModel):
    code: str
    message: str
    fields: dict[str, str] | None = None
