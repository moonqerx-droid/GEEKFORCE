"""The hand-off card: a specialist understands it in ten seconds and asks nothing again."""

from __future__ import annotations

import re

from helpflow_ai import ConversationContext, StepOutcome, StepRecord

RAW = re.compile(r"\b(?:[a-z]+_[a-z_]+|unknown|yes|no|medium|high|critical|other|laptop|desktop)\b")


def test_summary_is_plain_russian_with_the_employees_words(engine):
    ctx = ConversationContext(
        original_request="Не могу войти в CRM с ноутбука, но с телефона работает. Через 20 минут встреча.",
        playbook_id="crm_login_device_specific", urgency="high",
        known_facts={"other_device_works": "yes", "device": "laptop", "vpn": "no", "error_text": "ошибка соединения"},
        asked_facts=["error_text", "vpn"],
        completed_steps=[StepRecord(step_id="connect_vpn", outcome=StepOutcome.NOT_HELPED),
                         StepRecord(step_id="clear_crm_cookies", outcome=StepOutcome.NOT_HELPED)],
    )

    card = engine.build_escalation_card(ctx, "выполнено шагов: 2, проблема не решена")
    text = card.ai_summary

    assert not RAW.search(text), text
    assert "«Не могу войти в CRM с ноутбука" in text
    assert "Срочность: высокая" in text
    assert "С другого устройства работает — да" in text
    assert "VPN подключён — нет" in text
    assert "Пробовали: Подключитесь к VPN — не помогло; Удалите сохранённые данные сайта системы — не помогло" in text
    assert "Текущий результат" not in text
    assert len(text) <= 700


def test_answers_in_the_card_are_words_not_codes(engine):
    ctx = ConversationContext(original_request="странная штука с компьютером", playbook_id="unknown",
                              known_facts={"problem_area": "other", "details": "пищит и чёрный экран"},
                              asked_facts=["problem_area", "details"])

    card = engine.build_escalation_card(ctx, "не найден подтверждённый сценарий в базе знаний")

    assert [qa["answer"] for qa in card.questions_and_answers] == ["Другое", "пищит и чёрный экран"]
    assert "Сервис: Не определён" not in card.ai_summary
    assert not RAW.search(card.ai_summary), card.ai_summary


def test_dont_know_reads_as_such(engine):
    ctx = ConversationContext(original_request="что-то не так", playbook_id="unknown",
                              known_facts={"problem_area": "unknown"}, asked_facts=["problem_area"])

    card = engine.build_escalation_card(ctx, "не найден подтверждённый сценарий в базе знаний")

    assert card.questions_and_answers[0]["answer"] == "не знает"
    assert "не знает" in card.ai_summary


def test_failed_verification_is_spelled_out(engine):
    ctx = ConversationContext(original_request="забыл пароль", playbook_id="password_login",
                              completed_steps=[StepRecord(step_id="self_service_reset", outcome=StepOutcome.HELPED)],
                              verification_failed=True)

    text = engine.build_escalation_card(ctx, "выполнено шагов: 1, проблема не решена").ai_summary

    assert "при проверке сотрудник ответил, что проблема осталась" in text


def test_no_steps_at_all_is_not_called_zero_steps(engine, simulate):
    sim = simulate("1с очень медленно работает")
    sim.answer("да, у всех так")

    assert sim.decision.action.value == "escalate"
    assert "0" not in sim.decision.reason


def test_they_cannot_hear_me_is_not_i_cannot_hear_them(kb):
    from helpflow_ai import rules

    calls = kb.get("video_calls")
    assert rules.detect_symptoms("Меня не слышат в Teams", calls) == ["собеседники не слышат"]
    assert rules.detect_symptoms("не слышу собеседника в зуме", calls) == ["не слышно собеседников"]
    assert rules.detect_symptoms("на созвоне нет звука", calls) == ["не слышно собеседников"]


def test_title_taken_from_the_request_is_not_quoted_twice(engine):
    ctx = ConversationContext(original_request="странная штука с компьютером", playbook_id="unknown",
                              known_facts={"problem_area": "other"}, asked_facts=["problem_area"])

    text = engine.build_escalation_card(ctx, "не найден подтверждённый сценарий в базе знаний").ai_summary

    assert text.lower().count("странная штука с компьютером") == 1


def test_reason_does_not_repeat_the_steps(engine):
    ctx = ConversationContext(original_request="принтер не печатает", playbook_id="printer",
                              completed_steps=[StepRecord(step_id="check_printer_ready", outcome=StepOutcome.NOT_HELPED)])

    text = engine.build_escalation_card(ctx, "выполнено шагов: 1, проблема не решена").ai_summary

    assert "Почему передано: шаги не помогли." in text
