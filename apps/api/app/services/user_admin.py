from __future__ import annotations

import secrets
import string

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.security import hash_password, utc_now
from app.models.audit import AdminAuditEvent
from app.models.auth import AuthSession, User
from app.schemas.admin_users import AdminUserCreate, AdminUserUpdate


class UserAdminError(Exception):
    pass


class ManagedUserExists(UserAdminError):
    pass


class ManagedUserNotFound(UserAdminError):
    pass


class StaleUserRevision(UserAdminError):
    pass


class LastActiveAdmin(UserAdminError):
    pass


class SelfDisable(UserAdminError):
    pass


def split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(maxsplit=1)
    return parts[0], parts[1] if len(parts) == 2 else ""


def generate_temporary_password(length: int = 18) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    required = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase), secrets.choice(string.digits)]
    chars = required + [secrets.choice(alphabet) for _ in range(max(length, 14) - len(required))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "department": user.department,
        "role": user.role,
        "is_active": user.is_active,
        "status": "active" if user.is_active else "disabled",
        "must_change_password": user.must_change_password,
        "revision": user.revision,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


class UserAdminService:
    def __init__(self, session: Session):
        self.session = session

    def list_users(self) -> list[dict]:
        users = self.session.scalars(select(User).order_by(User.created_at, User.email)).all()
        return [serialize_user(user) for user in users]

    def create_operator(self, payload: AdminUserCreate, actor: User) -> tuple[dict, str]:
        if self.session.scalar(select(User).where(User.email == payload.email)) is not None:
            raise ManagedUserExists(payload.email)
        first_name, last_name = split_full_name(payload.full_name)
        temporary_password = generate_temporary_password()
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=payload.email,
            department=payload.department,
            password_hash=hash_password(temporary_password),
            role="operator",
            email_verified_at=utc_now(),
            must_change_password=True,
        )
        self.session.add(user)
        self.session.flush()
        self._audit(actor, user, "user.created", {
            "email": user.email, "name": user.full_name, "department": user.department, "role": user.role,
        })
        self.session.commit()
        self.session.refresh(user)
        return serialize_user(user), temporary_password

    def update_user(self, user_id: str, payload: AdminUserUpdate, actor: User) -> dict:
        user = self.session.get(User, user_id)
        if user is None:
            raise ManagedUserNotFound(user_id)
        if user.revision != payload.revision:
            raise StaleUserRevision(user_id)
        changes: dict[str, dict[str, object]] = {}
        values = payload.model_dump(exclude_unset=True, exclude={"revision"})
        if values.get("is_active") is False and user.id == actor.id:
            raise SelfDisable(user_id)
        if user.role == "admin" and (values.get("role", user.role) != "admin" or values.get("is_active") is False):
            if self._active_admin_count() <= 1:
                raise LastActiveAdmin(user_id)
        if "email" in values:
            duplicate = self.session.scalar(select(User).where(User.email == values["email"], User.id != user.id))
            if duplicate is not None:
                raise ManagedUserExists(str(values["email"]))
        if "full_name" in values:
            first_name, last_name = split_full_name(str(values.pop("full_name")))
            for field, value in (("first_name", first_name), ("last_name", last_name)):
                if getattr(user, field) != value:
                    changes[field] = {"from": getattr(user, field), "to": value}
                    setattr(user, field, value)
        sensitive = False
        for field, value in values.items():
            if getattr(user, field) == value:
                continue
            changes[field] = {"from": getattr(user, field), "to": value}
            setattr(user, field, value)
            sensitive = sensitive or field in {"email", "role", "is_active"}
        if not changes:
            return serialize_user(user)
        user.revision += 1
        if sensitive:
            self._revoke_sessions(user.id)
        self._audit(actor, user, "user.updated", changes)
        self.session.commit()
        self.session.refresh(user)
        return serialize_user(user)

    def reset_password(self, user_id: str, actor: User) -> tuple[dict, str]:
        user = self.session.get(User, user_id)
        if user is None:
            raise ManagedUserNotFound(user_id)
        temporary_password = generate_temporary_password()
        user.password_hash = hash_password(temporary_password)
        user.must_change_password = True
        user.revision += 1
        self._revoke_sessions(user.id)
        self._audit(actor, user, "user.password_reset", {"must_change_password": {"from": False, "to": True}})
        self.session.commit()
        self.session.refresh(user)
        return serialize_user(user), temporary_password

    def _active_admin_count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(User).where(
            User.role == "admin", User.is_active.is_(True),
        )) or 0)

    def _revoke_sessions(self, user_id: str) -> None:
        self.session.execute(update(AuthSession).where(
            AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None),
        ).values(revoked_at=utc_now()))

    def _audit(self, actor: User, target: User, action: str, changes: dict) -> None:
        self.session.add(AdminAuditEvent(
            actor_id=actor.id, target_user_id=target.id, action=action, changes=changes,
        ))
