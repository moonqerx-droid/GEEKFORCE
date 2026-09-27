"""Runs knowledge-base/test-cases/triage_cases.yaml against the rules engine."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CASES_FILE = Path(__file__).resolve().parents[3] / "knowledge-base" / "test-cases" / "triage_cases.yaml"
CASES = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_triage_case(case, engine, simulate):
    expect = case["expect"]
    result = engine.analyze(case["message"])

    assert result.recommended_playbook == expect["playbook"]
    if "service" in expect:
        assert result.service == expect["service"]
    if "urgency" in expect:
        assert result.urgency.value == expect["urgency"]
    if "urgency_reason_contains" in expect:
        assert expect["urgency_reason_contains"] in result.urgency_reason
    for symptom in expect.get("symptoms", []):
        assert symptom in result.symptoms
    for fact, value in expect.get("facts", {}).items():
        assert value.lower() in result.known_facts.get(fact, "").lower(), (fact, result.known_facts)
    for fact in expect.get("not_missing", []):
        assert fact not in result.missing_facts, "must not ask what the user already said"
    if "additional_issues" in expect:
        assert [i.playbook_id for i in result.additional_issues] == expect["additional_issues"]
    elif "questions_before_step" in expect:
        assert result.additional_issues == [], "one problem must not be split"
    if "should_escalate" in expect:
        assert result.should_escalate is expect["should_escalate"]
    if "questions_before_step" in expect:
        sim = simulate(case["message"])
        asked = 0
        while sim.decision.action.value == "ask":
            asked += 1
            sim.answer("не знаю")
        assert asked == expect["questions_before_step"]
        assert sim.decision.action.value == expect.get("action_after_questions", "step")


def test_analysis_never_repeats_known_facts(engine):
    result = engine.analyze("Не могу войти в CRM, VPN подключен, пишет «Сессия истекла»")
    assert result.known_facts["vpn"] == "yes"
    assert "vpn" not in result.missing_facts
    assert "error_text" not in result.missing_facts
    assert result.next_question is not None
    assert "VPN" not in result.next_question


def test_empty_message_is_rejected(engine):
    with pytest.raises(ValueError):
        engine.analyze("   ")


def test_all_results_are_valid_json_contract(engine):
    for case in CASES:
        data = engine.analyze(case["message"]).model_dump(mode="json")
        for key in ("summary", "service", "symptoms", "urgency", "urgency_reason", "known_facts",
                    "missing_facts", "next_question", "confidence", "recommended_playbook",
                    "should_escalate"):
            assert key in data
        assert 0.0 <= data["confidence"] <= 1.0
