"""«Срочно»: the employee marks the request urgent — it goes to a specialist at once, to the top
of the queue, with a promise of when they will answer."""


def send(client, cid, text):
    response = client.post(f"/api/conversations/{cid}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return response.json()


def new(client, text):
    cid = client.post("/api/conversations").json()["id"]
    return cid, send(client, cid, text)


def last_reply(state):
    return next(m["content"] for m in reversed(state["messages"]) if m["role"] == "assistant")


def test_urgent_hands_over_at_once_with_a_promise(client):
    cid, _ = new(client, "принтер не печатает")

    response = client.post(f"/api/conversations/{cid}/urgent")

    assert response.status_code == 200, response.text
    state = response.json()
    assert state["status"] == "ESCALATED"
    assert state["urgency"] == "high"
    assert state["urgency_reason"] == "сотрудник отметил обращение как срочное"
    assert "срочн" in last_reply(state).lower() and "в течение часа" in last_reply(state)
    assert state["escalation_card"]["urgency"] == "high"


def test_urgent_goes_to_the_top_of_the_queue(client):
    calm, _ = new(client, "позовите специалиста")
    urgent, _ = new(client, "принтер не печатает")

    client.post(f"/api/conversations/{urgent}/urgent")

    queue = client.get("/api/operator/tickets").json()
    assert queue[0]["id"] == urgent
    assert calm in [ticket["id"] for ticket in queue]


def test_already_with_a_specialist_just_rises(client):
    cid, state = new(client, "позовите специалиста")
    assert state["status"] == "ESCALATED" and state["urgency"] == "normal"

    state = client.post(f"/api/conversations/{cid}/urgent").json()

    assert state["status"] == "ESCALATED"
    assert state["urgency"] == "high"
    assert "пометку «Срочно»" in last_reply(state)


def test_critical_stays_critical(client):
    cid, state = new(client, "у всех не работает почта")
    assert state["urgency"] == "critical"

    state = client.post(f"/api/conversations/{cid}/urgent").json()

    assert state["urgency"] == "critical"


def test_nothing_to_hurry_without_a_description(client):
    cid = client.post("/api/conversations").json()["id"]
    assert client.post(f"/api/conversations/{cid}/urgent").status_code == 409


def test_a_solved_request_is_not_hurried(client):
    cid, state = new(client, "забыл пароль")
    client.post(f"/api/conversations/{cid}/step-result", json={"outcome": "helped"})
    send(client, cid, "да, всё работает")

    assert client.post(f"/api/conversations/{cid}/urgent").status_code == 409


def test_the_due_time_is_given_for_the_employee(client):
    cid, _ = new(client, "принтер не печатает")

    state = client.post(f"/api/conversations/{cid}/urgent").json()

    assert state["reply_due_at"] is not None
    assert state["reply_target_minutes"] == 60
