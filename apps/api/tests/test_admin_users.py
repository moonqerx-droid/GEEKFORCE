from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.dependencies.auth import require_admin, require_operator
from app.core.security import hash_password, hash_token, utc_now, verify_password
from app.main import app
from app.models.auth import AuthSession, User


def add_user(db_session, *, user_id: str, role: str = "employee", email: str | None = None) -> User:
    user = User(
        id=user_id,
        first_name="Тест",
        last_name="Пользователь",
        email=email or f"{user_id}@example.org",
        department="it",
        password_hash=hash_password("OriginalPass123"),
        role=role,
        email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def admin(db_session, client):
    user = add_user(db_session, user_id="admin-managed", role="admin")
    app.dependency_overrides[require_admin] = lambda: user
    return user


def test_admin_creates_operator_with_one_time_password(db_session, client, admin):
    response = client.post("/api/admin/users/operators", json={
        "full_name": "Анна Смирнова",
        "email": "Anna.Support@Example.org",
        "department": "it",
    })

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["name"] == "Анна Смирнова"
    assert body["user"]["email"] == "anna.support@example.org"
    assert body["user"]["role"] == "operator"
    assert body["user"]["must_change_password"] is True
    assert len(body["temporary_password"]) >= 14
    created = db_session.scalar(select(User).where(User.email == "anna.support@example.org"))
    assert verify_password(created.password_hash, body["temporary_password"])


def test_admin_lists_all_roles_and_never_returns_passwords(db_session, client, admin):
    add_user(db_session, user_id="employee-managed", role="employee")
    add_user(db_session, user_id="operator-managed", role="operator")

    response = client.get("/api/admin/users")

    assert response.status_code == 200
    body = response.json()
    assert {item["role"] for item in body} == {"admin", "employee", "operator"}
    assert all("password_hash" not in item and "temporary_password" not in item for item in body)


def test_sensitive_update_revokes_sessions_and_rejects_stale_revision(db_session, client, admin):
    employee = add_user(db_session, user_id="employee-edit", role="employee")
    session = AuthSession(
        user_id=employee.id,
        token_hash=hash_token("active-session"),
        expires_at=utc_now() + timedelta(hours=1),
    )
    db_session.add(session)
    db_session.commit()

    response = client.patch(f"/api/admin/users/{employee.id}", json={
        "email": "changed@example.org",
        "role": "operator",
        "revision": 1,
    })

    assert response.status_code == 200
    assert response.json()["email"] == "changed@example.org"
    assert response.json()["revision"] == 2
    db_session.refresh(session)
    assert session.revoked_at is not None

    stale = client.patch(f"/api/admin/users/{employee.id}", json={
        "full_name": "Старое Имя",
        "revision": 1,
    })
    assert stale.status_code == 409


def test_admin_reset_password_is_one_time_and_revokes_sessions(db_session, client, admin):
    employee = add_user(db_session, user_id="employee-reset")
    session = AuthSession(
        user_id=employee.id,
        token_hash=hash_token("reset-session"),
        expires_at=utc_now() + timedelta(hours=1),
    )
    db_session.add(session)
    db_session.commit()

    response = client.post(f"/api/admin/users/{employee.id}/reset-password")

    assert response.status_code == 200
    temporary = response.json()["temporary_password"]
    db_session.refresh(employee)
    db_session.refresh(session)
    assert employee.must_change_password is True
    assert verify_password(employee.password_hash, temporary)
    assert session.revoked_at is not None


def test_admin_cannot_disable_or_demote_last_active_admin(client, admin):
    disable = client.patch(f"/api/admin/users/{admin.id}", json={
        "is_active": False,
        "revision": 1,
    })
    demote = client.patch(f"/api/admin/users/{admin.id}", json={
        "role": "operator",
        "revision": 1,
    })

    assert disable.status_code == 400
    assert demote.status_code == 400


def test_operator_with_temporary_password_is_blocked_from_role_endpoints(db_session):
    operator = add_user(db_session, user_id="operator-temp", role="operator")
    operator.must_change_password = True
    db_session.commit()

    with pytest.raises(HTTPException) as blocked:
        require_operator(operator)

    assert blocked.value.status_code == 403
    assert blocked.value.detail["code"] == "password_change_required"


def test_user_changes_temporary_password_and_clears_requirement(db_session, client):
    operator = add_user(db_session, user_id="operator-password", role="operator")
    operator.must_change_password = True
    db_session.commit()
    from app.api.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: operator

    response = client.post("/api/auth/change-password", json={
        "current_password": "OriginalPass123",
        "password": "ChangedPass456",
        "password_confirmation": "ChangedPass456",
    })

    assert response.status_code == 204
    db_session.refresh(operator)
    assert operator.must_change_password is False
    assert verify_password(operator.password_hash, "ChangedPass456")
