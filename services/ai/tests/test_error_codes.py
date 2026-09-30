"""Error codes: the assistant recognises the code in any spelling, explains it in plain
words and works through that code's steps before the scenario's generic ones."""

from __future__ import annotations

import pytest

from helpflow_ai import ConversationContext, DecisionAction, StepOutcome, StepRecord, TriageEngine, rules


@pytest.mark.parametrize("text, codes", [
    ("проблема с впном, пишет ошибка 809", ["809"]),
    ("809 ошибка при подключении", ["809"]),
    ("впн не подключается, код 691", ["691"]),
    ("Outlook пишет 0x800ccc0e", ["0x800CCC0E"]),
    ("ошибка 80070005 при установке", ["0x80070005"]),
    ("принтер: ошибка 0x709", ["0x00000709"]),
    ("в хроме DNS_PROBE_FINISHED_NXDOMAIN", ["DNS_PROBE_FINISHED_NXDOMAIN"]),
    ("пишет net::err_cert_date_invalid", ["NET::ERR_CERT_DATE_INVALID"]),
    ("портал выдаёт 502 bad gateway", ["502", "BAD GATEWAY"]),
    ("Teams: код ошибки caa20002", ["0xCAA20002"]),
    ("zoom выдает ошибку 5003", ["5003"]),
])
def test_codes_are_found_in_any_spelling(text, codes):
    assert rules.extract_error_codes(text) == codes


@pytest.mark.parametrize("text", [
    "через 20 минут встреча, не работает почта",
    "сижу в 1603 кабинете, принтер не печатает",
    "не могу войти в 1с",
    "ошибка при входе уже 10 минут",
])
def test_numbers_that_are_not_codes_are_ignored(text):
    assert rules.extract_error_codes(text) == []


def test_the_base_knows_codes_and_their_other_spellings(kb):
    assert kb.error_code("809").playbook == "vpn_connection"
    assert kb.error_code("0x800CCC0F") is kb.error_code("0x800CCC0E")
    assert kb.error_code("12345") is None


@pytest.mark.parametrize("text, playbook", [
    ("пишет ошибка 809, ничего рабочего не открывается", "vpn_connection"),
    ("выскакивает 0x800CCC0E", "email_outlook"),
    ("при установке ошибка 1603", "app_not_starting"),
    ("код ошибки caa20002 при входе", "video_calls"),
])
def test_a_known_code_chooses_the_scenario(engine, text, playbook):
    assert engine.analyze(text).recommended_playbook == playbook


def test_a_generic_code_does_not_override_the_scenario(engine):
    analysis = engine.analyze("не могу войти в CRM с ноутбука, с телефона работает, ошибка 401")
    assert analysis.recommended_playbook == "crm_login_device_specific"


def test_a_code_leads_straight_to_its_steps_with_an_explanation(simulate):
    sim = simulate("проблема с впном, пишет ошибка 809")

    assert sim.decision.action == DecisionAction.STEP, "no generic questions: the code says what is wrong"
    assert sim.decision.step.id.startswith("code.809.")
    assert "Ошибка 809" in sim.decision.message and "не пропускает VPN" in sim.decision.message

    second = sim.step_result(StepOutcome.NOT_HELPED)
    assert second.step.id == "code.809.restart_router"
    assert "Ошибка 809" not in second.message, "the meaning is said once"

    third = sim.step_result(StepOutcome.NOT_HELPED)
    assert third.action == DecisionAction.ESCALATE
    assert "делает специалист" in third.message


def test_a_code_named_in_the_answer_is_used(simulate):
    sim = simulate("впн не подключается")
    assert sim.decision.action == DecisionAction.ASK and sim.decision.question.fact == "error_text"

    decision = sim.answer("691")

    assert decision.action == DecisionAction.STEP
    assert decision.step.id == "code.691.retype_credentials"


def test_a_code_with_admin_only_steps_is_handed_off_at_once_with_the_meaning(simulate):
    sim = simulate("впн пишет ошибка 812")

    assert sim.decision.action == DecisionAction.ESCALATE
    assert "Ошибка 812" in sim.decision.message and "нет права" in sim.decision.message.lower()


def test_escalate_after_steps_skips_the_generic_steps(simulate):
    sim = simulate("outlook ошибка 0x8004010F")
    assert sim.decision.step.id.startswith("code.0x8004010F.")

    decision = sim.step_result(StepOutcome.NOT_HELPED)

    assert decision.action == DecisionAction.ESCALATE


def test_an_unknown_code_keeps_the_usual_flow_and_is_noted(simulate):
    sim = simulate("впн не подключается, ошибка 12345")

    assert sim.analysis.known_facts["error_code"] == "12345"
    assert not (sim.decision.step and sim.decision.step.id.startswith("code."))


def test_the_card_explains_the_code(engine):
    ctx = ConversationContext(
        original_request="проблема с впном, пишет ошибка 809", playbook_id="vpn_connection",
        known_facts={"error_code": "809"},
        completed_steps=[StepRecord(step_id="code.809.hotspot", outcome=StepOutcome.NOT_HELPED)],
    )

    card = engine.build_escalation_card(ctx, "выполнено шагов: 1, проблема не решена")

    assert "Код ошибки — 809: Сеть не пропускает VPN" in card.ai_summary
    assert "ошибка 809" in card.summary.lower()


def test_code_steps_follow_the_step_rules(kb):
    steps = [s for pb in kb.playbooks for s in pb.steps if s.id.startswith("code.")]
    assert len(steps) >= 25
    assert all(s.when.get("error_code") for s in steps)


@pytest.mark.parametrize("text, starts", [
    ("впн не подключается, код 691", "Ошибка 691: VPN не принимает"),
    ("outlook выдаёт ошибку 0x800CCC0E", "Ошибка 0x800CCC0E: Outlook не может"),
    ("принтер пишет ошибка 0x00000709", "Ошибка 0x00000709: Windows не может"),
    ("проблема с впном, пишет ошибка 809", "Ошибка 809: сеть не пропускает"),
])
def test_names_and_abbreviations_keep_their_case(simulate, text, starts):
    assert simulate(text).decision.message.startswith(starts)
