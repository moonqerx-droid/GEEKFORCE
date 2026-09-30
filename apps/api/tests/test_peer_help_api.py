"""«Помощь коллег»: сотрудник, которому не помогли шаги, выкладывает тему обращения в ленту,
коллега берётся помочь, они переписываются, автор отмечает «Помог совет коллеги»."""

import pytest

from app.api.dependencies.auth import require_employee, require_operator
from app.core.security import utc_now
from app.main import app
from app.models.auth import User
from app.models.peer_help import DirectMessage, PeerHelpMessage


def make_user(db_session, user_id, first, last, role="employee", department="sales"):
    user = User(
        id=user_id, first_name=first, last_name=last, email=f"{user_id}@test.local",
        department=department, password_hash="unused", role=role, email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def people(db_session, client):
    ivan = make_user(db_session, "emp-ivan", "Иван", "Петров")
    elena = make_user(db_session, "emp-elena", "Елена", "Соколова", department="marketing")
    olga = make_user(db_session, "emp-olga", "Ольга", "Морозова", department="hr")
    anna = make_user(db_session, "op-anna", "Анна", "Смирнова", role="operator", department="it")
    app.dependency_overrides[require_operator] = lambda: anna
    act_as(ivan)
    return {"ivan": ivan, "elena": elena, "olga": olga, "anna": anna}


def act_as(user):
    app.dependency_overrides[require_employee] = lambda: user


def escalated(client, text="VPN подключается, но портал не открывается"):
    cid = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{cid}/messages", json={"content": text})
    assert client.post(f"/api/conversations/{cid}/escalate").json()["status"] == "ESCALATED"
    return cid


def publish(client, cid):
    response = client.post(f"/api/conversations/{cid}/peer-help")
    assert response.status_code == 201, response.text
    return response.json()


def test_colleague_helps_and_gets_credit(client, people):
    cid = escalated(client)
    item = publish(client, cid)
    assert item["status"] == "OPEN"
    assert item["author"]["name"] == "Иван Петров"

    act_as(people["elena"])
    claimed = client.post(f"/api/peer-help/{item['id']}/claim")
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["status"] == "HELPING"
    sent = client.post(f"/api/peer-help/{item['id']}/messages",
                       json={"content": "Попробуйте переподключить VPN и открыть портал заново."})
    assert sent.status_code == 201

    act_as(people["ivan"])
    resolved = client.post(f"/api/peer-help/{item['id']}/resolve")
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "RESOLVED"
    again = client.post(f"/api/peer-help/{item['id']}/resolve")
    assert again.status_code == 200

    conversation = client.get(f"/api/conversations/{cid}").json()
    assert conversation["status"] == "RESOLVED"
    assert conversation["resolved_by"] == "colleague"
    assert "Елена Соколова" in conversation["messages"][-1]["content"]
    colleagues = {c["name"]: c for c in client.get("/api/colleagues").json()}
    assert colleagues["Елена Соколова"]["helped_count"] == 1


def test_feed_shows_only_the_topic(client, people):
    cid = escalated(client, "VPN не подключается, мой номер телефона 89001234567")
    publish(client, cid)

    act_as(people["elena"])
    feed = client.get("/api/peer-help").json()

    assert len(feed) == 1
    assert feed[0]["messages"] == []
    assert "89001234567" not in str(feed[0])


def test_cannot_publish_someone_elses_request(client, people):
    cid = escalated(client)
    act_as(people["elena"])

    assert client.post(f"/api/conversations/{cid}/peer-help").status_code == 404


def test_security_request_cannot_be_published(client, people):
    cid = escalated(client, "Пришло письмо с архивом, я открыл его, похоже на фишинг")

    response = client.post(f"/api/conversations/{cid}/peer-help")

    assert response.status_code == 403


def test_fresh_request_is_not_eligible(client, people):
    cid = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{cid}/messages", json={"content": "принтер не печатает"})

    assert client.post(f"/api/conversations/{cid}/peer-help").status_code == 409


def test_publishing_twice_returns_the_same_request(client, people):
    cid = escalated(client)
    first = publish(client, cid)

    second = client.post(f"/api/conversations/{cid}/peer-help")

    assert second.status_code == 201
    assert second.json()["id"] == first["id"]


def test_only_one_helper_and_not_the_author(client, people):
    item = publish(client, escalated(client))
    assert client.post(f"/api/peer-help/{item['id']}/claim").status_code == 409

    act_as(people["elena"])
    assert client.post(f"/api/peer-help/{item['id']}/claim").status_code == 200
    act_as(people["olga"])
    assert client.post(f"/api/peer-help/{item['id']}/claim").status_code == 409


def test_chat_is_private_to_author_and_helper(client, people):
    item = publish(client, escalated(client))
    act_as(people["elena"])
    client.post(f"/api/peer-help/{item['id']}/claim")

    act_as(people["olga"])
    assert client.get(f"/api/peer-help/{item['id']}").status_code == 403
    assert client.post(f"/api/peer-help/{item['id']}/messages", json={"content": "привет"}).status_code == 403


def test_only_author_confirms_the_advice(client, people):
    item = publish(client, escalated(client))
    act_as(people["elena"])
    client.post(f"/api/peer-help/{item['id']}/claim")

    assert client.post(f"/api/peer-help/{item['id']}/resolve").status_code == 403


def test_secret_in_chat_is_rejected_and_not_saved(client, people, db_session):
    item = publish(client, escalated(client))
    act_as(people["elena"])
    client.post(f"/api/peer-help/{item['id']}/claim")

    act_as(people["ivan"])
    blocked = client.post(f"/api/peer-help/{item['id']}/messages", json={"content": "пароль: qwerty123"})

    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "secret_detected"
    assert db_session.query(PeerHelpMessage).count() == 0


def test_specialist_sees_helper_and_transcript(client, people):
    cid = escalated(client)
    item = publish(client, cid)
    act_as(people["elena"])
    client.post(f"/api/peer-help/{item['id']}/claim")
    client.post(f"/api/peer-help/{item['id']}/messages", json={"content": "Перезапустите VPN-клиент."})

    ticket = client.get(f"/api/operator/tickets/{cid}").json()

    assert ticket["peer_help"]["status"] == "HELPING"
    assert ticket["peer_help"]["helper"]["name"] == "Елена Соколова"
    assert ticket["peer_help"]["messages"][0]["content"] == "Перезапустите VPN-клиент."
    queue = client.get("/api/operator/tickets").json()
    assert cid in [t["id"] for t in queue]


def test_colleagues_are_employees_only(client, people):
    names = [c["name"] for c in client.get("/api/colleagues").json()]

    assert "Анна Смирнова" not in names
    assert "Иван Петров" not in names  # себя в списке нет
    assert {"Елена Соколова", "Ольга Морозова"} <= set(names)


def test_direct_messages_between_colleagues(client, people, db_session):
    sent = client.post("/api/colleagues/emp-elena/messages", json={"content": "Елена, как настроила VPN?"})
    assert sent.status_code == 201, sent.text

    act_as(people["elena"])
    history = client.get("/api/colleagues/emp-ivan/messages").json()
    assert [m["content"] for m in history] == ["Елена, как настроила VPN?"]
    assert history[0]["sender"]["name"] == "Иван Петров"

    act_as(people["olga"])
    assert client.get("/api/colleagues/emp-ivan/messages").json() == []


def test_direct_message_moderation_and_targets(client, people, db_session):
    rude = client.post("/api/colleagues/emp-elena/messages", json={"content": "ты идиот"})
    assert rude.status_code == 422
    assert rude.json()["detail"]["code"] == "abusive_language"
    assert db_session.query(DirectMessage).count() == 0
    assert client.post("/api/colleagues/emp-ivan/messages", json={"content": "я"}).status_code == 409
    assert client.post("/api/colleagues/op-anna/messages", json={"content": "привет"}).status_code == 404


def test_specialist_closing_the_request_removes_it_from_the_feed(client, people):
    cid = escalated(client)
    publish(client, cid)

    closed = client.post(f"/api/operator/tickets/{cid}/resolve", json={"summary": "Переустановлен VPN-клиент"})

    assert closed.status_code == 200, closed.text
    assert client.get("/api/peer-help").json() == []
