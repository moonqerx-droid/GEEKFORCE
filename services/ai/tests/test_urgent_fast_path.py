"""An urgent request gets a quick way round first and, if two tries fail, a specialist at once —
not the whole diagnosis while a meeting is starting."""

from __future__ import annotations

from helpflow_ai import DecisionAction, StepOutcome

URGENT = "не подключается VPN, а через 10 минут встреча с клиентом, срочно!"
CALM = "не подключается VPN"


def answer_questions(sim):
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("нет" if sim.decision.question.fact != "internet_works" else "да")


def play_steps(sim, failures):
    answer_questions(sim)
    decisions = [sim.decision]
    for _ in range(failures):
        if sim.decision.action != DecisionAction.STEP:
            break
        sim.step_result(StepOutcome.NOT_HELPED)
        answer_questions(sim)
        decisions.append(sim.decision)
    return decisions


def test_urgent_goes_to_a_specialist_after_two_failed_steps(simulate):
    decisions = play_steps(simulate(URGENT), 2)

    assert [d.action for d in decisions] == [DecisionAction.STEP, DecisionAction.STEP, DecisionAction.ESCALATE]
    assert decisions[0].step.workaround, "the quickest way round comes first"
    assert "срочн" in decisions[-1].reason


def test_not_urgent_keeps_the_full_diagnosis(simulate):
    decisions = play_steps(simulate(CALM), 2)

    assert decisions[-1].action == DecisionAction.STEP


def test_a_helpful_workaround_keeps_working_on_the_cause(simulate):
    sim = simulate(URGENT)
    play_steps(sim, 0)

    after = sim.step_result(StepOutcome.HELPED)

    assert after.action in (DecisionAction.ASK, DecisionAction.STEP), "unblocked: now the cause, calmly"
