"""The six mandatory scenarios from PROJECT_PLAN.md (stage 3), driven end to end."""

from __future__ import annotations

from helpflow_ai import ConversationContext, DecisionAction, StepOutcome

DEMO = "Не могу войти в CRM с ноутбука, но с телефона работает. Через 20 минут встреча."


def test_demo_vertical_slice(simulate):
    sim = simulate(DEMO)
    # urgent -> exactly one clarifying question
    assert sim.decision.action == DecisionAction.ASK
    assert sim.decision.question.fact == "error_text"

    first = sim.answer("Пишет: ошибка соединения")
    assert first.action == DecisionAction.STEP
    assert sim.ctx.known_facts["error_text"] == "ошибка соединения"

    second = sim.step_result(StepOutcome.NOT_HELPED)
    assert second.action == DecisionAction.STEP
    assert second.step.id != first.step.id

    verify = sim.step_result(StepOutcome.HELPED)
    assert verify.action == DecisionAction.VERIFY
    assert sim.verify("Да, доступ восстановился") is True


CASE_EXAMPLE = ("У меня опять всё сломалось. Вчера всё работало, сегодня не могу зайти в рабочую систему. "
                "Через телефон открывается, с ноутбука нет. Мне через 20 минут на встречу")


def test_case_example_full_path_to_specialist(simulate, engine):
    sim = simulate(CASE_EXAMPLE)
    assert sim.decision.action == DecisionAction.ASK  # one question: urgent
    sim.answer("просто крутится загрузка и ничего")
    assert sim.decision.action == DecisionAction.STEP
    while sim.decision.action == DecisionAction.STEP:
        sim.step_result(StepOutcome.NOT_HELPED)
    assert sim.decision.action == DecisionAction.ESCALATE

    card = engine.build_escalation_card(sim.ctx, sim.decision.reason)
    assert card.original_request == CASE_EXAMPLE
    assert card.urgency.value == "high" and "20 минут" in card.urgency_reason
    assert card.known_facts["other_device_works"] == "yes"
    assert card.known_facts["error_text"] == "просто крутится загрузка и ничего"
    assert card.questions_and_answers[0]["answer"] == "просто крутится загрузка и ничего"
    assert len(card.performed_steps) >= 3
    assert "не решена" in card.current_result


def test_simple_problem_starts_solving_quickly(simulate):
    sim = simulate("Забыл пароль, пишет «неверный пароль», пароль не менял")
    asked = 0
    while sim.decision.action == DecisionAction.ASK:
        asked += 1
        sim.answer("нет")
    assert asked <= 1
    assert sim.decision.action == DecisionAction.STEP


def test_ambiguous_request_asks_at_most_three_questions(simulate):
    sim = simulate("Всё сломалось, ничего не получается")
    questions = []
    while sim.decision.action == DecisionAction.ASK:
        questions.append(sim.decision.question.fact)
        sim.answer("не знаю")
    assert 1 <= len(questions) <= 3
    assert len(questions) == len(set(questions)), "questions must not repeat"
    assert sim.decision.action == DecisionAction.STEP


def test_answer_changes_next_step(simulate):
    without_vpn = simulate("Не открывается CRM, пишет «Сервер не найден»")
    while without_vpn.decision.action == DecisionAction.ASK:
        without_vpn.answer("нет")
    with_vpn = simulate("Не открывается CRM, пишет «Сервер не найден»")
    while with_vpn.decision.action == DecisionAction.ASK:
        with_vpn.answer("да")
    assert without_vpn.decision.step.id == "connect_vpn"
    assert with_vpn.decision.step.id != "connect_vpn"


def test_unsolvable_problem_escalates_with_full_context(simulate, engine):
    sim = simulate("Меня не слышат в Teams")
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("да")
    steps = 0
    while sim.decision.action == DecisionAction.STEP:
        steps += 1
        sim.step_result(StepOutcome.NOT_HELPED if steps % 2 else StepOutcome.CANNOT_DO)
    assert sim.decision.action == DecisionAction.ESCALATE
    assert steps >= 3

    card = engine.build_escalation_card(sim.ctx, sim.decision.reason)
    assert card.original_request == "Меня не слышат в Teams"
    assert card.service == "Видеосвязь"
    assert len(card.performed_steps) == steps
    assert {s["result"] for s in card.performed_steps} == {"не помогло", "не удалось выполнить"}
    assert card.questions_and_answers and card.questions_and_answers[0]["answer"]
    assert card.recommended_team
    assert card.current_result.startswith(f"Проблема не решена после {steps}")
    assert "Выполнено" in card.ai_summary and card.source == "rules"


def test_urgent_request_has_shorter_path(simulate):
    calm = simulate("Не могу войти в CRM")
    urgent = simulate("Срочно! Не могу войти в CRM, клиент ждет")
    count = {}
    for name, sim in (("calm", calm), ("urgent", urgent)):
        count[name] = 0
        while sim.decision.action == DecisionAction.ASK:
            count[name] += 1
            sim.answer("не знаю")
    assert urgent.analysis.urgency.value in ("high", "critical")
    assert count["urgent"] < count["calm"]


def test_mass_incident_escalates_without_diagnostics(simulate):
    sim = simulate("CRM не открывается ни у кого в отделе, у коллег тоже ошибка 502")
    assert sim.analysis.recommended_playbook == "mass_incident"
    assert sim.analysis.service == "CRM"
    assert sim.analysis.should_escalate is True
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("весь отдел")
    assert sim.decision.action == DecisionAction.ESCALATE
    assert sim.ctx.known_facts["affected_scope"] == "department"


def test_security_incident_shows_safety_notice(simulate):
    sim = simulate("Кажется словил вирус, файлы зашифрованы")
    while sim.decision.action == DecisionAction.ASK:
        sim.answer("нет")
    assert sim.decision.action == DecisionAction.ESCALATE
    assert "Отключите компьютер от сети" in sim.decision.message


def test_failed_verification_continues_troubleshooting(simulate):
    sim = simulate(DEMO)
    sim.answer("не знаю")
    first = sim.decision.step.id
    sim.step_result(StepOutcome.HELPED)
    assert sim.verify("Нет, всё ещё не пускает") is False
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id != first


def test_decide_is_pure_for_same_context(engine):
    ctx = ConversationContext(original_request=DEMO, playbook_id="crm_login_device_specific")
    assert engine.decide(ctx) == engine.decide(ctx)
