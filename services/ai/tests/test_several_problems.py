"""Two problems in one request: both are worked through, none is lost at a hand-off."""

from __future__ import annotations

from helpflow_ai import DecisionAction, StepOutcome


def test_the_second_problem_follows_without_a_confusing_check(simulate):
    sim = simulate("принтер не печатает и не приходят письма")
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("в браузере" if sim.decision.question.fact == "mail_client" else "нет")
    first = sim.decision.playbook_id
    assert sim.decision.action == DecisionAction.STEP

    after = sim.step_result(StepOutcome.HELPED)

    assert after.playbook_id != first, "straight on to the other problem"
    assert "Переходим ко второй проблеме" in after.message
    assert "Сейчас с этим всё в порядке" not in after.message


def test_a_problem_for_a_specialist_does_not_stop_the_other_one(simulate, engine):
    sim = simulate("нужен доступ к папке отдела на общем диске, и ещё принтер не печатает")

    assert sim.decision.action in (DecisionAction.ASK, DecisionAction.STEP)
    assert sim.decision.playbook_id == "printer"
    assert "специалист" in sim.decision.message and "принтер" in sim.decision.message.lower()
    assert "Начнём с первой" not in sim.decision.message
    assert sim.ctx.known_facts.get("handoff.access_rights")

    while sim.decision.action == DecisionAction.ASK:
        sim.answer("ничего не пишет")
    final = sim.step_result(StepOutcome.HELPED)

    assert final.action == DecisionAction.ESCALATE, "the access request still reaches the admins"
    assert "доступ" in final.message.lower()
    card = engine.build_escalation_card(sim.ctx, final.reason)
    statuses = {issue.playbook_id: issue.status for issue in card.issues}
    assert statuses == {"access_rights": "handed_off", "printer": "resolved"}
    assert "передано специалисту" in card.ai_summary


def test_two_problems_for_a_specialist_make_one_hand_off(simulate):
    sim = simulate("нужен доступ к папке отдела, и ещё нужно установить visio")
    while sim.decision.action == DecisionAction.STEP:
        sim.step_result(StepOutcome.NOT_HELPED)

    assert sim.decision.action == DecisionAction.ESCALATE
    assert "visio" in sim.decision.message.lower() or "установ" in sim.decision.message.lower()


def test_a_root_cause_still_asks_whether_the_rest_went_away(simulate):
    sim = simulate("интернет постоянно отваливается и outlook не синхронизируется")
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("в офисе" if sim.decision.question.fact == "location" else "да")
    assert sim.decision.playbook_id == "network_wifi"

    check = sim.step_result(StepOutcome.HELPED)

    assert check.action == DecisionAction.ASK
    assert "outlook" in check.message.lower() and "само" in check.message


import pytest

from helpflow_ai import rules


@pytest.mark.parametrize("text, expected", [
    ("нужен доступ к папке отдела на общем диске, и ещё принтер не печатает", {"access_rights", "printer"}),
    ("принтер не печатает, а ещё нужно установить visio", {"printer", "software_install"}),
    ("дайте доступ к crm и почта не приходит", {"access_rights", "email_outlook"}),
    ("не работает впн и не открывается почта", {"vpn_connection", "email_outlook"}),
])
def test_a_request_is_a_problem_too(kb, text, expected):
    best = rules.classify(text, kb.playbooks).playbook_id
    found = {pid for pid, _ in rules.plan_issues(text, kb.playbooks, best)}
    assert found == expected


def test_when_both_need_a_specialist_the_final_message_names_both(simulate):
    sim = simulate("принтер не печатает, а ещё нужно установить visio")
    while sim.decision.action == DecisionAction.STEP:
        sim.step_result(StepOutcome.NOT_HELPED)

    assert sim.decision.action == DecisionAction.ESCALATE
    assert "visio" in sim.decision.message.lower() and "принтер" in sim.decision.message.lower()
