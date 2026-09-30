"""«Решить самому» through the API: a code or a problem, answered without opening a request."""

from app.api.dependencies.auth import require_employee
from app.main import app


def test_a_code_is_looked_up(client):
    response = client.get("/api/self-help", params={"q": "впн пишет ошибка 809"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"]["code"] == "809"
    assert body["code"]["steps"], "the steps an employee can do alone"
    assert body["guide"]["playbook_id"] == "vpn_connection"


def test_looking_up_opens_no_request(client):
    client.get("/api/self-help", params={"q": "принтер не печатает"})

    assert client.get("/api/conversations").json() == []


def test_a_dangerous_topic_goes_to_a_specialist(client):
    body = client.get("/api/self-help", params={"q": "перешёл по ссылке и ввёл пароль"}).json()

    assert body["specialist_only"] is True
    assert body["notice"]


def test_popular_codes_and_topics(client):
    body = client.get("/api/self-help/popular").json()

    assert {"809", "691", "0x800CCC0E"} <= {item["code"] for item in body["codes"]}
    assert all(item["title"] for item in body["codes"])
    assert body["topics"] and all(topic["query"] for topic in body["topics"])


def test_only_for_signed_in_employees(client):
    app.dependency_overrides.pop(require_employee, None)
    assert client.get("/api/self-help", params={"q": "809"}).status_code in (401, 403)


def _with_vpn_document(db_session):
    from app.models.auth import User
    from app.services.knowledge import KnowledgeService
    from app.core.security import utc_now

    admin = User(id="admin-doc", first_name="Мария", last_name="И", email="admin-doc@example.org",
                 department="it", password_hash="x", role="admin", email_verified_at=utc_now())
    db_session.add(admin)
    db_session.commit()
    KnowledgeService(db_session).upload("vpn.md", "## Ошибка 809\n\nОшибка 809 означает, что домашний роутер "
                                        "блокирует VPN. Подключитесь к раздаче интернета с телефона.".encode(),
                                        "text/markdown", admin, title="Инструкция по VPN")


def test_after_self_help_the_document_is_not_repeated(client, db_session):
    _with_vpn_document(db_session)
    cid = client.post("/api/conversations").json()["id"]
    state = client.post(f"/api/conversations/{cid}/messages", json={"content": (
        "впн пишет ошибка 809. Уже пробовал: Подключитесь к интернету с телефона; Перезагрузите домашний роутер"
    )}).json()

    assert state["answer_kind"] != "document", "the employee already read it on «Решить самому»"
    assert state["playbook_id"] == "vpn_connection"
    assert not state["summary"].startswith("Вопрос по документу")


def test_a_complaint_answered_by_a_document_keeps_its_title(client, db_session):
    _with_vpn_document(db_session)
    cid = client.post("/api/conversations").json()["id"]
    state = client.post(f"/api/conversations/{cid}/messages", json={"content": "впн не подключается, ошибка 809"}).json()

    assert "VPN" in state["summary"] and not state["summary"].startswith("Вопрос по документу")


def test_a_question_answered_by_a_document_is_titled_as_one(client, db_session):
    _with_vpn_document(db_session)
    cid = client.post("/api/conversations").json()["id"]
    state = client.post(f"/api/conversations/{cid}/messages", json={"content": "что значит ошибка 809?"}).json()

    assert state["summary"].startswith("Вопрос по документу")
