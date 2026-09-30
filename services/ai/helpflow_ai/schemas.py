"""Typed contracts of the AI triage service.

Field names follow the team's original API contract so the backend can map them
onto the Conversation model without renaming.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

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


class AnswerKind(str, Enum):
    PLAYBOOK = "playbook"
    DOCUMENT = "document"
    GENERAL = "general"
    HANDOFF = "handoff"


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
    # For CHOICE: how each option reads as a one-tap answer ("В браузере").
    option_labels: dict[str, str] = Field(default_factory=dict)
    # For CHOICE: append «Не знаю» to the one-tap answers.
    offer_dont_know: bool = True
    # For YES_NO: store the opposite answer (question is phrased positively).
    invert: bool = False
    # Asked only when every listed fact has one of the given values.
    when_facts: dict[str, list[str]] = Field(default_factory=dict)
    # Asked only when one of these symptoms was described (empty = always).
    when_symptoms: list[str] = Field(default_factory=list)
    # Skipped when one of these symptoms was described.
    unless_symptoms: list[str] = Field(default_factory=list)
    # Asked only while no symptom of the playbook is known: "what exactly is wrong?"
    only_without_symptoms: bool = False


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
    # Same as when/unless, but over symptoms described by the user.
    when_symptoms: list[str] = Field(default_factory=list)
    unless_symptoms: list[str] = Field(default_factory=list)
    requires_admin: bool = False
    # Quick way around the problem (phone, web version). Offered first when urgent;
    # "helped" does not close the problem, the diagnosis continues.
    workaround: bool = False


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    service: str
    keywords: list[str]
    # How people actually describe this problem; used for meaning-based matching and
    # as typo vocabulary. Plain phrases, not keywords.
    examples: list[str] = Field(default_factory=list)
    # symptom label -> keywords that reveal it
    symptoms_hints: dict[str, list[str]] = Field(default_factory=dict)
    questions: list[Question] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    verify_question: str = "Проверьте, пожалуйста: проблема решена и всё работает как нужно?"
    # Shown to the user together with the escalation message.
    safety_notice: str | None = None
    escalate_immediately: bool = False
    # Hand off once questions are answered, if one of these symptoms was described.
    escalate_on_symptoms: list[str] = Field(default_factory=list)
    # Shown to the user before the standard hand-off text; {fact} placeholders allowed.
    escalation_note: str | None = None
    escalation_team: str = "Service Desk L2"
    default_urgency: Urgency = Urgency.MEDIUM


class ErrorCode(BaseModel):
    """One error code from knowledge-base/error-codes: what it means and what to do."""

    model_config = ConfigDict(extra="forbid")

    code: str
    # Other spellings or neighbouring codes with the same meaning and steps.
    also: list[str] = Field(default_factory=list)
    playbook: str
    title: str
    meaning: str
    steps: list[Step] = Field(default_factory=list)
    # After the code's own steps failed: straight to a specialist, skip the generic steps.
    escalate_after_steps: bool = False
    # A generic code (HTTP 403, 502) explains what happened but does not pick the scenario.
    decides_scenario: bool = True

    @property
    def codes(self) -> list[str]:
        """Canonical spellings: the main code first."""
        from .rules import canonical_code

        return list(dict.fromkeys(canonical_code(code) for code in (self.code, *self.also)))

    @property
    def step_prefix(self) -> str:
        return f"code.{self.codes[0]}."


class KnowledgeChunk(BaseModel):
    """One approved, attributable fragment available to grounded replies."""

    model_config = ConfigDict(extra="forbid")

    id: str
    service: str
    title: str
    text: str
    keywords: list[str] = Field(default_factory=list)
    safety_notice: str | None = None
    escalation_team: str


class KnowledgeMatch(BaseModel):
    """A retrieval result with a normalized deterministic score."""

    chunk: KnowledgeChunk
    score: float = Field(ge=0.0, le=1.0)


class Citation(BaseModel):
    """A source fragment safe for presentation in the chat UI."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=1200)


class RetrievedFragment(BaseModel):
    """Minimal contract accepted from the API knowledge repository."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^document:", min_length=10, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=20_000)


class EvidenceClaim(BaseModel):
    """One visible assertion and the exact source fragment supporting it."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=600)
    source_id: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=1200)


class EvidenceAnswer(BaseModel):
    """Structured model output accepted only after evidence validation."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=1200)
    claims: list[EvidenceClaim] = Field(default_factory=list, max_length=8)
    # Kept for compatibility with older providers. Validated source ids are
    # ultimately derived from claims by EvidenceValidator.
    source_ids: list[str] = Field(default_factory=list, max_length=4)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_operator: bool
    reason: str = Field(min_length=1, max_length=300)


class GroundedAnswer(EvidenceAnswer):
    """Backward-compatible name for the grounded response contract."""


class DetectedIssue(BaseModel):
    """One of several problems found in a single request."""

    playbook_id: str
    title: str
    service: str
    symptoms: list[str] = Field(default_factory=list)
    # The part of the user's text this problem was found in, as written.
    evidence: str = ""
    # For the escalation card: pending = not handled yet, in_progress = being solved,
    # resolved = a step helped or the user said it went away.
    # handed_off = needs a specialist; the other problems were worked through meanwhile.
    status: Literal["pending", "in_progress", "resolved", "handed_off"] = "pending"


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
    # Other problems from the same message, in the order they will be handled.
    additional_issues: list[DetectedIssue] = Field(default_factory=list)

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
    message_source: Literal["rules", "llm"] = "rules"
    source_ids: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    llm_latency_ms: int | None = Field(default=None, ge=0)
    answer_kind: AnswerKind | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=8)
    # Playbook of the problem this decision is about (differs from the dialogue's
    # playbook_id once the next of several problems is being handled).
    playbook_id: str | None = None
    # Facts the caller keeps with the conversation («this problem waits for a specialist»).
    remember: dict[str, str] = Field(default_factory=dict)


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
    current_result: str
    escalation_reason: str
    recommended_team: str
    ai_summary: str
    source: str = "rules"
    # Every problem from the request with its status; the first one is the main one.
    issues: list[DetectedIssue] = Field(default_factory=list)


class SelfHelpStep(BaseModel):
    id: str
    title: str
    instruction: str


class SelfHelpCode(BaseModel):
    code: str
    title: str
    meaning: str
    steps: list[SelfHelpStep] = Field(default_factory=list)


class SelfHelpGuide(BaseModel):
    playbook_id: str
    title: str
    steps: list[SelfHelpStep] = Field(default_factory=list)


class SelfHelpDocument(BaseModel):
    source_id: str
    title: str
    text: str


class SelfHelp(BaseModel):
    """«Решить самому»: what an employee can do alone for a code or a problem, no request needed."""

    query: str
    code: SelfHelpCode | None = None
    guide: SelfHelpGuide | None = None
    document: SelfHelpDocument | None = None
    # Security, a mass outage, someone else's password: no self-help, straight to a person.
    specialist_only: bool = False
    notice: str | None = None
