from datetime import datetime, timezone
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    content: str = Field(default="", max_length=4000)
    expected_revision: int | None = Field(default=None, ge=1)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def text_or_files(self):
        # A screenshot alone is a perfectly good message; an empty one is not.
        if not self.content and not self.attachment_ids:
            raise ValueError("message must contain text or a file")
        return self


class StepResultCreate(BaseModel):
    outcome: StepOutcome
    expected_revision: int | None = Field(default=None, ge=1)
    step_code: str | None = Field(default=None, min_length=1, max_length=120)


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    size: int
    kind: str
    url: str
    created_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime
    author_name: str | None = None
    attachments: list[AttachmentRead] = Field(default_factory=list)
    answer_kind: Literal["playbook", "document", "general", "handoff"] | None = None
    citations: list["CitationRead"] = Field(default_factory=list)

    @field_validator("citations", mode="before")
    @classmethod
    def nullable_citations_are_an_empty_list(cls, value):
        return value or []


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    instruction: str
    outcome: StepOutcome
    position: int
    created_at: datetime
    # The step's own title («Очистите очередь печати»), not the whole message it came with.
    title: str | None = None


class CurrentStep(BaseModel):
    code: str
    instruction: str


class CitationRead(BaseModel):
    source_id: str
    title: str
    quote: str


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
    answer_kind: Literal["playbook", "document", "general", "handoff"] | None = None
    citations: list[CitationRead] = Field(default_factory=list)
    # One-tap answers to the question the assistant just asked (empty for free text).
    quick_replies: list[str] = Field(default_factory=list)
    # The employee's other open request about the same problem, if this one is a repeat.
    similar_open: "SimilarOpen | None" = None
    assignee_id: str | None = None
    assignee_name: str | None = None
    escalated_at: datetime | None = None
    assigned_at: datetime | None = None
    first_operator_reply_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    rating: int | None = None
    rating_comment: str | None = None
    # While a specialist has not answered yet: the promised first-reply time (SLA).
    reply_target_minutes: int | None = None
    reply_due_at: datetime | None = None

    @classmethod
    def from_model(cls, model, quick_replies: list[str] | None = None, similar=None) -> "ConversationRead":
        data = cls.model_validate(model, from_attributes=True)
        data.quick_replies = list(quick_replies or [])
        if similar is not None:
            data.similar_open = SimilarOpen(id=similar.id, summary=similar.summary)
        if model.current_step_code and model.current_step_instruction:
            data.current_step = CurrentStep(
                code=model.current_step_code,
                instruction=model.current_step_instruction,
            )
        if data.answer_kind is None:
            data.answer_kind = _infer_answer_kind(model)
        titles = _step_titles()
        for step in data.completed_steps:
            step.title = titles.get(step.code)
        if model.status in ("ESCALATED", "IN_PROGRESS"):
            from app.services.sla import sla_for

            promise = sla_for(model, datetime.now(timezone.utc))
            if promise is not None and promise.replied_at is None:
                data.reply_target_minutes = promise.target_minutes
                data.reply_due_at = promise.due_at
        return data


class SimilarOpen(BaseModel):
    id: str
    summary: str | None = None


ConversationRead.model_rebuild()


class OperatorTicket(ConversationRead):
    original_request: str
    owner_name: str | None = None
    owner_department: str | None = None


def _infer_answer_kind(model):
    if model.status in {"ESCALATED", "IN_PROGRESS"}:
        return "handoff"
    codes = [model.current_step_code, *[step.code for step in getattr(model, "steps", [])]]
    if any(code and code.startswith("general.") for code in codes):
        return "general"
    if any(source_id.startswith("document:") for source_id in model.rag_source_ids):
        return "document"
    if model.playbook_id and any(message.role == "assistant" for message in model.messages):
        return "playbook"
    return None


def _strip_required(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


class RatingCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class OperatorMessageCreate(BaseModel):
    content: str = Field(default="", max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def text_or_files(self):
        if not self.content and not self.attachment_ids:
            raise ValueError("message must contain text or a file")
        return self


class ResolveCreate(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)

    _summary = field_validator("summary")(_strip_required)


@lru_cache(maxsize=1)
def _step_titles() -> dict[str, str]:
    """Step id → title from the knowledge base (error-code steps included)."""
    from helpflow_ai.knowledge import KnowledgeBase

    try:
        return {step.id: step.title for playbook in KnowledgeBase.load().playbooks for step in playbook.steps}
    except Exception:  # noqa: BLE001 — titles are a nicety; the step text is still there
        return {}
