from __future__ import annotations

from helpflow_ai import ConversationContext, DecisionAction, StepOutcome, StepRecord, TriageEngine

from test_llm import fake_llm


def test_unknown_low_risk_question_gets_fast_general_guidance(kb) -> None:
    calls: list = []
    engine = TriageEngine(kb, fake_llm([], calls))

    decision = engine.decide(ConversationContext(
        original_request="Как очистить кэш браузера?",
        playbook_id="unknown",
    ))

    assert decision.action == DecisionAction.STEP
    assert decision.step is not None
    assert decision.step.id == "general.browser_cache"
    assert decision.message.startswith("Общая рекомендация — не правило компании.")
    assert "сохраните" in decision.message.casefold()
    assert calls == []


def test_general_guidance_that_did_not_help_escalates(kb) -> None:
    decision = TriageEngine(kb).decide(ConversationContext(
        original_request="Как очистить кэш браузера?",
        playbook_id="unknown",
        completed_steps=[StepRecord(
            step_id="general.browser_cache",
            outcome=StepOutcome.NOT_HELPED,
        )],
    ))

    assert decision.action == DecisionAction.ESCALATE
    assert decision.escalation_team == "Service Desk L1"
    assert "общий совет не помог" in decision.reason


def test_general_guidance_that_helped_is_verified(kb) -> None:
    decision = TriageEngine(kb).decide(ConversationContext(
        original_request="Как очистить кэш браузера?",
        playbook_id="unknown",
        completed_steps=[StepRecord(
            step_id="general.browser_cache",
            outcome=StepOutcome.HELPED,
        )],
    ))

    assert decision.action == DecisionAction.VERIFY
    assert "проблема решена" in decision.message.casefold()


def test_company_policy_without_source_skips_diagnostic_questions(kb) -> None:
    decision = TriageEngine(kb).decide(ConversationContext(
        original_request="Сколько дней отпуска мне положено?",
        playbook_id="unknown",
    ))

    assert decision.action == DecisionAction.ESCALATE
    assert "нет подтверждённого источника" in decision.reason


def test_access_request_without_source_goes_directly_to_operator(kb) -> None:
    decision = TriageEngine(kb).decide(ConversationContext(
        original_request="Выдай мне права администратора в CRM",
        playbook_id="unknown",
    ))

    assert decision.action == DecisionAction.ESCALATE
    assert "нет подтверждённого источника" in decision.reason
