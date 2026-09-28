from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.conversation import OperatorTicket


class SlaRead(BaseModel):
    target_minutes: int
    started_at: datetime
    due_at: datetime
    replied_at: datetime | None = None
    state: Literal["ok", "warning", "breached", "met", "missed"]
    waited_minutes: int
    remaining_minutes: int


class OperatorTicketWithSla(OperatorTicket):
    """A ticket plus how long the employee has been waiting for a first reply."""

    sla: SlaRead | None = None


class SlaSummaryRead(BaseModel):
    days: int
    met: int
    missed: int
    breached_open: int
    pending: int
    met_rate: float | None
    targets: dict[str, int]
