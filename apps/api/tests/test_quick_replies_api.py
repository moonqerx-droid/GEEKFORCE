"""The employee sees one-tap answers for the question the assistant just asked."""


def start(client, text):
    conversation_id = client.post("/api/conversations").json()["id"]
    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return conversation_id, response.json()


def test_closed_question_comes_with_buttons_and_a_tap_answers_it(client):
    conversation_id, first = start(client, "Не работает почта, письма не приходят")
    assert first["status"] == "CLARIFYING"
    assert "Outlook" in first["messages"][-1]["content"]
    assert first["quick_replies"] == ["В программе Outlook", "В браузере", "Не знаю"]

    answered = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "В браузере", "expected_revision": first["revision"]},
    ).json()

    assert answered["known_facts"]["mail_client"] == "web"
    assert "В браузере" not in answered["quick_replies"]
    reloaded = client.get(f"/api/conversations/{conversation_id}").json()
    assert reloaded["quick_replies"] == answered["quick_replies"]


def test_free_text_question_has_no_buttons(client):
    _, result = start(client, "Помогите")
    assert result["quick_replies"] == []
