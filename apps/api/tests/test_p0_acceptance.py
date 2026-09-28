"""P0 product flows that must stay green for the hackathon demo."""


def send(client, cid, content):
    response = client.post(f"/api/conversations/{cid}/messages", json={"content": content})
    assert response.status_code == 200, response.text
    return response.json()


def test_crm_urgent_path_resolves(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Не могу войти в CRM, через 20 минут встреча")
    assert state["urgency"] == "high"
    state = send(client, cid, "Ошибка соединения, VPN не подключён")
    assert state["status"] == "TROUBLESHOOTING"
    state = client.post(
        f"/api/conversations/{cid}/step-result", json={"outcome": "helped"}
    ).json()
    assert state["status"] == "VERIFYING"
    assert send(client, cid, "Да, доступ восстановился")["status"] == "RESOLVED"


def test_vpn_failed_steps_escalate_with_fallback_metadata(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Не подключается VPN")
    while state["status"] == "CLARIFYING":
        state = send(client, cid, "не знаю")
    while state["status"] == "TROUBLESHOOTING":
        state = client.post(
            f"/api/conversations/{cid}/step-result", json={"outcome": "not_helped"}
        ).json()
    assert state["status"] == "ESCALATED"
    assert state["escalation_card"]["original_request"] == "Не подключается VPN"
    assert state["completed_steps"]
    assert isinstance(state["rag_source_ids"], list)


def test_phishing_escalates_without_dangerous_steps(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Перешёл по фишинговой ссылке и ввёл пароль")
    assert state["status"] == "ESCALATED"
    assert state["completed_steps"] == []
    assert "Отключите" in state["messages"][-1]["content"]
    assert state["escalation_card"]["recommended_team"]


def test_unknown_issue_escalates_without_hallucinated_step(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Происходит что-то странное")
    assistant_questions = []
    while state["status"] == "CLARIFYING":
        assistant_questions.append(state["messages"][-1]["content"])
        state = send(client, cid, "не знаю")
    assert state["status"] == "ESCALATED"
    # One question with the likely areas; «не знаю» there hands over to a person.
    assert len(assistant_questions) == len(set(assistant_questions)) == 1
    assert state["completed_steps"] == []
    assert state["escalation_card"]["recommended_team"] == "Service Desk L1"


def test_mass_outage_escalates_as_mass_incident(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "CRM не работает у всего отдела, у всех ошибка 502")
    if state["status"] == "CLARIFYING":
        state = send(client, cid, "весь отдел")
    assert state["status"] == "ESCALATED"
    assert state["playbook_id"] == "mass_incident"
    assert state["urgency"] == "critical"
    tickets = client.get("/api/operator/tickets").json()
    assert any(ticket["id"] == cid for ticket in tickets)
