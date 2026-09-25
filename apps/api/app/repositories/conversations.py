from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation, Message, TroubleshootingStep


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self) -> Conversation:
        conversation = Conversation()
        self.session.add(conversation)
        self.session.commit()
        return self.get(conversation.id)

    def get(self, conversation_id: str) -> Conversation | None:
        statement = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(Conversation.messages),
                selectinload(Conversation.steps),
            )
        )
        return self.session.scalar(statement)

    def save(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        self.session.commit()
        return self.get(conversation.id)

    def add_message(self, conversation_id: str, *, role: str, content: str) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        self.session.add(message)
        self.session.commit()
        self.session.refresh(message)
        return message

    def add_step_result(
        self,
        conversation_id: str,
        *,
        code: str,
        instruction: str,
        outcome: str,
    ) -> TroubleshootingStep:
        existing_count = len(self.get(conversation_id).steps)
        step = TroubleshootingStep(
            conversation_id=conversation_id,
            code=code,
            instruction=instruction,
            outcome=outcome,
            position=existing_count,
        )
        self.session.add(step)
        self.session.commit()
        self.session.refresh(step)
        return step

    def list_escalated(self) -> list[Conversation]:
        urgency_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        statement = (
            select(Conversation)
            .where(Conversation.status == "ESCALATED")
            .options(
                selectinload(Conversation.messages),
                selectinload(Conversation.steps),
            )
        )
        items = list(self.session.scalars(statement).all())
        return sorted(items, key=lambda item: (urgency_order.get(item.urgency, 9), item.created_at))
