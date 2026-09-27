from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.incidents import IncidentRepository
from app.schemas.incident import (
    IncidentBroadcastCreate,
    IncidentBroadcastResult,
    IncidentConfirm,
    IncidentRead,
    IncidentResolve,
)
from app.services.incidents import IncidentConflict, IncidentNotFound, IncidentService
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


def get_incident_service(db: Annotated[Session, Depends(get_db)]) -> IncidentService:
    settings = get_settings()
    return IncidentService(
        IncidentRepository(db),
        threshold=settings.incident_similarity_threshold,
        min_cluster_size=settings.incident_min_cluster_size,
        window_minutes=settings.incident_window_minutes,
    )


IncidentServiceDependency = Annotated[IncidentService, Depends(get_incident_service)]


@router.get("/incidents", response_model=list[IncidentRead])
def list_incidents(
    service: IncidentServiceDependency,
    _user: OperatorDependency,
    include_resolved: bool = False,
) -> list[IncidentRead]:
    return service.list_incidents(include_resolved=include_resolved)


def run_incident(action):
    try:
        return action()
    except IncidentNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found") from error
    except IncidentConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/incidents/{incident_id}/broadcast", response_model=IncidentBroadcastResult)
def broadcast_incident(
    incident_id: str,
    payload: IncidentBroadcastCreate,
    service: IncidentServiceDependency,
    user: OperatorDependency,
) -> IncidentBroadcastResult:
    return run_incident(lambda: service.broadcast(
        incident_id, payload.message, payload.request_key, payload.expected_revision, author=user,
    ))


@router.post("/incidents/{incident_id}/confirm", response_model=IncidentRead)
def confirm_incident(
    incident_id: str,
    payload: IncidentConfirm,
    service: IncidentServiceDependency,
    _user: OperatorDependency,
) -> IncidentRead:
    return run_incident(lambda: service.confirm(incident_id, payload.expected_revision))


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentRead)
def resolve_incident(
    incident_id: str,
    payload: IncidentResolve,
    service: IncidentServiceDependency,
    user: OperatorDependency,
) -> IncidentRead:
    return run_incident(lambda: service.resolve(
        incident_id, payload.message, payload.expected_revision, author=user,
    ))
