"""A second request about the same problem points to the one already open."""


def start(client, text):
    conversation_id = client.post("/api/conversations").json()["id"]
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_same_problem_points_to_the_open_request(client):
    first = start(client, "Не подключается VPN из дома")
    second = start(client, "впн опять не работает")

    assert second["similar_open"] == {"id": first["id"], "summary": first["summary"]}
    assert client.get(f"/api/conversations/{second['id']}").json()["similar_open"]["id"] == first["id"]


def test_other_problems_and_closed_requests_are_not_suggested(client):
    start(client, "Не подключается VPN из дома")
    printer = start(client, "принтер не печатает")
    assert printer["similar_open"] is None


def test_an_unclear_request_is_not_matched(client):
    start(client, "Помогите, всё сломалось")
    again = start(client, "Помогите, всё сломалось")
    assert again["similar_open"] is None
