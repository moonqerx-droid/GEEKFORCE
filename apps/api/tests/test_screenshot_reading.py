"""The assistant reads the text on a screenshot instead of asking for it again."""

import pytest

from app.services import ocr
from tests.test_attachments import PNG, new_conversation, people, upload  # noqa: F401


@pytest.fixture
def screen(monkeypatch):
    seen = {"text": None}
    monkeypatch.setattr(ocr, "read_text", lambda data, content_type: seen["text"])
    return seen


def send(client, conversation_id, content="", attachment_ids=()):
    response = client.post(f"/api/conversations/{conversation_id}/messages",
                           json={"content": content, "attachment_ids": list(attachment_ids)})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_screenshot_alone_is_read_and_understood(client, people, screen):
    screen["text"] = "Подключение VPN\nНе удалось подключиться. Ошибка 809\nОК"
    conversation_id = new_conversation(client)
    attachment = upload(client, conversation_id).json()

    state = send(client, conversation_id, attachment_ids=[attachment["id"]])

    assert state["playbook_id"] == "vpn_connection"
    assert "809" in state["known_facts"]["error_text"]
    assert "На скриншоте вижу" in state["messages"][-1]["content"]
    assert state["messages"][0]["content"] == ""  # the employee's own words stay as typed


def test_screenshot_text_answers_the_error_question(client, people, screen):
    screen["text"] = "Microsoft Outlook\nНет подключения к Microsoft Exchange."
    conversation_id = new_conversation(client)
    attachment = upload(client, conversation_id).json()

    state = send(client, conversation_id, "не работает почта в аутлуке", [attachment["id"]])

    assert state["playbook_id"] == "email_outlook"
    assert "Exchange" in state["known_facts"]["error_text"]
    assert state["known_facts"]["screenshot_text"].startswith("Microsoft Outlook")
    assert "Есть ли сообщение об ошибке" not in state["messages"][-1]["content"]
    assert state["messages"][0]["content"] == "не работает почта в аутлуке"


def test_unreadable_screenshot_keeps_the_old_behaviour(client, people, screen):
    screen["text"] = None
    conversation_id = new_conversation(client)
    attachment = upload(client, conversation_id).json()

    state = send(client, conversation_id, attachment_ids=[attachment["id"]])

    assert "Файл получен" in state["messages"][-1]["content"]
    assert "screenshot_text" not in state["known_facts"]


def test_best_error_line_is_picked_from_noisy_text():
    text = "Файл Правка Вид\nОшибка входа: неверное имя пользователя или пароль\nОтмена ОК"
    assert ocr.error_line(text) == "Ошибка входа: неверное имя пользователя или пароль"


def test_a_line_with_an_error_code_is_preferred():
    text = "Подключение VPN\nНе удалось подключиться к удалённому серверу.\nОшибка 809: сетевое подключение прервано."
    assert ocr.error_line(text) == "Ошибка 809: сетевое подключение прервано."


def test_sympathy_comes_first_and_the_quote_has_one_full_stop(client, people, screen):
    screen["text"] = "Microsoft Outlook\nНет подключения к Microsoft Exchange."
    conversation_id = new_conversation(client)
    attachment = upload(client, conversation_id).json()

    reply = send(client, conversation_id, "да вы задолбали, опять почта не работает!!!",
                 [attachment["id"]])["messages"][-1]["content"]

    assert reply.startswith("Понимаю")
    assert "«Нет подключения к Microsoft Exchange»." in reply
