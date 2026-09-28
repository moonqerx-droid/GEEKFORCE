from typing import Annotated
from functools import lru_cache

from helpflow_ai import TriageEngine

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import AttachmentRead, ConversationRead, MessageCreate, RatingCreate, StepResultCreate
from app.services.attachments import MAX_BYTES, AttachmentRejected, AttachmentService
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


def serialize(conversation, service: DialogueService | None = None) -> ConversationRead:
    replies = service.quick_replies(conversation) if service is not None else None
    similar = service.similar_open(conversation) if service is not None else None
    return ConversationRead.from_model(conversation, quick_replies=replies, similar=similar)


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
        return serialize(service.get_conversation(conversation_id), service)
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
        attachments = AttachmentService(db).pending_for(conversation_id, payload.attachment_ids)
    except AttachmentRejected as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    try:
        return serialize(service.handle_message(conversation_id, payload.content,
                                               expected_revision=payload.expected_revision,
                                               attachments=attachments), service)
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
                                                    step_code=payload.step_code), service)
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
        return serialize(service.escalate(conversation_id), service)
    except ConversationNotFound as exc:
        raise not_found() from exc
    except DialogueConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{conversation_id}/rating", response_model=ConversationRead)
def rate_conversation(
    conversation_id: str,
    payload: RatingCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_employee)],
) -> ConversationRead:
    conversation = ConversationRepository(db).get(conversation_id, owner_id=user.id)
    if conversation is None:
        raise not_found()
    if conversation.status != "RESOLVED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="only resolved conversations can be rated")
    conversation.rating = payload.rating
    conversation.rating_comment = (payload.comment or "").strip() or None
    db.commit()
    return serialize(ConversationRepository(db).get(conversation_id))


async def read_limited(file: UploadFile) -> bytes:
    """Read at most one byte past the limit so an oversized upload is refused without buffering it all."""
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    return data


@router.post("/{conversation_id}/attachments", response_model=AttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    conversation_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_employee)],
    file: Annotated[UploadFile, File()],
) -> AttachmentRead:
    conversation = ConversationRepository(db).get(conversation_id, owner_id=user.id)
    if conversation is None:
        raise not_found()
    if conversation.status == "RESOLVED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Обращение уже закрыто")
    try:
        attachment = AttachmentService(db).store(conversation, user, file.filename, await read_limited(file))
    except AttachmentRejected as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    return AttachmentRead.model_validate(attachment)
