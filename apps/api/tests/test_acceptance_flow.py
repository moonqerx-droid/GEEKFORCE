def test_urgent_crm_problem_reaches_resolution(client):
    conversation = client.post("/api/conversations").json()
    conversation_id = conversation["id"]

    analyzed = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Не могу войти в CRM с ноутбука, через 20 минут встреча"},
    ).json()
    assert analyzed["urgency"] == "high"
    assert analyzed["status"] == "CLARIFYING"

    troubleshooting = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Пишет: ошибка соединения"},
    ).json()
    assert troubleshooting["status"] == "TROUBLESHOOTING"
    assert troubleshooting["current_step"]["code"] == "clear_crm_cookies"

    retry = client.post(
        f"/api/conversations/{conversation_id}/step-result",
        json={"outcome": "not_helped"},
    ).json()
    assert retry["status"] == "TROUBLESHOOTING"
    assert retry["current_step"]["code"] == "try_private_window"

    verifying = client.post(
        f"/api/conversations/{conversation_id}/step-result",
        json={"outcome": "helped"},
    ).json()
    assert verifying["status"] == "VERIFYING"

    resolved = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "Да, доступ восстановился"},
    ).json()
    assert resolved["status"] == "RESOLVED"
    assert [step["outcome"] for step in resolved["completed_steps"]] == [
        "not_helped",
        "helped",
    ]
