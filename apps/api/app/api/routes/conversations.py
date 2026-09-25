from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import ConversationRead, MessageCreate, StepResultCreate
from app.services.ai import MockAIService
from app.services.dialogue import ConversationNotFound, DialogueConflict, DialogueService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def get_dialogue_service(db: Annotated[Session, Depends(get_db)]) -> DialogueService:
    return DialogueService(ConversationRepository(db), MockAIService())


DialogueDependency = Annotated[DialogueService, Depends(get_dialogue_service)]


def serialize(conversation) -> ConversationRead:
    return ConversationRead.from_model(conversation)


def not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(service: DialogueDependency) -> ConversationRead:
    return serialize(service.create_conversation())


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: str, service: DialogueDependency) -> ConversationRead:
    try:
        return serialize(service.get_conversation(conversation_id))
    except ConversationNotFound as exc:
        raise not_found() from exc


@router.post("/{conversation_id}/messages", response_model=ConversationRead)
def send_message(
    conversation_id: str,
    payload: MessageCreate,
    service: DialogueDependency,
) -> ConversationRead:
    try:
        return serialize(service.handle_message(conversation_id, payload.content))
    except ConversationNotFound as exc:
        raise not_found() from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{conversation_id}/step-result", response_model=ConversationRead)
def record_step_result(
    conversation_id: str,
    payload: StepResultCreate,
    service: DialogueDependency,
) -> ConversationRead:
    try:
        return serialize(service.record_step_result(conversation_id, payload.outcome.value))
    except ConversationNotFound as exc:
        raise not_found() from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{conversation_id}/escalate", response_model=ConversationRead)
def escalate(conversation_id: str, service: DialogueDependency) -> ConversationRead:
    try:
        return serialize(service.escalate(conversation_id))
    except ConversationNotFound as exc:
        raise not_found() from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

