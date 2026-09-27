from datetime import timedelta

import pytest

from app.core.security import hash_password, utc_now
from app.models.auth import User
from app.models.conversation import Conversation
from app.services.operator_metrics import OperatorMetricsService


def add_operator(db_session, user_id: str, name: str) -> User:
    first_name, last_name = name.split(maxsplit=1)
    user = User(
        id=user_id,
        first_name=first_name,
        last_name=last_name,
        email=f"{user_id}@example.org",
        department="it",
        password_hash=hash_password("StrongPass123"),
        role="operator",
        email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


def add_ticket(
    db_session,
    operator: User,
    *,
    days_ago: int,
    status: str,
    first_reply: int | None = None,
    resolution: int | None = None,
    rating: int | None = None,
    playbook: str = "vpn_connection",
    urgency: str = "normal",
):
    start = utc_now() - timedelta(days=days_ago, hours=1)
    ticket = Conversation(
        workflow_version="triage-v1",
        status=status,
        created_at=start,
        updated_at=start,
        escalated_at=start,
        assigned_at=start,
        assignee_id=operator.id,
        playbook_id=playbook,
        urgency=urgency,
        rating=rating,
    )
    if first_reply is not None:
        ticket.first_operator_reply_at = start + timedelta(minutes=first_reply)
    if resolution is not None:
        ticket.resolved_at = start + timedelta(minutes=resolution)
        ticket.resolved_by = "operator"
    db_session.add(ticket)
    db_session.commit()


def test_operator_metrics_are_scoped_and_hand_calculated(db_session):
    anna = add_operator(db_session, "anna-metrics", "Анна Смирнова")
    oleg = add_operator(db_session, "oleg-metrics", "Олег Кузнецов")
    add_ticket(db_session, anna, days_ago=1, status="RESOLVED", first_reply=3, resolution=20, rating=4)
    add_ticket(db_session, anna, days_ago=2, status="RESOLVED", first_reply=7, resolution=40, rating=5)
    add_ticket(db_session, anna, days_ago=0, status="IN_PROGRESS")
    add_ticket(db_session, oleg, days_ago=1, status="RESOLVED", first_reply=60, resolution=120, rating=1)

    result = OperatorMetricsService(db_session, first_reply_sla_minutes=15).for_operator(anna.id, 7)

    assert result["assigned"] == 3
    assert result["resolved"] == 2
    assert result["in_progress"] == 1
    assert result["waiting_first_reply"] == 1
    assert result["median_first_reply_minutes"] == pytest.approx(5)
    assert result["p90_first_reply_minutes"] == pytest.approx(7)
    assert result["median_resolution_minutes"] == pytest.approx(30)
    assert result["average_rating"] == pytest.approx(4.5)
    assert result["ratings_count"] == 2
    assert result["first_reply_sla_rate"] == 1
    assert sum(day["resolved"] for day in result["daily"]) == 2
    assert result["topics"][0] == {"name": "vpn_connection", "count": 3}


def test_operator_metrics_ignore_items_outside_period(db_session):
    operator = add_operator(db_session, "old-metrics", "Иван Старый")
    add_ticket(db_session, operator, days_ago=40, status="RESOLVED", first_reply=2, resolution=4)

    result = OperatorMetricsService(db_session).for_operator(operator.id, 7)

    assert result["assigned"] == 0
    assert result["resolved"] == 0
    assert result["median_first_reply_minutes"] is None

