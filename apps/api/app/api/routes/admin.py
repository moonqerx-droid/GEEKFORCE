from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.routes.auth import get_email_sender
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import User
from app.schemas.auth import _normalize_email, _normalize_name
from app.services.admin import AdminService, SelfDeactivation, UserExists, UserNotFound
from app.services.email import EmailPayload, EmailSender, MemoryEmailSender

router = APIRouter(prefix="/api/admin", tags=["admin"])

AdminDependency = Annotated[User, Depends(require_admin)]


def get_admin_service(db: Annotated[Session, Depends(get_db)]) -> AdminService:
    return AdminService(db, get_settings().app_public_url)


ServiceDependency = Annotated[AdminService, Depends(get_admin_service)]


class InviteCreate(BaseModel):
    email: str
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)

    _email = field_validator("email")(_normalize_email)
    _names = field_validator("first_name", "last_name")(_normalize_name)


class InviteRead(BaseModel):
    invite_url: str
    expires_at: datetime
    email_sent: bool


class TeamMember(BaseModel):
    id: str
    email: str
    name: str
    role: Literal["operator", "admin"]
    status: Literal["active", "disabled", "invited"]
    created_at: datetime
    last_login_at: datetime | None


class TeamMemberUpdate(BaseModel):
    is_active: bool


def _send_invite(sender: EmailSender, email: str, first_name: str, url: str) -> bool:
    if isinstance(sender, MemoryEmailSender):
        return False
    try:
        sender.send(EmailPayload(
            recipient=email,
            subject="Приглашение в команду поддержки HelpFlow",
            text=f"Здравствуйте, {first_name}!\n\nВас пригласили в команду поддержки HelpFlow. "
                 f"Задайте пароль по ссылке (действует 7 дней):\n{url}",
            html=f"<p>Здравствуйте, {first_name}!</p><p>Вас пригласили в команду поддержки HelpFlow.</p>"
                 f"<p><a href=\"{url}\">Принять приглашение</a> — ссылка действует 7 дней.</p>",
            action_url=url,
        ))
        return True
    except Exception:
        return False


@router.get("/operators", response_model=list[TeamMember])
def list_team(service: ServiceDependency, _admin: AdminDependency):
    return service.team()


@router.post("/operators/invite", response_model=InviteRead, status_code=status.HTTP_201_CREATED)
def invite_operator(
    payload: InviteCreate,
    service: ServiceDependency,
    admin: AdminDependency,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
):
    try:
        invite, url = service.invite(
            email=payload.email, first_name=payload.first_name, last_name=payload.last_name, invited_by=admin,
        )
    except UserExists as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким email уже есть") from exc
    return InviteRead(invite_url=url, expires_at=invite.expires_at,
                      email_sent=_send_invite(sender, payload.email, payload.first_name, url))


@router.patch("/operators/{user_id}", response_model=TeamMember)
def update_member(user_id: str, payload: TeamMemberUpdate, service: ServiceDependency, admin: AdminDependency):
    try:
        return service.set_active(user_id, payload.is_active, admin)
    except UserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник поддержки не найден") from exc
    except SelfDeactivation as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя отключить самого себя") from exc


@router.get("/metrics")
def metrics(service: ServiceDependency, _admin: AdminDependency, days: Annotated[int, Query(ge=1, le=90)] = 7):
    return service.metrics(days)
