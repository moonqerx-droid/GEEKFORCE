"""Two problems in one request, through the HTTP API: both are handled, none is lost."""


def send(client, cid, text):
    response = client.post(f"/api/conversations/{cid}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return response.json()


def step(client, cid, outcome):
    response = client.post(f"/api/conversations/{cid}/step-result", json={"outcome": outcome})
    assert response.status_code == 200, response.text
    return response.json()


def last_reply(state):
    return next(m["content"] for m in reversed(state["messages"]) if m["role"] == "assistant")


def test_the_printer_is_worked_on_while_the_access_request_waits(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "нужен доступ к папке отдела на общем диске, и ещё принтер не печатает")

    assert state["status"] in {"CLARIFYING", "TROUBLESHOOTING"}
    assert "нужен специалист" in last_reply(state) and "принтер" in last_reply(state).lower()
    while state["status"] == "CLARIFYING":
        state = send(client, cid, "ничего не пишет")

    state = step(client, cid, "helped")

    assert state["status"] == "ESCALATED"
    card = state["escalation_card"]
    assert {i["playbook_id"]: i["status"] for i in card["issues"]} == {
        "access_rights": "handed_off", "printer": "resolved"}
    assert card["recommended_team"] == "Администраторы доступа"


def test_both_problems_solved_close_with_both_named(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "принтер не печатает и не приходят письма")
    while state["status"] != "RESOLVED":
        if state["status"] == "CLARIFYING":
            state = send(client, cid, "в браузере" if "браузере" in last_reply(state) else "нет")
        elif state["status"] == "TROUBLESHOOTING":
            state = step(client, cid, "helped")
        elif state["status"] == "VERIFYING":
            state = send(client, cid, "да, всё работает")
        else:
            raise AssertionError(state["status"])

    assert "Переходим ко второй проблеме" in " ".join(m["content"] for m in state["messages"])
    assert "обе проблемы" in last_reply(state).lower()
