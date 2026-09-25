from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationStatus(StrEnum):
    NEW = "NEW"
    ANALYZING = "ANALYZING"
    CLARIFYING = "CLARIFYING"
    TROUBLESHOOTING = "TROUBLESHOOTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class Urgency(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class StepOutcome(StrEnum):
    HELPED = "helped"
    NOT_HELPED = "not_helped"
    CANNOT_PERFORM = "cannot_perform"


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class StepResultCreate(BaseModel):
    outcome: StepOutcome


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    instruction: str
    outcome: StepOutcome
    position: int
    created_at: datetime


class CurrentStep(BaseModel):
    code: str
    instruction: str


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime
    summary: str | None
    service: str | None
    symptoms: list[str]
    urgency: Urgency
    urgency_reason: str | None
    known_facts: dict[str, str]
    missing_facts: list[str]
    confidence: float | None
    playbook_id: str | None
    messages: list[MessageRead]
    completed_steps: list[StepRead] = Field(validation_alias="steps")
    current_step: CurrentStep | None = None
    escalation_summary: str | None
    incident_id: str | None

    @classmethod
    def from_model(cls, model) -> "ConversationRead":
        data = cls.model_validate(model, from_attributes=True)
        if model.current_step_code and model.current_step_instruction:
            data.current_step = CurrentStep(
                code=model.current_step_code,
                instruction=model.current_step_instruction,
            )
        return data


class OperatorTicket(ConversationRead):
    original_request: str

