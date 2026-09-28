def test_create_and_send_message(client):
    created_response = client.post("/api/conversations")
    assert created_response.status_code == 201
    created = created_response.json()

    response = client.post(
        f"/api/conversations/{created['id']}/messages",
        json={"content": "Не работает CRM, встреча через 20 минут"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CLARIFYING"
    assert response.json()["urgency"] == "high"
    assert [message["role"] for message in response.json()["messages"]] == [
        "user",
        "assistant",
    ]


def test_unknown_conversation_returns_404(client):
    response = client.get("/api/conversations/missing")

    assert response.status_code == 404


def test_blank_message_returns_422(client):
    conversation_id = client.post("/api/conversations").json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "   "},
    )

    assert response.status_code == 422
    loaded = client.get(f"/api/conversations/{conversation_id}").json()
    assert loaded["messages"] == []


def test_step_result_in_wrong_state_returns_409(client):
    conversation_id = client.post("/api/conversations").json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/step-result",
        json={"outcome": "not_helped"},
    )

    assert response.status_code == 409
    assert client.get(f"/api/conversations/{conversation_id}").json()["status"] == "NEW"


def test_escalation_endpoint_is_idempotent(client):
    conversation_id = client.post("/api/conversations").json()["id"]

    first = client.post(f"/api/conversations/{conversation_id}/escalate")
    second = client.post(f"/api/conversations/{conversation_id}/escalate")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["escalation_summary"] == second.json()["escalation_summary"]


def test_rejected_message_does_not_mutate_history(client):
    conversation_id = client.post("/api/conversations").json()["id"]
    state = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "Забыл пароль"}).json()
    client.post(f"/api/conversations/{conversation_id}/step-result",
                json={"outcome": "helped", "step_code": state["current_step"]["code"]})
    before = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "да"}).json()
    assert before["status"] == "RESOLVED"

    rejected = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Лишнее сообщение после закрытия"},
    )
    after = client.get(f"/api/conversations/{conversation_id}").json()

    assert rejected.status_code == 409
    assert after["messages"] == before["messages"]


def test_text_typed_during_a_step_is_read_as_its_result(client):
    conversation_id = client.post("/api/conversations").json()["id"]
    state = client.post(f"/api/conversations/{conversation_id}/messages",
                        json={"content": "Принтер не печатает"}).json()
    assert state["status"] == "TROUBLESHOOTING"
    first_step = state["current_step"]["code"]

    state = client.post(f"/api/conversations/{conversation_id}/messages",
                        json={"content": "не помогло", "expected_revision": state["revision"]}).json()

    assert [step["code"] for step in state["completed_steps"]] == [first_step]
    assert state["completed_steps"][0]["outcome"] == "not_helped"
    assert state["current_step"]["code"] != first_step
    assert any(m["role"] == "user" and m["content"] == "не помогло" for m in state["messages"])
