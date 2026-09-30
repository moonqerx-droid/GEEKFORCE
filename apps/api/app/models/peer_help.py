from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import utc_now
from app.db.base import Base
from app.models.auth import User


class PeerHelpRequest(Base):
    """Тема обращения в ленте «Помощь коллег». Сам диалог остаётся у специалиста в очереди."""

    __tablename__ = "peer_help_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, index=True
    )
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    helper_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    area: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    author: Mapped[User] = relationship(foreign_keys=[author_id])
    helper: Mapped[User | None] = relationship(foreign_keys=[helper_id])
    messages: Mapped[list[PeerHelpMessage]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="PeerHelpMessage.id"
    )


class PeerHelpMessage(Base):
    __tablename__ = "peer_help_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    peer_help_request_id: Mapped[str] = mapped_column(
        ForeignKey("peer_help_requests.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    request: Mapped[PeerHelpRequest] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship()


class DirectMessage(Base):
    """Личная переписка двух сотрудников (раздел «Коллеги»)."""

    __tablename__ = "direct_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    sender: Mapped[User] = relationship(foreign_keys=[sender_id])
    recipient: Mapped[User] = relationship(foreign_keys=[recipient_id])
