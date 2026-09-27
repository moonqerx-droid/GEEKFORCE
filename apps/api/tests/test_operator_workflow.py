import pytest

from app.api.dependencies.auth import require_admin, require_employee, require_operator
from app.core.security import utc_now
from app.main import app
from app.models.auth import User


def make_user(db_session, user_id, role, first_name="Анна", last_name="Смирнова"):
    user = User(
        id=user_id, first_name=first_name, last_name=last_name,
        email=f"{user_id}@test.local", department="it", password_hash="unused",
        role=role, email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def people(db_session, client):
    employee = make_user(db_session, "emp-1", "employee", "Иван", "Петров")
    operator = make_user(db_session, "op-1", "operator", "Анна", "Смирнова")
    other = make_user(db_session, "op-2", "operator", "Олег", "Кузнецов")
    admin = make_user(db_session, "admin-1", "admin", "Мария", "Иванова")
    app.dependency_overrides[require_employee] = lambda: employee
    app.dependency_overrides[require_operator] = lambda: operator
    app.dependency_overrides[require_admin] = lambda: admin
    return {"employee": employee, "operator": operator, "other": other, "admin": admin}


def act_as_operator(user):
    app.dependency_overrides[require_operator] = lambda: user


def escalated(client, text="Не работает CRM, срочно, встреча через 20 минут"):
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": text})
    response = client.post(f"/api/conversations/{conversation_id}/escalate")
    assert response.json()["status"] == "ESCALATED"
    return conversation_id


def test_escalation_records_timestamp(client, people):
    conversation_id = escalated(client)

    conversation = client.get(f"/api/conversations/{conversation_id}").json()

    assert conversation["escalated_at"] is not None
    assert conversation["resolved_at"] is None


def test_employee_message_after_escalation_is_kept_without_assistant_reply(client, people):
    conversation_id = escalated(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Добавлю: ошибка 502 на входе"},
    )

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Добавлю: ошибка 502 на входе"


def test_operator_assigns_replies_and_resolves(client, people):
    conversation_id = escalated(client)

    assigned = client.post(f"/api/operator/tickets/{conversation_id}/assign")
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "IN_PROGRESS"
    assert assigned.json()["assignee_name"] == "Анна Смирнова"
    assert assigned.json()["assigned_at"] is not None

    replied = client.post(
        f"/api/operator/tickets/{conversation_id}/messages",
        json={"content": "Здравствуйте! Сбросила сессию, попробуйте войти снова."},
    )
    assert replied.status_code == 200
    body = replied.json()
    assert body["messages"][-1]["role"] == "operator"
    assert body["messages"][-1]["author_name"] == "Анна Смирнова"
    assert body["first_operator_reply_at"] is not None

    employee_view = client.get(f"/api/conversations/{conversation_id}").json()
    assert employee_view["messages"][-1]["content"].startswith("Здравствуйте!")

    resolved = client.post(
        f"/api/operator/tickets/{conversation_id}/resolve",
        json={"summary": "Сброшена зависшая сессия CRM"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_by"] == "operator"
    assert resolved.json()["resolved_at"] is not None
    assert "Сброшена зависшая сессия CRM" in resolved.json()["messages"][-1]["content"]


def test_first_reply_auto_assigns_unassigned_ticket(client, people):
    conversation_id = escalated(client)

    response = client.post(
        f"/api/operator/tickets/{conversation_id}/messages", json={"content": "Смотрю"},
    )

    assert response.json()["status"] == "IN_PROGRESS"
    assert response.json()["assignee_id"] == "op-1"


def test_cannot_take_ticket_assigned_to_another_operator(client, people):
    conversation_id = escalated(client)
    client.post(f"/api/operator/tickets/{conversation_id}/assign")

    act_as_operator(people["other"])

    assert client.post(f"/api/operator/tickets/{conversation_id}/assign").status_code == 409
    assert client.post(
        f"/api/operator/tickets/{conversation_id}/messages", json={"content": "Я тоже"},
    ).status_code == 409


def test_operator_cannot_touch_conversation_that_was_not_escalated(client, people):
    conversation_id = client.post("/api/conversations").json()["id"]

    assert client.post(f"/api/operator/tickets/{conversation_id}/assign").status_code == 409
    assert client.get(f"/api/operator/tickets/{conversation_id}").status_code == 404


def test_queue_scopes(client, people):
    waiting = escalated(client, "Не работает CRM")
    mine = escalated(client, "Не работает VPN")
    done = escalated(client, "Не работает почта")
    client.post(f"/api/operator/tickets/{mine}/assign")
    client.post(f"/api/operator/tickets/{done}/resolve", json={"summary": "Готово"})

    queue = {t["id"] for t in client.get("/api/operator/tickets").json()}
    my = {t["id"] for t in client.get("/api/operator/tickets?scope=mine").json()}
    resolved = {t["id"] for t in client.get("/api/operator/tickets?scope=resolved").json()}

    assert queue == {waiting, mine}
    assert my == {mine}
    assert resolved == {done}


def test_ticket_includes_employee_identity(client, people):
    conversation_id = escalated(client)

    ticket = client.get(f"/api/operator/tickets/{conversation_id}").json()

    assert ticket["owner_name"] == "Иван Петров"
    assert ticket["owner_department"] == "it"
    assert ticket["original_request"].startswith("Не работает CRM")


def test_employee_rates_resolved_conversation_once_resolved(client, people):
    conversation_id = escalated(client)

    early = client.post(f"/api/conversations/{conversation_id}/rating", json={"rating": 5})
    assert early.status_code == 409

    client.post(f"/api/operator/tickets/{conversation_id}/resolve", json={"summary": "Готово"})
    rated = client.post(
        f"/api/conversations/{conversation_id}/rating", json={"rating": 5, "comment": "Быстро!"},
    )

    assert rated.status_code == 200
    assert rated.json()["rating"] == 5
    assert rated.json()["rating_comment"] == "Быстро!"


def test_rating_is_validated(client, people):
    conversation_id = escalated(client)
    client.post(f"/api/operator/tickets/{conversation_id}/resolve", json={"summary": "Готово"})

    assert client.post(
        f"/api/conversations/{conversation_id}/rating", json={"rating": 7},
    ).status_code == 422


def test_admin_can_work_the_queue(client, people):
    conversation_id = escalated(client)
    act_as_operator(people["admin"])

    response = client.post(f"/api/operator/tickets/{conversation_id}/assign")

    assert response.status_code == 200
    assert response.json()["assignee_name"] == "Мария Иванова"


def test_handoff_keeps_the_assistants_explanation(client, people):
    conversation_id = client.post("/api/conversations").json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Нужен доступ к папке бухгалтерии на общем диске"},
    ).json()

    assert response["status"] == "ESCALATED"
    last = response["messages"][-1]["content"]
    assert "папке бухгалтерии на общем диске" in last
    assert "администратор" in last.lower()
