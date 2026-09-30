from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_employee
from app.db.session import get_db
from app.models.auth import User
from app.schemas.peer_help import ColleagueRead, DirectMessageRead, PeerHelpMessageCreate, PeerHelpRead
from app.services.moderation import ModerationViolation
from app.services.peer_help import PeerHelpError, PeerHelpService

router = APIRouter(tags=["peer-help"])

EmployeeDependency = Annotated[User, Depends(require_employee)]


def get_service(db: Annotated[Session, Depends(get_db)]) -> PeerHelpService:
    return PeerHelpService(db)


ServiceDependency = Annotated[PeerHelpService, Depends(get_service)]


def run(action):
    try:
        return action()
    except PeerHelpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ModerationViolation as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get("/api/peer-help", response_model=list[PeerHelpRead])
def feed(service: ServiceDependency, _user: EmployeeDependency):
    # В ленте только тема и область — переписка видна лишь автору и помощнику.
    return [PeerHelpRead.from_model(item, include_messages=False) for item in service.feed()]


@router.get("/api/conversations/{conversation_id}/peer-help", response_model=PeerHelpRead | None)
def for_conversation(conversation_id: str, service: ServiceDependency, user: EmployeeDependency):
    item = service.for_conversation(conversation_id)
    if item is None or item.author_id != user.id:
        return None
    return PeerHelpRead.from_model(item)


@router.post("/api/conversations/{conversation_id}/peer-help", response_model=PeerHelpRead, status_code=201)
def publish(conversation_id: str, service: ServiceDependency, user: EmployeeDependency):
    return PeerHelpRead.from_model(run(lambda: service.publish(conversation_id, user)))


@router.get("/api/peer-help/{request_id}", response_model=PeerHelpRead)
def detail(request_id: str, service: ServiceDependency, user: EmployeeDependency):
    return PeerHelpRead.from_model(run(lambda: service.require_participant(request_id, user)))


@router.post("/api/peer-help/{request_id}/claim", response_model=PeerHelpRead)
def claim(request_id: str, service: ServiceDependency, user: EmployeeDependency):
    return PeerHelpRead.from_model(run(lambda: service.claim(request_id, user)))


@router.post("/api/peer-help/{request_id}/messages", response_model=PeerHelpRead, status_code=201)
def message(request_id: str, payload: PeerHelpMessageCreate, service: ServiceDependency, user: EmployeeDependency):
    return PeerHelpRead.from_model(run(lambda: service.add_message(request_id, user, payload.content)))


@router.post("/api/peer-help/{request_id}/resolve", response_model=PeerHelpRead)
def resolve(request_id: str, service: ServiceDependency, user: EmployeeDependency):
    return PeerHelpRead.from_model(run(lambda: service.resolve(request_id, user)))


@router.get("/api/colleagues", response_model=list[ColleagueRead])
def colleagues(service: ServiceDependency, user: EmployeeDependency):
    return [ColleagueRead.from_user(item) for item in service.colleagues(user)]


@router.get("/api/colleagues/{other_id}/messages", response_model=list[DirectMessageRead])
def direct_history(other_id: str, service: ServiceDependency, user: EmployeeDependency):
    return [DirectMessageRead.from_model(m) for m in run(lambda: service.direct_history(user, other_id))]


@router.post("/api/colleagues/{other_id}/messages", response_model=DirectMessageRead, status_code=201)
def send_direct(other_id: str, payload: PeerHelpMessageCreate, service: ServiceDependency, user: EmployeeDependency):
    return DirectMessageRead.from_model(run(lambda: service.send_direct(user, other_id, payload.content)))
