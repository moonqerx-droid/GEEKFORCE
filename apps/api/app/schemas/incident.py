from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class IncidentUpdateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    request_key: str
    created_at: datetime


class IncidentMember(BaseModel):
    """One request of the incident: whose it is and what the employee wrote."""

    id: str
    status: str
    owner_name: str | None = None
    owner_department: str | None = None
    original_request: str = ""
    created_at: datetime


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: IncidentStatus
    service: str
    title: str
    signature_tokens: list[str]
    similarity_threshold: float
    revision: int
    created_at: datetime
    updated_at: datetime
    conversation_count: int
    conversation_ids: list[str]
    evidence_tokens: list[str]
    latest_update: IncidentUpdateRead | None = None
    # Human-readable service name as the requests call it ("VPN", not the normalized "vpn").
    service_label: str | None = None
    affected_employees: int = 0
    first_seen_at: datetime | None = None
    members: list[IncidentMember] = Field(default_factory=list)


class IncidentBroadcastCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    request_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_revision: int = Field(ge=1)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        if not (trimmed := value.strip()):
            raise ValueError("message must not be blank")
        return trimmed


class IncidentBroadcastResult(BaseModel):
    incident: IncidentRead
    delivered_to: list[str]


class IncidentConfirm(BaseModel):
    expected_revision: int = Field(ge=1)


class IncidentResolve(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    expected_revision: int = Field(ge=1)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        if not (trimmed := value.strip()):
            raise ValueError("message must not be blank")
        return trimmed
