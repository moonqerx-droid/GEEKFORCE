import pytest

from app.repositories.conversations import ConversationRepository
from app.services.ai import MockAIService
from app.services.dialogue import DialogueConflict, DialogueService


@pytest.fixture
def mock_ai():
    return MockAIService()


@pytest.fixture
def dialogue(db_session, mock_ai):
    return DialogueService(ConversationRepository(db_session), mock_ai)


def test_mock_ai_detects_urgent_crm_request(mock_ai):
    result = mock_ai.analyze("Не могу войти в CRM с ноутбука. Через 20 минут встреча")

    assert result.service == "CRM"
    assert result.urgency == "high"
    assert result.recommended_playbook == "crm_login_device_specific"


def test_mock_ai_returns_generic_fallback(mock_ai):
    result = mock_ai.analyze("У меня всё сломалось")

    assert result.service == "Не определён"
    assert result.missing_facts == ["затронутый сервис", "наблюдаемый симптом"]
    assert result.recommended_playbook == "generic_clarification"


def test_mock_ai_rejects_blank_input(mock_ai):
    with pytest.raises(ValueError, match="blank"):
        mock_ai.analyze("   ")


def test_unsuccessful_step_selects_next_step(dialogue):
    conversation = dialogue.create_conversation()
    dialogue.handle_message(
        conversation.id,
        "Не могу войти в CRM с ноутбука, встреча через 20 минут",
    )
    dialogue.handle_message(conversation.id, "Ошибка соединения")

    updated = dialogue.record_step_result(conversation.id, "not_helped")

    assert updated.status == "TROUBLESHOOTING"
    assert len(updated.steps) == 1
    assert updated.current_step_code == "try_private_window"


def test_helped_step_requires_confirmation_before_resolution(dialogue):
    conversation = dialogue.create_conversation()
    dialogue.handle_message(conversation.id, "Не работает CRM")
    dialogue.handle_message(conversation.id, "Ошибка соединения")

    verifying = dialogue.record_step_result(conversation.id, "helped")
    assert verifying.status == "VERIFYING"

    resolved = dialogue.handle_message(conversation.id, "Да, доступ восстановился")

    assert resolved.status == "RESOLVED"


def test_uncertain_verification_reply_keeps_verifying(dialogue):
    conversation = dialogue.create_conversation()
    dialogue.handle_message(conversation.id, "Не работает CRM")
    dialogue.handle_message(conversation.id, "Ошибка соединения")
    dialogue.record_step_result(conversation.id, "helped")

    updated = dialogue.handle_message(conversation.id, "Не знаю, сейчас проверю")

    assert updated.status == "VERIFYING"
    assert "да или нет" in updated.messages[-1].content.casefold()


def test_negative_verification_reply_continues_troubleshooting(dialogue):
    conversation = dialogue.create_conversation()
    dialogue.handle_message(conversation.id, "Не работает CRM")
    dialogue.handle_message(conversation.id, "Ошибка соединения")
    dialogue.record_step_result(conversation.id, "helped")

    updated = dialogue.handle_message(conversation.id, "Ошибка осталась")

    assert updated.status == "TROUBLESHOOTING"
    assert updated.current_step_code == "clear_site_data"


def test_step_result_in_wrong_state_raises_conflict(dialogue):
    conversation = dialogue.create_conversation()

    with pytest.raises(DialogueConflict):
        dialogue.record_step_result(conversation.id, "not_helped")


def test_escalation_is_idempotent(dialogue):
    conversation = dialogue.create_conversation()
    dialogue.handle_message(conversation.id, "Не работает CRM")

    first = dialogue.escalate(conversation.id)
    second = dialogue.escalate(conversation.id)

    assert first.status == "ESCALATED"
    assert second.status == "ESCALATED"
    assert first.escalation_summary == second.escalation_summary


def test_repeated_failures_advance_then_escalate(dialogue):
    conversation = dialogue.create_conversation()
    dialogue.handle_message(conversation.id, "Не работает CRM")
    dialogue.handle_message(conversation.id, "Ошибка соединения")

    second_step = dialogue.record_step_result(conversation.id, "not_helped")
    assert second_step.current_step_code == "try_private_window"

    third_step = dialogue.record_step_result(conversation.id, "not_helped")
    assert third_step.current_step_code == "clear_site_data"

    escalated = dialogue.record_step_result(conversation.id, "not_helped")

    assert escalated.status == "ESCALATED"


def test_generic_problem_does_not_receive_crm_instructions(dialogue):
    conversation = dialogue.create_conversation()
    dialogue.handle_message(conversation.id, "У меня всё сломалось")

    updated = dialogue.handle_message(conversation.id, "Не печатает офисный принтер")

    assert updated.status == "ESCALATED"
    assert all("CRM" not in message.content for message in updated.messages)
