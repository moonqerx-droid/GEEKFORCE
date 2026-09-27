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
