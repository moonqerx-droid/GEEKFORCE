import pytest

from app.api.dependencies.auth import get_current_user, require_admin, require_operator
from app.core.security import hash_password, utc_now
from app.main import app
from app.models.auth import User
from app.models.conversation import Conversation


def add_user(db_session, user_id: str, role: str) -> User:
    user = User(
        id=user_id,
        first_name="Анна",
        last_name="Смирнова",
        email=f"{user_id}@example.org",
        department="it",
        password_hash=hash_password("StrongPass123"),
        role=role,
        email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def operator_client(db_session, client):
    operator = add_user(db_session, "operator-profile", "operator")
    app.dependency_overrides[get_current_user] = lambda: operator
    app.dependency_overrides[require_operator] = lambda: operator
    return client, operator


def test_profile_returns_identity_and_updates_only_safe_fields(db_session, operator_client):
    client, operator = operator_client

    profile = client.get("/api/profile")
    updated = client.patch("/api/profile", json={
        "full_name": "Анна Петрова",
        "department": "operations",
    })

    assert profile.status_code == 200
    assert profile.json()["name"] == "Анна Смирнова"
    assert profile.json()["role"] == "operator"
    assert updated.status_code == 200
    assert updated.json()["name"] == "Анна Петрова"
    assert updated.json()["department"] == "operations"
    db_session.refresh(operator)
    assert operator.email == "operator-profile@example.org"
    assert operator.role == "operator"


def test_operator_profile_metrics_exclude_team_comparison(db_session, operator_client):
    client, operator = operator_client
    db_session.add(Conversation(
        workflow_version="triage-v1",
        status="IN_PROGRESS",
        assignee_id=operator.id,
        escalated_at=utc_now(),
        assigned_at=utc_now(),
    ))
    db_session.commit()

    response = client.get("/api/profile/metrics?days=7")

    assert response.status_code == 200
    body = response.json()
    assert body["in_progress"] == 1
    assert body["waiting_first_reply"] == 1
    assert "operators" not in body
    assert "rank" not in body
    assert "topics" not in body


def test_admin_reads_full_metrics_for_one_operator(db_session, client):
    admin = add_user(db_session, "admin-profile", "admin")
    operator = add_user(db_session, "operator-detail", "operator")
    app.dependency_overrides[require_admin] = lambda: admin

    response = client.get(f"/api/admin/users/{operator.id}/metrics?days=30")

    assert response.status_code == 200
    assert response.json()["operator_id"] == operator.id
    assert "topics" in response.json()
    assert len(response.json()["daily"]) == 30


def test_employee_has_no_specialist_metrics(db_session, client):
    employee = add_user(db_session, "employee-profile", "employee")
    app.dependency_overrides[get_current_user] = lambda: employee
    app.dependency_overrides[require_operator] = lambda: require_operator(employee)

    assert client.get("/api/profile").status_code == 200
    assert client.get("/api/profile/metrics").status_code == 403
