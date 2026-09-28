"""Reply templates: the support lead maintains them, specialists read and insert them."""

import pytest
from sqlalchemy import select

from app.api.dependencies.auth import require_admin, require_operator, require_verified_user
from app.core.security import utc_now
from app.main import app
from app.models.audit import AdminAuditEvent
from app.models.auth import User

URL = "/api/operator/templates"


def make_user(db_session, user_id, role):
    user = User(id=user_id, first_name="Мария", last_name="Иванова", email=f"{user_id}@example.org",
                department="it", password_hash="x", role=role, email_verified_at=utc_now())
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def admin(db_session, client):
    user = make_user(db_session, "admin-tpl", "admin")
    app.dependency_overrides[require_admin] = lambda: user
    return user


def test_admin_creates_edits_and_deletes_a_template(client, admin, db_session):
    created = client.post(URL, json={
        "title": "  Сброс сессии CRM ", "body": "{имя}, сбросила зависшую сессию. Попробуйте войти ещё раз.",
    })
    assert created.status_code == 201, created.text
    template = created.json()
    assert template["title"] == "Сброс сессии CRM"
    assert template["body"].startswith("{имя}, сбросила")

    edited = client.patch(f"{URL}/{template['id']}", json={"title": "Сброс сессии"})
    assert edited.status_code == 200
    assert edited.json()["title"] == "Сброс сессии"
    assert edited.json()["body"] == template["body"]

    assert client.delete(f"{URL}/{template['id']}").status_code == 204
    assert client.get(URL).json() == []
    assert client.delete(f"{URL}/{template['id']}").status_code == 404

    actions = [event.action for event in db_session.scalars(select(AdminAuditEvent)).all()]
    assert actions == ["template.created", "template.updated", "template.deleted"]


def test_specialists_read_templates_sorted_by_title(client, admin):
    for title in ["Перезагрузка", "Доступ выдан", "Ваш пароль сброшен"]:
        client.post(URL, json={"title": title, "body": f"{title}."})

    listed = client.get(URL)

    assert listed.status_code == 200
    assert [item["title"] for item in listed.json()] == ["Ваш пароль сброшен", "Доступ выдан", "Перезагрузка"]


@pytest.mark.parametrize("payload", [
    {"title": "   ", "body": "текст"},
    {"title": "Название", "body": "  "},
    {"title": "x" * 121, "body": "текст"},
    {"title": "Название", "body": "x" * 4001},
])
def test_blank_or_too_long_templates_are_refused(client, admin, payload):
    assert client.post(URL, json=payload).status_code == 422


def test_specialists_cannot_change_templates(client, db_session):
    operator = make_user(db_session, "op-tpl", "operator")
    app.dependency_overrides[require_verified_user] = lambda: operator

    assert client.get(URL).status_code == 200
    assert client.post(URL, json={"title": "Шаблон", "body": "Текст"}).status_code == 403


def test_employees_cannot_read_templates(client, db_session):
    employee = make_user(db_session, "emp-tpl", "employee")
    app.dependency_overrides.pop(require_operator, None)
    app.dependency_overrides[require_verified_user] = lambda: employee

    assert client.get(URL).status_code == 403


def test_untrusted_origin_cannot_write(client, admin):
    response = client.post(URL, json={"title": "Шаблон", "body": "Текст"}, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
