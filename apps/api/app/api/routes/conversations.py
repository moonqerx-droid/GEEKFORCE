from typing import Annotated
from functools import lru_cache

from helpflow_ai import TriageEngine

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import ConversationRead, MessageCreate, StepResultCreate
from app.services.ai import MockAIService
from app.services.dialogue import ConversationNotFound, DialogueConflict, DialogueService
from app.services.triage import TriageDialogueService
from app.api.dependencies.auth import require_employee
from app.models.auth import User

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@lru_cache
def get_triage_engine() -> TriageEngine:
    return TriageEngine.from_env()


def get_dialogue_service(request: Request, db: Annotated[Session, Depends(get_db)]) -> DialogueService:
    repository = ConversationRepository(db)
    conversation_id = request.path_params.get("conversation_id")
    conversation = repository.get(conversation_id) if conversation_id else None
    if conversation is not None and conversation.workflow_version == "legacy":
        return DialogueService(repository, MockAIService())
    return TriageDialogueService(repository, get_triage_engine())


DialogueDependency = Annotated[DialogueService, Depends(get_dialogue_service)]


def serialize(conversation) -> ConversationRead:
    return ConversationRead.from_model(conversation)


def not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    service: DialogueDependency,
    user: Annotated[User, Depends(require_employee)],
) -> ConversationRead:
    conversation = service.create_conversation()
    conversation.owner_id = user.id
    service.repository.session.commit()
    return serialize(conversation)


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_employee)],
) -> list[ConversationRead]:
    return [serialize(item) for item in ConversationRepository(db).list_by_owner(user.id)]


def ensure_owned(db: Session, conversation_id: str, user: User) -> None:
    if ConversationRepository(db).get(conversation_id, owner_id=user.id) is None:
        raise not_found()


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: str,
    service: DialogueDependency,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_employee)],
) -> ConversationRead:
    ensure_owned(db, conversation_id, user)
    try:
        return serialize(service.get_conversation(conversation_id))
    except ConversationNotFound as exc:
        raise not_found() from exc


@router.post("/{conversation_id}/messages", response_model=ConversationRead)
def send_message(
    conversation_id: str,
    payload: MessageCreate,
    service: DialogueDependency,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_employee)],
) -> ConversationRead:
    ensure_owned(db, conversation_id, user)
    try:
        return serialize(service.handle_message(conversation_id, payload.content,
                                               expected_revision=payload.expected_revision))
    except ConversationNotFound as exc:
        raise not_found() from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{conversation_id}/step-result", response_model=ConversationRead)
def record_step_result(
    conversation_id: str,
    payload: StepResultCreate,
    service: DialogueDependency,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_employee)],
) -> ConversationRead:
    ensure_owned(db, conversation_id, user)
    try:
        return serialize(service.record_step_result(conversation_id, payload.outcome.value,
                                                    expected_revision=payload.expected_revision,
                                                    step_code=payload.step_code))
    except ConversationNotFound as exc:
        raise not_found() from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{conversation_id}/escalate", response_model=ConversationRead)
def escalate(
    conversation_id: str,
    service: DialogueDependency,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_employee)],
) -> ConversationRead:
    ensure_owned(db, conversation_id, user)
    try:
        return serialize(service.escalate(conversation_id))
    except ConversationNotFound as exc:
        raise not_found() from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
