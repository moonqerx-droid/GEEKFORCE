from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.core.security import utc_now
from app.db.session import get_db
from app.models.auth import User
from app.models.conversation import Conversation
from app.schemas.sla import SlaSummaryRead
from app.services.sla import TARGET_MINUTES, summarize

router = APIRouter(prefix="/api/operator", tags=["operator"])


@router.get("/sla", response_model=SlaSummaryRead)
def sla_summary(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[User, Depends(require_admin)],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> SlaSummaryRead:
    """How many requests handed to people in the period got a first reply within the norm."""
    now = utc_now()
    since = now - timedelta(days=days)
    handed_off = db.scalars(select(Conversation).where(Conversation.escalated_at.is_not(None))).all()
    recent = [item for item in handed_off if _aware(item.escalated_at) >= since]
    summary = summarize(recent, now)
    return SlaSummaryRead(
        days=days, met=summary.met, missed=summary.missed, breached_open=summary.breached_open,
        pending=summary.pending, met_rate=summary.met_rate, targets=dict(TARGET_MINUTES),
    )


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=utc_now().tzinfo)
