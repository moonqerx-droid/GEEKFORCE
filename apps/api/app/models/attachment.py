from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.db.base import Base
from app.models.conversation import utc_now


class Attachment(Base):
    """A file a person put into a conversation: a screenshot, a photo of a screen, a log.

    Bytes live in the database: files are small (≤10 MB), they share the conversation's
    lifetime and backups, and no extra volume is needed. `data` is deferred so lists of
    messages never load file contents.
    """

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True)
    uploader_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    message: Mapped["Message | None"] = relationship(back_populates="attachments")

    @property
    def kind(self) -> str:
        return "image" if self.content_type.startswith("image/") else "file"

    @property
    def url(self) -> str:
        return f"/api/attachments/{self.id}"


from app.models.conversation import Message  # noqa: E402
