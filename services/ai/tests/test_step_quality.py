"""Steps are read by employees without IT knowledge: one action, a plain path, the expected
result. What needs admin rights or could break something goes to a specialist."""

from __future__ import annotations

import re

import pytest

from helpflow_ai import ConversationContext, DecisionAction, StepOutcome, StepRecord, TriageEngine
from helpflow_ai.knowledge import KnowledgeBase
from helpflow_ai.schemas import Playbook, Step

# Words an employee should not meet in a step: commands, system internals, admin tools.
# «Cmd» with a capital is the Mac key, not the command prompt.
JARGON = re.compile(r"\b(?:cmd|ipconfig|[Dd][Nn][Ss]|flushdns|regedit|[Рр]еестр\w*|трей|\.exe|[Пп]роцесс\w*)\b")
# A step says what should happen or what to do if it does not.
EXPECTED = re.compile(r"долж|появит|заработа|если\b|увидите|откроется|станет|загорит|пропад", re.I)

KB = KnowledgeBase.load()
USER_STEPS = [(pb.id, step) for pb in KB.playbooks for step in pb.steps if not step.requires_admin]


@pytest.mark.parametrize("playbook_id, step", USER_STEPS, ids=[f"{p}.{s.id}" for p, s in USER_STEPS])
def test_user_steps_have_no_jargon(playbook_id, step):
    assert not JARGON.search(f"{step.title} {step.instruction}"), step.instruction


@pytest.mark.parametrize("playbook_id, step", USER_STEPS, ids=[f"{p}.{s.id}" for p, s in USER_STEPS])
def test_user_steps_say_what_to_expect(playbook_id, step):
    assert EXPECTED.search(step.instruction), step.instruction


@pytest.mark.parametrize("playbook_id, step", USER_STEPS, ids=[f"{p}.{s.id}" for p, s in USER_STEPS])
def test_user_steps_are_short(playbook_id, step):
    assert len(step.instruction) <= 420, len(step.instruction)


def test_scenarios_with_steps_offer_a_workaround_where_one_exists():
    with_workaround = {pb.id for pb in KB.playbooks if any(s.workaround for s in pb.steps)}
    # CRM has none on purpose: «work from the phone» tells nothing to someone who said it works.
    assert {"network_wifi", "video_calls", "email_outlook", "printer", "vpn_connection"} <= with_workaround


def _kb_with(step: Step) -> KnowledgeBase:
    base = [pb for pb in KB.playbooks if pb.id != "printer"]
    printer = KB.get("printer").model_copy(update={"steps": [
        Step(id="safe", title="Проверьте бумагу", instruction="Если бумаги нет — доложите."), step]})
    return KnowledgeBase([*base, printer])


def test_admin_step_is_handed_to_a_specialist_not_shown():
    engine = TriageEngine(_kb_with(Step(id="reinstall_driver", title="Переустановите драйвер принтера",
                                        instruction="Удалите драйвер и установите заново.",
                                        requires_admin=True)))
    ctx = ConversationContext(original_request="принтер не печатает, висит в очереди", playbook_id="printer",
                              completed_steps=[StepRecord(step_id="safe", outcome=StepOutcome.NOT_HELPED)])

    decision = engine.decide(ctx)

    assert decision.action == DecisionAction.ESCALATE
    assert "Переустановите драйвер принтера" in decision.message
    assert "администратор" in decision.message
    assert "Переустановите драйвер принтера" in decision.reason


def test_when_only_a_workaround_is_left_the_specialist_gets_it_and_the_employee_gets_the_tip():
    engine = TriageEngine(KB)
    ctx = ConversationContext(
        original_request="принтер не печатает", playbook_id="printer",
        completed_steps=[StepRecord(step_id="check_printer_ready", outcome=StepOutcome.NOT_HELPED),
                         StepRecord(step_id="clear_print_queue", outcome=StepOutcome.NOT_HELPED)])

    decision = engine.decide(ctx)

    assert decision.action == DecisionAction.ESCALATE
    assert "другой принтер" in decision.message
    assert decision.message.index("Передаю") < decision.message.index("другой принтер")


def test_urgent_request_still_starts_with_the_workaround():
    engine = TriageEngine(KB)
    ctx = ConversationContext(original_request="принтер не печатает, срочно, через 10 минут встреча",
                              playbook_id="printer", urgency="high")

    decision = engine.decide(ctx)

    assert decision.action == DecisionAction.STEP and decision.step.id == "print_elsewhere"
