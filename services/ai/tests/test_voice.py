"""The assistant speaks the employee's language."""

from __future__ import annotations

import pytest

from helpflow_ai import ConversationContext, StepOutcome, StepRecord, voice


@pytest.mark.parametrize("team, phrase", [
    ("Service Desk L1 (оргтехника)", "специалисту по оргтехнике"),
    ("Отдел информационной безопасности", "в отдел информационной безопасности"),
    ("Администраторы доступа", "администраторам доступа"),
    ("Какая-то новая команда", "специалисту поддержки"),
])
def test_teams_are_named_for_people(team, phrase):
    assert voice.to_whom(team) == phrase


@pytest.mark.parametrize("text, expected", [
    ("да вы задолбали, ничего не работает!!!", "Понимаю"),
    ("ОПЯТЬ НЕ РАБОТАЕТ ПОЧТА СРОЧНО", "Понимаю"),
    ("снова отвалился впн", "повторяется"),
    ("принтер не печатает", ""),
    ("не работает почта, пишет ошибку", ""),
])
def test_one_short_acknowledgement_only_when_it_helps(text, expected):
    said = voice.acknowledgement(text)
    assert (expected in said) if expected else said == ""


def test_hand_off_never_shows_internal_team_codes(engine):
    steps = [StepRecord(step_id="check_printer_ready", outcome=StepOutcome.NOT_HELPED),
             StepRecord(step_id="clear_print_queue", outcome=StepOutcome.NOT_HELPED)]
    decision = engine.decide(ConversationContext(
        original_request="принтер не печатает", playbook_id="printer", completed_steps=steps,
    ))
    assert decision.action.value == "escalate"
    assert "Service Desk" not in decision.message
    assert "специалисту по оргтехнике" in decision.message
