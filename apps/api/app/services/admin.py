"""Support lead tools: team management, the bootstrap admin and support metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, hash_token, new_token, utc_now
from app.models.auth import OperatorInvite, User
from app.models.conversation import Conversation

INVITE_LIFETIME = timedelta(days=7)
URGENCY_LEVELS = ("low", "normal", "high", "critical")


class AdminError(Exception):
    pass


class UserExists(AdminError):
    pass


class UserNotFound(AdminError):
    pass


class SelfDeactivation(AdminError):
    pass


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=utc_now().tzinfo)


def _minutes(start, end) -> float | None:
    if start is None or end is None:
        return None
    return (_aware(end) - _aware(start)).total_seconds() / 60


def bootstrap_admin(session: Session, *, email: str, password: str,
                    first_name: str = "Администратор", last_name: str = "HelpFlow") -> User | None:
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        return existing
    user = User(
        first_name=first_name, last_name=last_name, email=email, department="it",
        password_hash=hash_password(password), role="admin", email_verified_at=utc_now(),
    )
    session.add(user)
    session.commit()
    return user


class AdminService:
    def __init__(self, session: Session, app_public_url: str):
        self.session = session
        self.app_public_url = app_public_url.rstrip("/")

    # --- team -----------------------------------------------------------------

    def invite(self, *, email: str, first_name: str, last_name: str, invited_by: User):
        email = email.strip().lower()
        if self.session.scalar(select(User).where(User.email == email)) is not None:
            raise UserExists(email)
        raw_token = new_token()
        invite = OperatorInvite(
            email=email, first_name=first_name, last_name=last_name, invited_by_id=invited_by.id,
            token_hash=hash_token(raw_token), expires_at=utc_now() + INVITE_LIFETIME,
        )
        self.session.add(invite)
        self.session.commit()
        url = (f"{self.app_public_url}/operator/register?token={quote(raw_token)}"
               f"&email={quote(email)}&first_name={quote(first_name)}&last_name={quote(last_name)}")
        return invite, url

    def team(self) -> list[dict]:
        users = self.session.scalars(
            select(User).where(User.role.in_(("operator", "admin"))).order_by(User.created_at)
        ).all()
        members = [{
            "id": user.id, "email": user.email, "name": user.full_name, "role": user.role,
            "status": "active" if user.is_active else "disabled",
            "created_at": user.created_at, "last_login_at": user.last_login_at,
        } for user in users]
        known = {user.email for user in users}
        now = utc_now()
        invites = self.session.scalars(
            select(OperatorInvite).where(OperatorInvite.used_at.is_(None)).order_by(OperatorInvite.created_at)
        ).all()
        for invite in invites:
            if invite.email in known or _aware(invite.expires_at) <= now:
                continue
            known.add(invite.email)
            name = " ".join(part for part in (invite.first_name, invite.last_name) if part)
            members.append({
                "id": invite.id, "email": invite.email, "name": name or invite.email, "role": "operator",
                "status": "invited", "created_at": invite.created_at, "last_login_at": None,
            })
        return members

    def set_active(self, user_id: str, is_active: bool, actor: User) -> dict:
        user = self.session.get(User, user_id)
        if user is None or user.role not in {"operator", "admin"}:
            raise UserNotFound(user_id)
        if user.id == actor.id and not is_active:
            raise SelfDeactivation(user_id)
        user.is_active = is_active
        self.session.commit()
        return next(item for item in self.team() if item["id"] == user_id)

    # --- metrics --------------------------------------------------------------

    def metrics(self, days: int) -> dict:
        now = utc_now()
        start_day = (now - timedelta(days=days - 1)).date()
        since = now - timedelta(days=days)
        # Empty drafts (opened and never written to) stay NEW and are not requests.
        conversations = [
            item for item in self.session.scalars(select(Conversation).where(Conversation.status != "NEW")).all()
            if _aware(item.created_at) >= since
        ]
        by_assistant = [c for c in conversations if c.resolved_by == "assistant"]
        by_operator = [c for c in conversations if c.resolved_by == "operator"]
        resolved = by_assistant + by_operator
        open_items = [c for c in conversations if c.status in {"ESCALATED", "IN_PROGRESS"}]
        ratings = [c.rating for c in conversations if c.rating]
        resolution = [m for c in resolved if (m := _minutes(c.created_at, c.resolved_at)) is not None]
        first_reply = [m for c in conversations
                       if (m := _minutes(c.escalated_at, c.first_operator_reply_at)) is not None]

        daily = {start_day + timedelta(days=offset): {"assistant": 0, "operator": 0, "open": 0, "total": 0}
                 for offset in range(days)}
        for item in conversations:
            bucket = daily.get(_aware(item.created_at).date())
            if bucket is None:
                continue
            bucket["total"] += 1
            key = item.resolved_by if item.resolved_by in {"assistant", "operator"} else (
                "open" if item.status in {"ESCALATED", "IN_PROGRESS"} else None)
            if key:
                bucket[key] += 1

        problems: dict[str, dict] = defaultdict(lambda: {"count": 0, "escalated": 0, "service": None})
        for item in conversations:
            if not item.playbook_id:
                continue
            entry = problems[item.playbook_id]
            entry["count"] += 1
            entry["service"] = entry["service"] or item.service
            if item.escalated_at is not None or item.status in {"ESCALATED", "IN_PROGRESS"}:
                entry["escalated"] += 1
        top_problems = sorted((
            {"playbook_id": key, "service": value["service"], "count": value["count"],
             "escalation_rate": value["escalated"] / value["count"]}
            for key, value in problems.items()
        ), key=lambda item: -item["count"])[:8]

        urgency = Counter(item.urgency for item in conversations)
        operators = []
        staff = self.session.scalars(select(User).where(User.role.in_(("operator", "admin")))).all()
        for user in staff:
            mine = [c for c in conversations if c.assignee_id == user.id]
            if not mine and user.role == "admin":
                continue
            done = [c for c in mine if c.status == "RESOLVED"]
            times = [m for c in done if (m := _minutes(c.assigned_at or c.escalated_at, c.resolved_at)) is not None]
            operators.append({
                "id": user.id, "name": user.full_name, "is_active": user.is_active,
                "in_progress": sum(1 for c in mine if c.status == "IN_PROGRESS"),
                "resolved": len(done),
                "median_resolution_minutes": median(times) if times else None,
                "average_rating": (sum(c.rating for c in done if c.rating) / len(r)) if (
                    r := [c for c in done if c.rating]) else None,
            })

        return {
            "days": days,
            "total": len(conversations),
            "resolved_by_assistant": len(by_assistant),
            "resolved_by_operator": len(by_operator),
            "open": len(open_items),
            "waiting": sum(1 for c in open_items if c.status == "ESCALATED"),
            "self_service_rate": len(by_assistant) / len(resolved) if resolved else None,
            "median_resolution_minutes": median(resolution) if resolution else None,
            "median_first_reply_minutes": median(first_reply) if first_reply else None,
            "average_rating": sum(ratings) / len(ratings) if ratings else None,
            "ratings_count": len(ratings),
            "daily": [{"date": day.isoformat(), **values} for day, values in daily.items()],
            "top_problems": top_problems,
            "urgency": {level: urgency.get(level, 0) for level in URGENCY_LEVELS},
            "operators": operators,
        }
