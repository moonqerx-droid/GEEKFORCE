def _start(client, message: str) -> dict:
    conversation_id = client.post("/api/conversations").json()["id"]
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": message},
    )
    assert response.status_code == 200
    return response.json()


def test_general_answer_kind_survives_reload(client) -> None:
    response = _start(client, "Как закрепить верхнюю строку в Excel?")

    assert response["answer_kind"] == "general"
    assert response["citations"] == []
    loaded = client.get(f"/api/conversations/{response['id']}").json()
    assert loaded["answer_kind"] == "general"


def test_playbook_and_handoff_are_distinguishable(client) -> None:
    playbook = _start(client, "Как подключиться к VPN-клиенту?")
    handoff = _start(client, "Сколько дней отпуска мне положено в этом году?")

    assert playbook["answer_kind"] == "playbook"
    assert handoff["answer_kind"] == "handoff"
