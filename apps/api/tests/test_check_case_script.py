"""The jury smoke script must fail closed on an unexpected dialogue action."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[3] / "scripts" / "check-case.py"


def load_script():
    spec = importlib.util.spec_from_file_location("helpflow_check_case", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_catalog_contains_every_required_jury_scenario():
    module = load_script()

    names = {case.slug for case in module.CASES}

    assert names == {
        "case-example",
        "simple-password",
        "ambiguous",
        "multiple-symptoms",
        "access-request",
        "urgent-teams",
        "outlook-how-to",
        "company-policy",
        "phishing",
    }


def test_validate_case_reports_each_contract_mismatch():
    module = load_script()
    case = module.Case(
        slug="probe",
        title="Probe",
        message="test",
        statuses=("ESCALATED",),
        answer_kinds=("handoff",),
        playbooks=("security_incident",),
        urgency="critical",
        assistant_contains=("отключ",),
    )
    state = {
        "status": "CLARIFYING",
        "answer_kind": "playbook",
        "playbook_id": "unknown",
        "urgency": "normal",
        "messages": [{"role": "assistant", "content": "Уточните вопрос"}],
    }

    errors = module.validate_case(case, state)

    assert len(errors) == 5
    assert any("status" in error for error in errors)
    assert any("answer_kind" in error for error in errors)
    assert any("playbook" in error for error in errors)
    assert any("urgency" in error for error in errors)
    assert any("ответ" in error for error in errors)


def test_validate_case_accepts_multi_issue_first_action():
    module = load_script()
    case = next(case for case in module.CASES if case.slug == "multiple-symptoms")
    state = {
        "status": "CLARIFYING",
        "answer_kind": "playbook",
        "playbook_id": "network_wifi",
        "urgency": "normal",
        "messages": [{
            "role": "assistant",
            "content": "Вижу сразу несколько проблем: Outlook и Zoom. Начнём с интернета, остальное разберём следом.",
        }],
    }

    assert module.validate_case(case, state) == []


def test_document_probe_requires_a_document_answer_and_citation():
    module = load_script()
    state = {
        "status": "TROUBLESHOOTING",
        "answer_kind": "document",
        "playbook_id": "vpn_connection",
        "urgency": "normal",
        "messages": [{
            "role": "assistant",
            "content": "По документу «VPN»: используйте Континент.",
            "answer_kind": "document",
            "citations": [{"source_id": "document:vpn:0", "title": "VPN", "quote": "используйте Континент"}],
        }],
    }

    assert module.validate_document_probe(state) == []
    state["messages"][-1]["citations"] = []
    assert module.validate_document_probe(state) == ["нет цитаты корпоративного документа"]
