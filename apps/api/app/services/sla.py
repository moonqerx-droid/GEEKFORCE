"""First-reply SLA for requests handed to people.

The clock starts when the assistant hands the request over (`escalated_at`) and stops at
the specialist's first reply (`first_operator_reply_at`). Low urgency has no norm of its
own in the brief, so it shares the normal 4 hours.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

TARGET_MINUTES = {"critical": 15, "high": 60, "normal": 240, "low": 240}
# Less than this share of the norm left: warn before it is too late.
WARNING_SHARE = 0.2

SlaState = Literal["ok", "warning", "breached", "met", "missed"]


@dataclass(frozen=True)
class Sla:
    target_minutes: int
    started_at: datetime
    due_at: datetime
    replied_at: datetime | None
    state: SlaState
    waited_minutes: int
    remaining_minutes: int


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _minutes(delta: timedelta) -> int:
    return round(delta.total_seconds() / 60)


def sla_for(conversation, now: datetime) -> Sla | None:
    started = _aware(getattr(conversation, "escalated_at", None))
    if started is None:
        return None
    target = TARGET_MINUTES.get(getattr(conversation, "urgency", None) or "normal", TARGET_MINUTES["normal"])
    due = started + timedelta(minutes=target)
    replied = _aware(getattr(conversation, "first_operator_reply_at", None))
    if replied is not None:
        return Sla(target, started, due, replied, "met" if replied <= due else "missed",
                   _minutes(replied - started), _minutes(due - replied))
    now = _aware(now)
    remaining = due - now
    if remaining < timedelta(0):
        state: SlaState = "breached"
    elif remaining < timedelta(minutes=target * WARNING_SHARE):
        state = "warning"
    else:
        state = "ok"
    return Sla(target, started, due, None, state, _minutes(now - started), _minutes(remaining))


@dataclass(frozen=True)
class SlaSummary:
    met: int
    missed: int
    breached_open: int
    pending: int

    @property
    def met_rate(self) -> float | None:
        decided = self.met + self.missed + self.breached_open
        return self.met / decided if decided else None


def summarize(conversations, now: datetime) -> SlaSummary:
    """Met / missed by the first reply; still waiting past the norm counts as a miss."""
    counts = {"met": 0, "missed": 0, "breached": 0, "open": 0}
    for conversation in conversations:
        sla = sla_for(conversation, now)
        if sla is None:
            continue
        key = {"met": "met", "missed": "missed", "breached": "breached"}.get(sla.state, "open")
        counts[key] += 1
    return SlaSummary(counts["met"], counts["missed"], counts["breached"], counts["open"])
