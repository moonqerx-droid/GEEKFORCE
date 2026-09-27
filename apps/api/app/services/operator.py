"""Specialist side of a conversation: taking it, answering in the same thread, closing it."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.models.auth import User
from app.models.conversation import Conversation, Message, utc_now
from app.services.dialogue import ConversationNotFound, DialogueConflict

HANDOFF_STATUSES = {"ESCALATED", "IN_PROGRESS", "RESOLVED"}
URGENCY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}


class OperatorService:
    def __init__(self, session: Session):
        self.session = session

    def _query(self):
        return select(Conversation).options(
            selectinload(Conversation.messages).selectinload(Message.author),
            selectinload(Conversation.steps),
            selectinload(Conversation.owner),
            selectinload(Conversation.assignee),
        ).execution_options(populate_existing=True)

    def list(self, scope: str, user: User) -> list[Conversation]:
        statement = self._query()
        if scope == "mine":
            statement = statement.where(
                Conversation.assignee_id == user.id, Conversation.status == "IN_PROGRESS",
            )
        elif scope == "resolved":
            statement = statement.where(
                Conversation.status == "RESOLVED", Conversation.escalated_at.is_not(None),
            ).order_by(Conversation.resolved_at.desc()).limit(50)
            return list(self.session.scalars(statement).all())
        else:
            statement = statement.where(Conversation.status.in_(("ESCALATED", "IN_PROGRESS")))
        items = list(self.session.scalars(statement).all())
        return sorted(items, key=lambda item: (
            URGENCY_ORDER.get(item.urgency, 9), item.escalated_at or item.created_at,
        ))

    def get(self, conversation_id: str) -> Conversation:
        conversation = self.session.scalar(self._query().where(Conversation.id == conversation_id))
        handed_off = conversation is not None and (
            conversation.status in {"ESCALATED", "IN_PROGRESS"}
            or (conversation.status in HANDOFF_STATUSES and conversation.escalated_at is not None)
        )
        if not handed_off:
            raise ConversationNotFound(conversation_id)
        return conversation

    def _load_for_action(self, conversation_id: str) -> Conversation:
        conversation = self.session.scalar(self._query().where(Conversation.id == conversation_id))
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        if conversation.status not in {"ESCALATED", "IN_PROGRESS"}:
            raise DialogueConflict("conversation is not waiting for a specialist")
        return conversation

    @staticmethod
    def _take(conversation: Conversation, user: User) -> None:
        if conversation.assignee_id and conversation.assignee_id != user.id:
            raise DialogueConflict("conversation is already assigned to another specialist")
        if conversation.assignee_id is None:
            conversation.assignee_id = user.id
            conversation.assigned_at = utc_now()
        conversation.status = "IN_PROGRESS"

    def _commit(self, conversation: Conversation) -> Conversation:
        conversation.updated_at = utc_now()
        try:
            self.session.commit()
        except StaleDataError as exc:
            self.session.rollback()
            raise DialogueConflict("conversation changed; reload it before retrying") from exc
        return self.session.scalar(self._query().where(Conversation.id == conversation.id))

    def assign(self, conversation_id: str, user: User) -> Conversation:
        conversation = self._load_for_action(conversation_id)
        self._take(conversation, user)
        return self._commit(conversation)

    def reply(self, conversation_id: str, user: User, content: str) -> Conversation:
        conversation = self._load_for_action(conversation_id)
        self._take(conversation, user)
        conversation.messages.append(Message(role="operator", content=content, author_id=user.id))
        conversation.first_operator_reply_at = conversation.first_operator_reply_at or utc_now()
        return self._commit(conversation)

    def resolve(self, conversation_id: str, user: User, summary: str) -> Conversation:
        conversation = self._load_for_action(conversation_id)
        self._take(conversation, user)
        now = utc_now()
        conversation.messages.append(Message(
            role="operator", author_id=user.id,
            content=f"Обращение закрыто. Итог: {summary}",
        ))
        conversation.status = "RESOLVED"
        conversation.resolved_at = now
        conversation.resolved_by = "operator"
        return self._commit(conversation)
