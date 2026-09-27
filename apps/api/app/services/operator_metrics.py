from __future__ import annotations

from collections import Counter
from datetime import timedelta
from math import ceil
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import utc_now
from app.models.auth import User
from app.models.conversation import Conversation


class OperatorMetricsNotFound(Exception):
    pass


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=utc_now().tzinfo)


def _minutes(start, end) -> float | None:
    if start is None or end is None:
        return None
    return (_aware(end) - _aware(start)).total_seconds() / 60


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * 0.9) - 1)]


class OperatorMetricsService:
    def __init__(self, session: Session, first_reply_sla_minutes: int = 15):
        self.session = session
        self.first_reply_sla_minutes = first_reply_sla_minutes

    def for_operator(self, operator_id: str, days: int) -> dict:
        operator = self.session.get(User, operator_id)
        if operator is None or operator.role not in {"operator", "admin"}:
            raise OperatorMetricsNotFound(operator_id)
        now = utc_now()
        since = now - timedelta(days=days)
        start_day = (now - timedelta(days=days - 1)).date()
        tickets = [
            item for item in self.session.scalars(
                select(Conversation).where(Conversation.assignee_id == operator_id)
            ).all()
            if _aware(item.created_at) >= since
        ]
        resolved = [item for item in tickets if item.status == "RESOLVED"]
        first_reply_times = [
            value for item in tickets
            if (value := _minutes(item.escalated_at, item.first_operator_reply_at)) is not None
        ]
        resolution_times = [
            value for item in resolved
            if (value := _minutes(item.assigned_at or item.escalated_at, item.resolved_at)) is not None
        ]
        ratings = [item.rating for item in resolved if item.rating is not None]
        daily = {start_day + timedelta(days=offset): 0 for offset in range(days)}
        for item in resolved:
            if item.resolved_at is not None and (day := _aware(item.resolved_at).date()) in daily:
                daily[day] += 1
        topics = Counter(item.playbook_id or "unknown" for item in tickets)
        urgency = Counter(item.urgency for item in tickets)
        return {
            "operator_id": operator.id,
            "operator_name": operator.full_name,
            "days": days,
            "assigned": len(tickets),
            "resolved": len(resolved),
            "in_progress": sum(item.status == "IN_PROGRESS" for item in tickets),
            "waiting_first_reply": sum(
                item.status == "IN_PROGRESS" and item.first_operator_reply_at is None for item in tickets
            ),
            "median_first_reply_minutes": median(first_reply_times) if first_reply_times else None,
            "p90_first_reply_minutes": _p90(first_reply_times),
            "median_resolution_minutes": median(resolution_times) if resolution_times else None,
            "p90_resolution_minutes": _p90(resolution_times),
            "average_rating": sum(ratings) / len(ratings) if ratings else None,
            "ratings_count": len(ratings),
            "first_reply_sla_rate": (
                sum(value <= self.first_reply_sla_minutes for value in first_reply_times) / len(first_reply_times)
                if first_reply_times else None
            ),
            "daily": [{"date": day.isoformat(), "resolved": count} for day, count in daily.items()],
            "topics": [
                {"name": name, "count": count}
                for name, count in sorted(topics.items(), key=lambda item: (-item[1], item[0]))
            ],
            "urgency": {level: urgency.get(level, 0) for level in ("low", "normal", "high", "critical")},
        }
