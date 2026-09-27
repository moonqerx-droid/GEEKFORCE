from types import SimpleNamespace

import pytest

from app.services.incident_detection import (
    IncidentFingerprint,
    build_fingerprint,
    recompute_signature,
    similarity,
)


def conversation(**overrides):
    values = {
        "service": "CRM",
        "summary": "Ошибка доступа в CRM",
        "symptoms": ["Сервис не открывается"],
        "known_facts": {"error_text": "HTTP 502"},
        "playbook_id": "service_unavailable",
        "messages": [SimpleNamespace(role="user", content="У всех не работает CRM")],
    }
    return SimpleNamespace(**(values | overrides))


def fingerprint(service, tokens):
    return IncidentFingerprint(service=service, weighted_tokens=tokens)


def test_fingerprint_normalizes_russian_and_preserves_codes():
    result = build_fingerprint(conversation())

    assert result is not None
    assert result.service == "crm"
    assert result.weighted_tokens["502"] == 3
    assert result.weighted_tokens["crm"] == 3
    assert "не" not in result.weighted_tokens


@pytest.mark.parametrize(
    ("service", "playbook"),
    [("Не определён", "unknown"), ("ИБ", "security_incident")],
)
def test_unknown_and_security_are_not_clusterable(service, playbook):
    assert build_fingerprint(conversation(service=service, playbook_id=playbook)) is None


def test_same_text_from_different_services_never_matches():
    crm = fingerprint("crm", {"502": 3, "недоступен": 2})
    mail = fingerprint("почта", {"502": 3, "недоступен": 2})

    assert similarity(crm, mail).score == 0.0
    assert similarity(crm, mail).evidence_tokens == []


def test_threshold_boundary_is_inclusive():
    left = fingerprint("crm", {"crm": 3, "502": 3, "вход": 2})
    exact = fingerprint("crm", {"crm": 3, "502": 3, "портал": 2})

    result = similarity(left, exact)

    assert result.score == pytest.approx(0.6)
    assert result.score >= 0.55
    assert result.evidence_tokens == ["502", "crm"]


def test_signature_keeps_service_codes_and_majority_tokens():
    fingerprints = [
        fingerprint("crm", {"crm": 3, "502": 3, "недоступен": 2, "офис": 1}),
        fingerprint("crm", {"crm": 3, "502": 3, "недоступен": 2, "дом": 1}),
        fingerprint("crm", {"crm": 3, "503": 3, "недоступен": 2, "дом": 1}),
    ]

    assert recompute_signature(fingerprints) == ["502", "503", "crm", "недоступен", "дом"]


def test_similarity_is_deterministic_across_repeated_calls():
    left = build_fingerprint(conversation())
    right = build_fingerprint(conversation(messages=[SimpleNamespace(
        role="user", content="CRM не открывается: HTTP 502"
    )]))
    assert left is not None and right is not None

    results = [similarity(left, right) for _ in range(10)]

    assert all(result == results[0] for result in results)


def test_filler_words_do_not_count_as_evidence():
    result = build_fingerprint(conversation(
        messages=[SimpleNamespace(role="user", content="Опять пишет ошибку, что делать, помогите пожалуйста")],
        known_facts={},
    ))

    assert {"опять", "пишет", "делать", "помогите", "пожалуйста"}.isdisjoint(result.weighted_tokens)
