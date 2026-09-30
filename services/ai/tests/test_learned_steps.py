"""What helped colleagues, approved by the support lead, is offered before a hand-off."""

from helpflow_ai import ConversationContext, DecisionAction, StepRecord, TriageEngine


def _after_all_printer_steps(kb, extra=()):
    printer = kb.get("printer")
    facts = {question.fact: "не знаю" for question in printer.questions}
    done = [StepRecord(step_id=step.id, outcome="not_helped") for step in printer.steps]
    return ConversationContext(
        original_request="принтер не печатает", playbook_id="printer", known_facts=facts,
        asked_facts=list(facts), completed_steps=[*done, *extra], urgency="medium",
        messages=[{"role": "user", "content": "принтер не печатает"}],
    )


def test_an_approved_solution_comes_before_the_hand_off(kb):
    engine = TriageEngine(kb)
    assert engine.decide(_after_all_printer_steps(kb)).action == DecisionAction.ESCALATE

    engine.set_learned_steps([{"id": "s1", "playbook_id": "printer",
                               "instruction": "Выключите принтер на минуту и удалите задание из очереди печати."}])
    decision = engine.decide(_after_all_printer_steps(kb))
    assert decision.action == DecisionAction.STEP
    assert decision.step.id == "learned.s1"
    assert "Решение, которое помогло коллегам" in decision.message

    tried = engine.decide(_after_all_printer_steps(kb, [StepRecord(step_id="learned.s1", outcome="not_helped")]))
    assert tried.action == DecisionAction.ESCALATE


def test_a_solution_for_another_scenario_is_not_offered(kb):
    engine = TriageEngine(kb)
    engine.set_learned_steps([{"id": "s2", "playbook_id": "vpn_connection", "instruction": "Обновите сертификат."}])
    assert engine.decide(_after_all_printer_steps(kb)).action == DecisionAction.ESCALATE
