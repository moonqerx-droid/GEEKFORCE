"""Interactive console demo: python -m helpflow_ai"""

from __future__ import annotations

import json
import sys

from . import ConversationContext, DecisionAction, StepOutcome, StepRecord, TriageEngine

OUTCOMES = {"1": StepOutcome.HELPED, "2": StepOutcome.NOT_HELPED, "3": StepOutcome.CANNOT_DO}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = TriageEngine.from_env()
    print(f"HelpFlow AI ({'LLM ' + engine.llm.model if engine.llm else 'rules only'}). Пустая строка — выход.")
    message = input("\nОпишите проблему: ").strip()
    if not message:
        return
    analysis = engine.analyze(message)
    print(json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2))
    ctx = ConversationContext(
        original_request=message,
        known_facts=analysis.known_facts,
        playbook_id=analysis.recommended_playbook,
        urgency=analysis.urgency,
    )
    while True:
        decision = engine.decide(ctx)
        print(f"\n[{decision.action.value}] {decision.message}")
        if decision.action == DecisionAction.ESCALATE:
            card = engine.build_escalation_card(ctx, decision.reason)
            print(json.dumps(card.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return
        if decision.action == DecisionAction.ASK:
            ctx = ctx.model_copy(update={"asked_facts": [*ctx.asked_facts, decision.question.fact]})
            reply = input("> ").strip()
            if not reply:
                return
            ctx = ctx.model_copy(update={"known_facts": {**ctx.known_facts, **engine.absorb_answer(reply, ctx)}})
        elif decision.action == DecisionAction.STEP:
            choice = input("1 — помогло, 2 — не помогло, 3 — не могу выполнить > ").strip()
            if choice not in OUTCOMES:
                return
            record = StepRecord(step_id=decision.step.id, outcome=OUTCOMES[choice])
            ctx = ctx.model_copy(update={"completed_steps": [*ctx.completed_steps, record],
                                         "verification_failed": False})
        else:  # VERIFY
            if engine.interpret_confirmation(input("> ")):
                print("\nОбращение закрыто. Рады, что всё работает!")
                return
            ctx = ctx.model_copy(update={"verification_failed": True})


if __name__ == "__main__":
    main()
