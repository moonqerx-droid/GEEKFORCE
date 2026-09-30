"""A step learned from a closed request: what the specialist did, rewritten by the support lead so
the next employee with the same problem can try it before waiting for a specialist."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import utc_now
from app.db.base import Base


class LearnedStep(Base):
    __tablename__ = "learned_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    playbook_id: Mapped[str] = mapped_column(String(120), index=True)
    # Written for the employee: «Перезапустите VPN-клиент и выберите профиль "Офис-2"».
    instruction: Mapped[str] = mapped_column(Text)
    # The closed request it was learned from; kept even if that request is deleted later.
    source_conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
