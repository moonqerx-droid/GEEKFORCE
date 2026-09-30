"""Closed requests teach the assistant: a resolution becomes a step once the support lead approves it."""

from app.api.dependencies.auth import require_admin
from app.core.security import utc_now
from app.main import app
from app.models.conversation import Conversation, Message
from tests.test_admin_conversations import add_user


def closed_printer_request(db_session, owner):
    conversation = Conversation(workflow_version="triage-v1", owner_id=owner.id, status="RESOLVED",
                                playbook_id="printer", summary="Не печатает принтер", resolved_by="operator",
                                resolved_at=utc_now(), escalated_at=utc_now())
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation_id=conversation.id, role="user", content="принтер не печатает"))
    db_session.add(Message(conversation_id=conversation.id, role="operator",
                           content="Обращение закрыто. Итог: Очистил зависшую очередь печати на сервере"))
    db_session.commit()
    return conversation


def test_the_whole_loop_from_a_resolution_to_the_next_employee(client, db_session):
    admin = add_user(db_session, "admin-learning", "admin")
    app.dependency_overrides[require_admin] = lambda: admin
    source = closed_printer_request(db_session, add_user(db_session, "emp-learning", "employee"))

    overview = client.get("/api/admin/learning").json()
    [suggestion] = overview["suggestions"]
    assert suggestion["resolution"] == "Очистил зависшую очередь печати на сервере"
    assert suggestion["playbook_title"] == "Не печатает принтер"

    created = client.post("/api/admin/learning/steps", json={
        "playbook_id": "printer", "source_conversation_id": source.id,
        "instruction": "Откройте очередь печати, отмените все задания и отправьте документ заново.",
    })
    assert created.status_code == 201, created.text
    assert client.get("/api/admin/learning").json()["suggestions"] == []  # used once, not suggested again

    cid = client.post("/api/conversations").json()["id"]
    current = client.post(f"/api/conversations/{cid}/messages", json={"content": "Принтер не печатает"}).json()
    seen = []
    for _ in range(12):
        while current["status"] == "CLARIFYING":
            current = client.post(f"/api/conversations/{cid}/messages", json={"content": "Не знаю"}).json()
        if current["status"] != "TROUBLESHOOTING":
            break
        seen.append(current["current_step"]["code"])
        current = client.post(f"/api/conversations/{cid}/step-result", json={"outcome": "not_helped"}).json()
    assert seen[-1].startswith("learned."), seen  # tried last, right before the hand-off
    assert current["status"] == "ESCALATED"


def test_a_step_must_be_written_for_an_employee(client, db_session):
    admin = add_user(db_session, "admin-learning2", "admin")
    app.dependency_overrides[require_admin] = lambda: admin
    assert client.post("/api/admin/learning/steps", json={"playbook_id": "printer", "instruction": "ок"}).status_code == 422
    assert client.post("/api/admin/learning/steps", json={
        "playbook_id": "no-such", "instruction": "Перезагрузите компьютер и попробуйте снова."}).status_code == 422
