from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.conversation import ConversationRead, OperatorMessageCreate, OperatorTicket, ResolveCreate
from app.api.dependencies.auth import require_operator
from app.models.auth import User
from app.services.dialogue import ConversationNotFound, DialogueConflict
from app.services.operator import OperatorService

router = APIRouter(prefix="/api/operator", tags=["operator"])

OperatorDependency = Annotated[User, Depends(require_operator)]


def get_operator_service(db: Annotated[Session, Depends(get_db)]) -> OperatorService:
    return OperatorService(db)


ServiceDependency = Annotated[OperatorService, Depends(get_operator_service)]


def to_ticket(conversation) -> OperatorTicket:
    serialized = ConversationRead.from_model(conversation)
    original_request = next(
        (message.content for message in conversation.messages if message.role == "user"), "",
    )
    return OperatorTicket(
        **serialized.model_dump(),
        original_request=original_request,
        owner_name=conversation.owner_name,
        owner_department=conversation.owner_department,
    )


def run(action):
    try:
        return to_ticket(action())
    except ConversationNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/tickets", response_model=list[OperatorTicket])
def list_tickets(
    service: ServiceDependency,
    user: OperatorDependency,
    scope: Literal["queue", "mine", "resolved"] = "queue",
) -> list[OperatorTicket]:
    return [to_ticket(item) for item in service.list(scope, user)]


@router.get("/tickets/{conversation_id}", response_model=OperatorTicket)
def get_ticket(conversation_id: str, service: ServiceDependency, _user: OperatorDependency) -> OperatorTicket:
    return run(lambda: service.get(conversation_id))


@router.post("/tickets/{conversation_id}/assign", response_model=OperatorTicket)
def assign_ticket(conversation_id: str, service: ServiceDependency, user: OperatorDependency) -> OperatorTicket:
    return run(lambda: service.assign(conversation_id, user))


@router.post("/tickets/{conversation_id}/messages", response_model=OperatorTicket)
def reply_to_ticket(
    conversation_id: str,
    payload: OperatorMessageCreate,
    service: ServiceDependency,
    user: OperatorDependency,
) -> OperatorTicket:
    return run(lambda: service.reply(conversation_id, user, payload.content))


@router.post("/tickets/{conversation_id}/resolve", response_model=OperatorTicket)
def resolve_ticket(
    conversation_id: str,
    payload: ResolveCreate,
    service: ServiceDependency,
    user: OperatorDependency,
) -> OperatorTicket:
    return run(lambda: service.resolve(conversation_id, user, payload.summary))
