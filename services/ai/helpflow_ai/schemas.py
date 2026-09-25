"""Typed contracts of the AI triage service.

Field names follow section 7 of PROJECT_PLAN.md so the backend can map them
onto the Conversation model without renaming.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StepOutcome(str, Enum):
    HELPED = "helped"
    NOT_HELPED = "not_helped"
    CANNOT_DO = "cannot_do"


class DecisionAction(str, Enum):
    ASK = "ask"
    STEP = "step"
    VERIFY = "verify"
    ESCALATE = "escalate"


class QuestionKind(str, Enum):
    TEXT = "text"
    YES_NO = "yes_no"
    CHOICE = "choice"


class Question(BaseModel):
    """A clarifying question bound to the fact it fills."""

    model_config = ConfigDict(extra="forbid")

    fact: str
    text: str
    kind: QuestionKind = QuestionKind.TEXT
    # For CHOICE: normalized value -> keywords that select it.
    options: dict[str, list[str]] = Field(default_factory=dict)
    # For YES_NO: store the opposite answer (question is phrased positively).
    invert: bool = False


class Step(BaseModel):
    """One troubleshooting instruction shown to the user."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    instruction: str
    # Step is offered only when every listed fact has one of the given values.
    when: dict[str, list[str]] = Field(default_factory=dict)
    # Step is skipped when any listed fact has one of the given values.
    unless: dict[str, list[str]] = Field(default_factory=dict)
    requires_admin: bool = False


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    service: str
    keywords: list[str]
    # symptom label -> keywords that reveal it
    symptoms_hints: dict[str, list[str]] = Field(default_factory=dict)
    questions: list[Question] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    verify_question: str = "Проверьте, пожалуйста: проблема решена и всё работает как нужно?"
    # Shown to the user together with the escalation message.
    safety_notice: str | None = None
    escalate_immediately: bool = False
    escalation_team: str = "Service Desk L2"
    default_urgency: Urgency = Urgency.MEDIUM


class Analysis(BaseModel):
    """Structured understanding of the user's request."""

    summary: str
    service: str
    symptoms: list[str] = Field(default_factory=list)
    urgency: Urgency = Urgency.MEDIUM
    urgency_reason: str = ""
    known_facts: dict[str, str] = Field(default_factory=dict)
    missing_facts: list[str] = Field(default_factory=list)
    next_question: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    recommended_playbook: str
    should_escalate: bool = False
    source: str = "rules"

    @field_validator("summary", "service", "recommended_playbook")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class StepRecord(BaseModel):
    """A step that was already shown and its result."""

    step_id: str
    outcome: StepOutcome


class ConversationContext(BaseModel):
    """What the AI needs to know about the dialogue so far."""

    original_request: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    known_facts: dict[str, str] = Field(default_factory=dict)
    asked_facts: list[str] = Field(default_factory=list)
    completed_steps: list[StepRecord] = Field(default_factory=list)
    playbook_id: str | None = None
    urgency: Urgency | None = None
    # Set by the backend when the user said "no" at the verification stage.
    verification_failed: bool = False


class Decision(BaseModel):
    """What the dialogue should do next."""

    action: DecisionAction
    # Ready-to-show assistant text for the chat.
    message: str
    question: Question | None = None
    step: Step | None = None
    reason: str = ""
    escalation_team: str | None = None


class EscalationCard(BaseModel):
    """Everything a specialist needs without re-reading the chat."""

    original_request: str
    summary: str
    service: str
    urgency: Urgency
    urgency_reason: str
    known_facts: dict[str, str]
    questions_and_answers: list[dict[str, str]]
    performed_steps: list[dict[str, str]]
    escalation_reason: str
    recommended_team: str
    ai_summary: str
    source: str = "rules"
