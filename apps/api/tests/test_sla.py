"""First-reply SLA: critical 15 min, high 1 h, normal (and low) 4 h."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.api.dependencies.auth import require_admin, require_operator, require_verified_user
from app.core.security import utc_now
from app.main import app
from app.models import Conversation, Message
from app.models.auth import User
from app.services.sla import sla_for

NOW = utc_now()


def ticket(urgency="normal", escalated_minutes_ago=10, replied_after=None):
    escalated = NOW - timedelta(minutes=escalated_minutes_ago)
    replied = escalated + timedelta(minutes=replied_after) if replied_after is not None else None
    return SimpleNamespace(urgency=urgency, escalated_at=escalated, first_operator_reply_at=replied)


@pytest.mark.parametrize(("urgency", "target"), [("critical", 15), ("high", 60), ("normal", 240), ("low", 240)])
def test_target_depends_on_urgency(urgency, target):
    assert sla_for(ticket(urgency), NOW).target_minutes == target


def test_waiting_ticket_with_plenty_of_time_is_ok():
    state = sla_for(ticket("high", escalated_minutes_ago=10), NOW)

    assert state.state == "ok"
    assert state.remaining_minutes == 50
    assert state.waited_minutes == 10
    assert state.due_at == state.started_at + timedelta(minutes=60)


def test_less_than_a_fifth_left_is_a_warning():
    assert sla_for(ticket("high", escalated_minutes_ago=48), NOW).state == "ok"       # 12 of 60 left: exactly 20 %
    assert sla_for(ticket("high", escalated_minutes_ago=49), NOW).state == "warning"  # 11 left: less than 20 %
    assert sla_for(ticket("critical", escalated_minutes_ago=13), NOW).state == "warning"


def test_overdue_without_reply_is_breached():
    state = sla_for(ticket("critical", escalated_minutes_ago=40), NOW)

    assert state.state == "breached"
    assert state.remaining_minutes == -25


def test_replied_in_time_or_late():
    assert sla_for(ticket("critical", escalated_minutes_ago=60, replied_after=10), NOW).state == "met"
    late = sla_for(ticket("critical", escalated_minutes_ago=60, replied_after=30), NOW)
    assert late.state == "missed"
    assert late.waited_minutes == 30


def test_not_handed_to_people_has_no_sla():
    assert sla_for(SimpleNamespace(urgency="high", escalated_at=None, first_operator_reply_at=None), NOW) is None


def test_naive_timestamps_from_sqlite_are_treated_as_utc():
    naive = ticket("normal", escalated_minutes_ago=30)
    naive.escalated_at = naive.escalated_at.replace(tzinfo=None)

    assert sla_for(naive, NOW).waited_minutes == 30


# --- API ------------------------------------------------------------------------

def escalated(db_session, *, urgency, minutes_ago, replied_after=None, owner=None):
    # Real "now": the server compares with its own clock, not with the module import time.
    moment = utc_now() - timedelta(minutes=minutes_ago)
    item = Conversation(
        workflow_version="triage-v1", status="IN_PROGRESS" if replied_after is not None else "ESCALATED",
        urgency=urgency, service="CRM", summary="Не открывается CRM", created_at=moment, escalated_at=moment,
        first_operator_reply_at=moment + timedelta(minutes=replied_after) if replied_after is not None else None,
        owner_id=owner.id if owner else None,
    )
    item.messages.append(Message(role="user", content="Не открывается CRM"))
    db_session.add(item)
    db_session.commit()
    return item


def test_queue_tickets_carry_their_sla(client, db_session):
    item = escalated(db_session, urgency="critical", minutes_ago=14)

    [queued] = client.get("/api/operator/tickets").json()
    single = client.get(f"/api/operator/tickets/{item.id}").json()

    assert queued["sla"]["state"] == "warning"
    assert queued["sla"]["target_minutes"] == 15
    assert 0 <= queued["sla"]["remaining_minutes"] <= 1
    assert single["sla"]["state"] == "warning"


def test_admin_sees_the_share_of_tickets_answered_in_time(client, db_session):
    admin = User(id="admin-sla", first_name="Мария", last_name="Иванова", email="admin-sla@example.org",
                 department="it", password_hash="x", role="admin", email_verified_at=NOW)
    db_session.add(admin)
    db_session.commit()
    app.dependency_overrides[require_admin] = lambda: admin
    escalated(db_session, urgency="critical", minutes_ago=120, replied_after=5)    # met
    escalated(db_session, urgency="high", minutes_ago=300, replied_after=30)       # met
    escalated(db_session, urgency="critical", minutes_ago=120, replied_after=40)   # missed
    escalated(db_session, urgency="high", minutes_ago=90)                          # breached, still waiting
    escalated(db_session, urgency="normal", minutes_ago=10)                        # still in time: not counted yet

    body = client.get("/api/operator/sla?days=7").json()

    assert (body["met"], body["missed"], body["breached_open"], body["pending"]) == (2, 1, 1, 1)
    assert body["met_rate"] == pytest.approx(0.5)
    assert body["targets"] == {"critical": 15, "high": 60, "normal": 240, "low": 240}


def test_sla_summary_is_for_the_support_lead_only(client, db_session):
    operator = User(id="op-sla", first_name="Анна", last_name="С", email="op-sla@example.org",
                    department="it", password_hash="x", role="operator", email_verified_at=NOW)
    db_session.add(operator)
    db_session.commit()
    app.dependency_overrides.pop(require_operator, None)
    app.dependency_overrides[require_verified_user] = lambda: operator

    assert client.get("/api/operator/sla").status_code == 403
