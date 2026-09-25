def create_escalated_conversation(client, initial_message="Не работает CRM, встреча через 20 минут"):
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": initial_message},
    )
    current = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Ошибка соединения"},
    ).json()
    for _ in range(3):
        if current["status"] != "CLARIFYING":
            break
        current = client.post(
            f"/api/conversations/{conversation_id}/messages", json={"content": "Да"},
        ).json()
    assert current["status"] == "TROUBLESHOOTING"
    result = client.post(
        f"/api/conversations/{conversation_id}/step-result",
        json={"outcome": "not_helped"},
    )
    assert result.status_code == 200
    client.post(f"/api/conversations/{conversation_id}/escalate")
    return conversation_id


def test_operator_queue_returns_escalated_ticket_with_context(client):
    conversation_id = create_escalated_conversation(client)

    response = client.get("/api/operator/tickets")

    assert response.status_code == 200
    ticket = response.json()[0]
    assert ticket["id"] == conversation_id
    assert ticket["original_request"] == "Не работает CRM, встреча через 20 минут"
    assert ticket["messages"]
    assert ticket["completed_steps"]
    assert ticket["escalation_summary"]
    assert "встреча через 20 минут" in ticket["escalation_summary"]
    assert "соединения" in ticket["escalation_summary"]


def test_operator_queue_sorts_high_urgency_first(client):
    normal_id = create_escalated_conversation(client, "Не работает CRM")
    urgent_id = create_escalated_conversation(client, "Не работает CRM, срочно, встреча через 20 минут")

    tickets = client.get("/api/operator/tickets").json()

    assert [ticket["id"] for ticket in tickets] == [urgent_id, normal_id]
