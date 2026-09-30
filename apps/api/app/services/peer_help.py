"""«Помощь коллег»: тема обращения в ленте, один помощник, чат с модерацией и счётчик помощи.
Обращение при этом остаётся в очереди специалиста — коллеги помогают параллельно."""

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.security import utc_now
from app.models.auth import User
from app.models.conversation import Conversation, Message
from app.models.peer_help import DirectMessage, PeerHelpMessage, PeerHelpRequest
from app.services.moderation import validate_peer_message

# Обращения по безопасности коллегам не показываем — только специалисту.
SECURITY_TERMS = ("фишинг", "взлом", "чужая учет", "чужая учёт", "скомпромет", "утечк", "вирус", "шифровальщик")
FAILED_OUTCOMES = {"not_helped", "cannot_perform"}
ACTIVE = ("OPEN", "HELPING")


class PeerHelpError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _with_people(statement):
    return statement.options(
        selectinload(PeerHelpRequest.author), selectinload(PeerHelpRequest.helper),
        selectinload(PeerHelpRequest.messages).selectinload(PeerHelpMessage.sender),
    )


class PeerHelpService:
    def __init__(self, session: Session):
        self.session = session

    def get(self, request_id: str) -> PeerHelpRequest | None:
        return self.session.scalar(_with_people(select(PeerHelpRequest).where(PeerHelpRequest.id == request_id)))

    def for_conversation(self, conversation_id: str) -> PeerHelpRequest | None:
        return self.session.scalar(_with_people(
            select(PeerHelpRequest).where(PeerHelpRequest.conversation_id == conversation_id)
        ))

    def feed(self) -> list[PeerHelpRequest]:
        return list(self.session.scalars(_with_people(
            # Обращение закрыли иначе (специалист, ассистент, конец сбоя) — просьба больше не нужна.
            select(PeerHelpRequest).join(Conversation, Conversation.id == PeerHelpRequest.conversation_id)
            .where(PeerHelpRequest.status.in_(ACTIVE), Conversation.status != "RESOLVED")
            .order_by(PeerHelpRequest.created_at.desc())
        )))

    def publish(self, conversation_id: str, author: User) -> PeerHelpRequest:
        conversation = self.session.get(Conversation, conversation_id)
        if conversation is None or conversation.owner_id != author.id:
            raise PeerHelpError(404, "Обращение не найдено.")
        existing = self.for_conversation(conversation_id)
        if existing is not None:
            return existing
        first_request = next((m.content for m in conversation.messages if m.role == "user"), "")
        text = " ".join([
            conversation.summary or "", conversation.service or "",
            " ".join(map(str, (conversation.known_facts or {}).values())), first_request,
        ]).casefold()
        if conversation.playbook_id == "security_incident" or any(term in text for term in SECURITY_TERMS):
            raise PeerHelpError(403, "Обращения по информационной безопасности коллегам не показываем — ими занимается специалист.")
        tried_and_failed = any(step.outcome in FAILED_OUTCOMES for step in conversation.steps)
        waiting = conversation.status in {"ESCALATED", "IN_PROGRESS"}
        if not (waiting or (conversation.status == "TROUBLESHOOTING" and tried_and_failed)):
            raise PeerHelpError(409, "Спросить коллег можно, когда шаги не помогли или обращение ждёт специалиста.")
        item = PeerHelpRequest(
            conversation_id=conversation.id, author_id=author.id,
            title=(conversation.summary or "Нужна помощь с обращением")[:300],
            area=(conversation.service or "Другое")[:120],
        )
        self.session.add(item)
        try:
            self.session.commit()
        except IntegrityError:  # тот же сотрудник нажал дважды
            self.session.rollback()
        return self.for_conversation(conversation_id)

    def claim(self, request_id: str, helper: User) -> PeerHelpRequest:
        item = self._require(request_id)
        if item.author_id == helper.id:
            raise PeerHelpError(409, "Свою просьбу взять нельзя.")
        if item.status == "HELPING" and item.helper_id == helper.id:
            return item
        if item.status != "OPEN":
            raise PeerHelpError(409, "Другой коллега уже помогает.")
        # Условие на OPEN в самом UPDATE: из двух одновременных «Помогу» пройдёт один.
        changed = self.session.execute(
            PeerHelpRequest.__table__.update()
            .where(PeerHelpRequest.id == request_id, PeerHelpRequest.status == "OPEN")
            .values(status="HELPING", helper_id=helper.id, updated_at=utc_now())
        )
        if changed.rowcount != 1:
            self.session.rollback()
            raise PeerHelpError(409, "Другой коллега уже помогает.")
        self.session.commit()
        self.session.expire_all()
        return self.get(request_id)

    def require_participant(self, request_id: str, user: User) -> PeerHelpRequest:
        item = self._require(request_id)
        if user.id not in {item.author_id, item.helper_id}:
            raise PeerHelpError(403, "Чат видят только автор и помощник.")
        return item

    def add_message(self, request_id: str, user: User, content: str) -> PeerHelpRequest:
        item = self.require_participant(request_id, user)
        if item.status != "HELPING":
            raise PeerHelpError(409, "Чат открыт, пока коллега помогает.")
        cleaned = validate_peer_message(content)
        self.session.add(PeerHelpMessage(peer_help_request_id=item.id, sender_id=user.id, content=cleaned))
        self.session.commit()
        self.session.expire_all()
        return self.get(item.id)

    def resolve(self, request_id: str, author: User) -> PeerHelpRequest:
        item = self._require(request_id)
        if item.author_id != author.id:
            raise PeerHelpError(403, "Подтвердить решение может только автор обращения.")
        if item.status == "RESOLVED":
            return item
        if item.status != "HELPING" or item.helper is None:
            raise PeerHelpError(409, "Сначала коллега должен откликнуться.")
        conversation = self.session.get(Conversation, item.conversation_id)
        item.status = "RESOLVED"
        item.helper.helped_count = (item.helper.helped_count or 0) + 1
        if conversation.status != "RESOLVED":
            conversation.status = "RESOLVED"
            conversation.resolved_at = utc_now()
            conversation.resolved_by = "colleague"
            conversation.current_step_code = None
            conversation.current_step_instruction = None
            conversation.messages.append(Message(
                role="assistant",
                content=f"Совет коллеги — {item.helper.full_name} — помог. Обращение закрыто, спасибо за взаимопомощь!",
            ))
        self.session.commit()
        self.session.expire_all()
        return self.get(item.id)

    # Коллеги и личные сообщения

    def colleagues(self, me: User) -> list[User]:
        return list(self.session.scalars(
            select(User).where(User.role == "employee", User.is_active.is_(True), User.id != me.id)
            .order_by(User.first_name, User.last_name)
        ))

    def colleague(self, user_id: str) -> User:
        user = self.session.get(User, user_id)
        if user is None or user.role != "employee" or not user.is_active:
            raise PeerHelpError(404, "Коллега не найден.")
        return user

    def direct_history(self, me: User, other_id: str) -> list[DirectMessage]:
        self.colleague(other_id)
        return list(self.session.scalars(
            select(DirectMessage).where(or_(
                (DirectMessage.sender_id == me.id) & (DirectMessage.recipient_id == other_id),
                (DirectMessage.sender_id == other_id) & (DirectMessage.recipient_id == me.id),
            )).order_by(DirectMessage.id)
            .options(selectinload(DirectMessage.sender), selectinload(DirectMessage.recipient))
        ))

    def send_direct(self, me: User, other_id: str, content: str) -> DirectMessage:
        if other_id == me.id:
            raise PeerHelpError(409, "Себе написать нельзя.")
        recipient = self.colleague(other_id)
        message = DirectMessage(sender_id=me.id, recipient_id=recipient.id, content=validate_peer_message(content))
        self.session.add(message)
        self.session.commit()
        return self.session.scalar(select(DirectMessage).where(DirectMessage.id == message.id).options(
            selectinload(DirectMessage.sender), selectinload(DirectMessage.recipient)))

    def _require(self, request_id: str) -> PeerHelpRequest:
        item = self.get(request_id)
        if item is None:
            raise PeerHelpError(404, "Просьба не найдена.")
        return item
