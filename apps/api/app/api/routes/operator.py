from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import ConversationRead, OperatorTicket

router = APIRouter(prefix="/api/operator", tags=["operator"])


@router.get("/tickets", response_model=list[OperatorTicket])
def list_tickets(db: Annotated[Session, Depends(get_db)]) -> list[OperatorTicket]:
    conversations = ConversationRepository(db).list_escalated()
    tickets = []
    for conversation in conversations:
        serialized = ConversationRead.from_model(conversation)
        original_request = next(
            (message.content for message in conversation.messages if message.role == "user"),
            "",
        )
        tickets.append(
            OperatorTicket(
                **serialized.model_dump(),
                original_request=original_request,
            )
        )
    return tickets

