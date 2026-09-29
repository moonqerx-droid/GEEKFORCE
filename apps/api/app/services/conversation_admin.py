"""The support lead's view of every conversation: find one by its words and delete it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.attachment import Attachment
from app.models.audit import AdminAuditEvent
from app.models.auth import User
from app.models.conversation import Conversation, Message, TroubleshootingStep


class ConversationNotFound(LookupError):
    pass


@dataclass(frozen=True)
class ConversationRow:
    id: str
    status: str
    created_at: datetime
    owner_name: str | None
    owner_email: str | None
    first_message: str
    match: str | None
    messages: int


def _snippet(text: str, needle: str | None = None, width: int = 140) -> str:
    flat = " ".join(text.split())
    if needle:
        at = flat.casefold().find(needle.casefold())
        if at > width // 2:
            flat = "…" + flat[at - width // 3:]
    return flat if len(flat) <= width else flat[:width - 1] + "…"


class ConversationAdminService:
    def __init__(self, session: Session):
        self.session = session

    def list(self, query: str = "", limit: int = 100) -> list[ConversationRow]:
        """Newest first; with a query, only conversations where some message contains it."""
        needle = query.strip()
        statement = select(Conversation).order_by(Conversation.created_at.desc()).limit(limit)
        if needle:
            matching = select(Message.conversation_id).where(Message.content.ilike(f"%{needle}%"))
            statement = statement.where(Conversation.id.in_(matching))
        conversations = self.session.scalars(statement).all()
        owners = {user.id: user for user in self.session.scalars(
            select(User).where(User.id.in_({c.owner_id for c in conversations if c.owner_id}))
        )}
        rows = []
        for conversation in conversations:
            texts = [m.content for m in sorted(conversation.messages, key=lambda m: m.id)]
            first = next((m.content for m in sorted(conversation.messages, key=lambda m: m.id)
                          if m.role == "user"), "")
            hit = next((t for t in texts if needle and needle.casefold() in t.casefold()), None)
            owner = owners.get(conversation.owner_id)
            rows.append(ConversationRow(
                id=conversation.id,
                status=conversation.status,
                created_at=conversation.created_at,
                owner_name=f"{owner.first_name} {owner.last_name}".strip() if owner else None,
                owner_email=owner.email if owner else None,
                first_message=_snippet(first),
                match=_snippet(hit, needle) if hit else None,
                messages=len(texts),
            ))
        return rows

    def delete(self, conversation_id: str, actor: User) -> None:
        """Remove the conversation with its messages, steps and attachments; keep an audit record."""
        conversation = self.session.get(Conversation, conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        owner_id, status, messages = conversation.owner_id, conversation.status, len(conversation.messages)
        self.session.expunge(conversation)
        for model in (Attachment, TroubleshootingStep, Message):
            self.session.execute(delete(model).where(model.conversation_id == conversation_id))
        self.session.execute(delete(Conversation).where(Conversation.id == conversation_id))
        # The audit keeps who deleted what, never the deleted words.
        self.session.add(AdminAuditEvent(
            actor_id=actor.id, target_user_id=owner_id, action="conversation_deleted",
            changes={"conversation_id": conversation_id, "status": status, "messages": messages},
        ))
        self.session.commit()
