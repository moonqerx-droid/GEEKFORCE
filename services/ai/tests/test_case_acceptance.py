"""Acceptance tests for the five request types the jury checks.

Principle under test: the user never answers a question that is not needed to
pick the next step, and never repeats what the first message already said.
"""

from __future__ import annotations

import pytest

from helpflow_ai import DecisionAction, StepOutcome

CASE_EXAMPLE = ("У меня опять всё сломалось. Вчера всё работало, сегодня не могу зайти в рабочую систему. "
                "Через телефон открывается, с ноутбука нет. Мне через 20 минут на встречу")


def first_question_facts(sim) -> list[str]:
    facts = []
    while sim.decision.action == DecisionAction.ASK:
        facts.append(sim.decision.question.fact)
        sim.answer("не знаю")
    return facts


# --- unsolvable by the user: new access ------------------------------------

ACCESS = "Нужен доступ к папке бухгалтерии на общем диске"


def test_access_request_extracts_named_resource(engine):
    analysis = engine.analyze(ACCESS)
    assert analysis.recommended_playbook == "access_rights"
    assert "бухгалтерии" in analysis.known_facts["resource"]
    assert "resource" not in analysis.missing_facts


def test_new_access_goes_to_admins_without_questions(simulate, engine):
    sim = simulate(ACCESS)
    assert sim.decision.action == DecisionAction.ESCALATE
    assert sim.decision.escalation_team == "Администраторы доступа"
    assert "папке бухгалтерии" in sim.decision.message

    card = engine.build_escalation_card(sim.ctx, sim.decision.reason)
    assert "бухгалтерии" in card.known_facts["resource"]
    assert card.questions_and_answers == []


@pytest.mark.parametrize("message, resource", [
    ("Дайте доступ в 1С, я новый сотрудник", "1С"),
    ("пожалуйста откройте доступ к шаре Marketing, горит отчёт!!", "шаре Marketing"),
    ("нужен доступ в джиру к проекту SALES", "джиру к проекту SALES"),
])
def test_access_variations_do_not_ask_for_named_resource(simulate, message, resource):
    sim = simulate(message)
    assert sim.analysis.recommended_playbook == "access_rights"
    assert resource.lower() in sim.ctx.known_facts["resource"].lower()
    assert "resource" not in first_question_facts(sim)


def test_lost_access_still_troubleshoots(simulate):
    sim = simulate("Пропал доступ к папке отдела на общем диске, пишет доступ запрещён")
    assert sim.analysis.recommended_playbook == "access_rights"
    assert "resource" not in first_question_facts(sim)
    assert sim.decision.action == DecisionAction.STEP
