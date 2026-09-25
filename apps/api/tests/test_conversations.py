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
