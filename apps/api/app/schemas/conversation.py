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
    IN_PROGRESS = "IN_PROGRESS"


class Urgency(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    OPERATOR = "operator"


class StepOutcome(StrEnum):
    HELPED = "helped"
    NOT_HELPED = "not_helped"
    CANNOT_PERFORM = "cannot_perform"


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class StepResultCreate(BaseModel):
    outcome: StepOutcome
    expected_revision: int | None = Field(default=None, ge=1)
    step_code: str | None = Field(default=None, min_length=1, max_length=120)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime
    author_name: str | None = None


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
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    revision: int
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
    escalation_card: dict | None = None
    rag_source_ids: list[str] = Field(default_factory=list)
    ai_fallback_reason: str | None = None
    ai_latency_ms: int | None = None
    assignee_id: str | None = None
    assignee_name: str | None = None
    escalated_at: datetime | None = None
    assigned_at: datetime | None = None
    first_operator_reply_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    rating: int | None = None
    rating_comment: str | None = None

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
    owner_name: str | None = None
    owner_department: str | None = None


def _strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


class RatingCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class OperatorMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    _content = field_validator("content")(_strip_required)


class ResolveCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)

    _summary = field_validator("summary")(_strip_required)
