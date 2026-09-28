"""The employee sees one-tap answers for the question the assistant just asked."""

import pytest


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
    _, result = start(client, "Не приходят письма в Outlook")
    assert "ошибк" in result["messages"][-1]["content"]
    assert result["quick_replies"] == []


def test_unclear_request_offers_the_likely_areas(client):
    conversation_id, result = start(client, "Помогите, всё сломалось")
    assert result["quick_replies"][0] == "Вход или пароль"
    assert result["quick_replies"][-1] == "Другое"

    picked = client.post(f"/api/conversations/{conversation_id}/messages",
                         json={"content": "Почта", "expected_revision": result["revision"]}).json()

    assert picked["playbook_id"] == "email_outlook"


@pytest.mark.parametrize("tap, playbook", [
    ("Вход или пароль", "password_login"),
    ("VPN", "vpn_connection"),
    ("Интернет или Wi-Fi", "network_wifi"),
    ("Всё медленно работает", "slow_performance"),
    ("Нет доступа к папке или программе", "access_rights"),
])
def test_every_area_button_leads_to_its_scenario(client, tap, playbook):
    conversation_id, result = start(client, "Помогите, всё сломалось")
    assert tap in result["quick_replies"]
    picked = client.post(f"/api/conversations/{conversation_id}/messages",
                         json={"content": tap, "expected_revision": result["revision"]}).json()
    assert picked["playbook_id"] == playbook
