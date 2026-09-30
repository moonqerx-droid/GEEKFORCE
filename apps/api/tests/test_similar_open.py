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


def test_continue_there_moves_the_words_and_removes_the_duplicate(client):
    first = start(client, "Не подключается VPN из дома")
    second = start(client, "впн опять не работает")

    merged = client.post(f"/api/conversations/{second['id']}/merge")
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["id"] == first["id"]
    assert body["messages"][-1]["role"] == "user"
    assert body["messages"][-1]["content"] == "впн опять не работает"
    assert client.get(f"/api/conversations/{second['id']}").status_code == 404
    assert second["id"] not in [item["id"] for item in client.get("/api/conversations").json()]


def test_nothing_to_merge_into_is_a_conflict(client):
    printer = start(client, "принтер не печатает")
    assert client.post(f"/api/conversations/{printer['id']}/merge").status_code == 409
