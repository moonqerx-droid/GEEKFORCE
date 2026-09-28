from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies.auth import require_employee
from app.api.routes.operator import IncidentServiceDependency
from app.models.auth import User

router = APIRouter(prefix="/api/known-issues", tags=["known-issues"])


class KnownIssue(BaseModel):
    """A confirmed outage as an employee needs it: what is down, since when, what support says."""

    id: str
    service: str
    since: datetime
    affected: int
    update: str | None = None


@router.get("", response_model=list[KnownIssue])
def list_known_issues(
    service: IncidentServiceDependency,
    _user: Annotated[User, Depends(require_employee)],
) -> list[KnownIssue]:
    # Only outages a specialist confirmed: a radar guess must not tell people something is broken.
    return [
        KnownIssue(
            id=item.id,
            service=item.service_label or item.service,
            since=item.first_seen_at or item.created_at,
            affected=item.affected_employees or item.conversation_count,
            update=item.latest_update.message if item.latest_update else None,
        )
        for item in service.list_incidents()
        if item.status.value == "ACTIVE"
    ]
