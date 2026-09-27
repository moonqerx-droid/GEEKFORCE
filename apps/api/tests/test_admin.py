from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import require_admin, require_verified_user
from app.core.security import utc_now
from app.main import app
from app.models.auth import User
from app.models.conversation import Conversation, Message
from app.services.admin import bootstrap_admin


def make_user(db_session, user_id, role, first_name="Мария", last_name="Иванова", active=True):
    user = User(
        id=user_id, first_name=first_name, last_name=last_name,
        email=f"{user_id}@test.local", department="it", password_hash="unused",
        role=role, email_verified_at=utc_now(), is_active=active,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def admin(db_session, client):
    user = make_user(db_session, "admin-1", "admin")
    app.dependency_overrides[require_admin] = lambda: user
    return user


def test_non_admin_is_rejected(db_session, client):
    operator = make_user(db_session, "op-9", "operator")
    app.dependency_overrides[require_verified_user] = lambda: operator

    assert client.get("/api/admin/metrics").status_code == 403


def test_invite_operator_returns_link_and_lists_pending(client, admin):
    response = client.post("/api/admin/operators/invite", json={
        "email": "New.Operator@Company.ru", "first_name": "Олег", "last_name": "Кузнецов",
    })

    assert response.status_code == 201
    body = response.json()
    assert "/operator/register?" in body["invite_url"]
    assert "token=" in body["invite_url"]
    team = client.get("/api/admin/operators").json()
    pending = [item for item in team if item["status"] == "invited"]
    assert pending[0]["email"] == "new.operator@company.ru"
    assert pending[0]["name"] == "Олег Кузнецов"


def test_invite_rejects_existing_user(db_session, client, admin):
    make_user(db_session, "op-1", "operator")

    response = client.post("/api/admin/operators/invite", json={
        "email": "op-1@test.local", "first_name": "Анна", "last_name": "Смирнова",
    })

    assert response.status_code == 409


def test_invited_operator_registers_with_verified_email(client, admin):
    invite = client.post("/api/admin/operators/invite", json={
        "email": "anna@company.ru", "first_name": "Анна", "last_name": "Смирнова",
    }).json()
    token = invite["invite_url"].split("token=")[1].split("&")[0]

    registered = client.post("/api/auth/operator/register", json={
        "first_name": "Анна", "last_name": "Смирнова", "email": "anna@company.ru",
        "department": "it", "password": "StrongPass123", "password_confirmation": "StrongPass123",
        "invite_token": token,
    })

    assert registered.status_code == 201
    assert registered.json()["role"] == "operator"
    assert registered.json()["email_verified_at"] is not None
    team = client.get("/api/admin/operators").json()
    assert [item["status"] for item in team if item["email"] == "anna@company.ru"] == ["active"]


def test_admin_deactivates_operator(db_session, client, admin):
    make_user(db_session, "op-1", "operator", "Анна", "Смирнова")

    response = client.patch("/api/admin/operators/op-1", json={"is_active": False})

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"


def test_admin_cannot_deactivate_self(client, admin):
    assert client.patch("/api/admin/operators/admin-1", json={"is_active": False}).status_code == 400


def add_conversation(db_session, *, days_ago, playbook, urgency="normal", resolved_by=None,
                     assignee=None, minutes_to_resolve=10, minutes_to_reply=None, rating=None,
                     status=None):
    created = utc_now() - timedelta(days=days_ago, hours=1)
    conversation = Conversation(
        workflow_version="triage-v1", created_at=created, updated_at=created,
        playbook_id=playbook, urgency=urgency, service=playbook,
        status=status or ("RESOLVED" if resolved_by else "ESCALATED"),
        resolved_by=resolved_by, rating=rating,
        assignee_id=assignee.id if assignee else None,
    )
    if resolved_by:
        conversation.resolved_at = created + timedelta(minutes=minutes_to_resolve)
    if resolved_by == "operator" or status in {"ESCALATED", "IN_PROGRESS"}:
        conversation.escalated_at = created + timedelta(minutes=2)
    if minutes_to_reply is not None:
        conversation.first_operator_reply_at = created + timedelta(minutes=2 + minutes_to_reply)
    conversation.messages.append(Message(role="user", content="проблема", created_at=created))
    db_session.add(conversation)
    db_session.commit()
    return conversation


def test_metrics_summary(db_session, client, admin):
    operator = make_user(db_session, "op-1", "operator", "Анна", "Смирнова")
    add_conversation(db_session, days_ago=1, playbook="vpn_connection", resolved_by="assistant",
                     minutes_to_resolve=6, rating=5)
    add_conversation(db_session, days_ago=2, playbook="vpn_connection", resolved_by="assistant",
                     minutes_to_resolve=10, rating=4)
    add_conversation(db_session, days_ago=2, playbook="password_login", resolved_by="operator",
                     assignee=operator, minutes_to_resolve=40, minutes_to_reply=4, rating=3)
    add_conversation(db_session, days_ago=3, playbook="access_rights", urgency="high",
                     status="IN_PROGRESS", assignee=operator, minutes_to_reply=8)
    add_conversation(db_session, days_ago=40, playbook="vpn_connection", resolved_by="assistant")

    metrics = client.get("/api/admin/metrics?days=7").json()

    assert metrics["total"] == 4
    assert metrics["resolved_by_assistant"] == 2
    assert metrics["resolved_by_operator"] == 1
    assert metrics["open"] == 1
    assert metrics["self_service_rate"] == pytest.approx(2 / 3)
    assert metrics["median_resolution_minutes"] == pytest.approx(10)
    assert metrics["median_first_reply_minutes"] == pytest.approx(6)
    assert metrics["average_rating"] == pytest.approx(4)
    assert metrics["ratings_count"] == 3
    assert len(metrics["daily"]) == 7
    assert sum(day["assistant"] for day in metrics["daily"]) == 2
    top = {item["playbook_id"]: item for item in metrics["top_problems"]}
    assert top["vpn_connection"]["count"] == 2
    assert top["vpn_connection"]["escalation_rate"] == 0
    assert top["password_login"]["escalation_rate"] == 1
    assert metrics["urgency"]["high"] == 1
    load = {item["name"]: item for item in metrics["operators"]}
    assert load["Анна Смирнова"]["in_progress"] == 1
    assert load["Анна Смирнова"]["resolved"] == 1


def test_bootstrap_admin_is_idempotent(db_session):
    first = bootstrap_admin(db_session, email="Boss@Company.ru", password="StrongPass123")
    second = bootstrap_admin(db_session, email="boss@company.ru", password="StrongPass123")

    assert first.id == second.id
    assert first.role == "admin"
    assert first.email_verified_at is not None


def test_bootstrap_admin_skips_without_credentials(db_session):
    assert bootstrap_admin(db_session, email="", password="") is None
