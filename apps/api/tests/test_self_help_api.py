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
