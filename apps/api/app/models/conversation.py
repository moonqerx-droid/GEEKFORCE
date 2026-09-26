from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(32), default="NEW", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symptoms: Mapped[list[str]] = mapped_column(JSON, default=list)
    urgency: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    urgency_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_facts: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    missing_facts: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    playbook_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    current_step_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    current_step_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    incident_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workflow_version: Mapped[str] = mapped_column(String(20), default="legacy", server_default="legacy")
    asked_facts: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    verification_failed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    escalation_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    __mapper_args__ = {"version_id_col": revision}

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    steps: Mapped[list[TroubleshootingStep]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="TroubleshootingStep.position",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class TroubleshootingStep(Base):
    __tablename__ = "troubleshooting_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(120))
    instruction: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="steps")
