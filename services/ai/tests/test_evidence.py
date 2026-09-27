from __future__ import annotations

from helpflow_ai.evidence import EvidenceValidator
from helpflow_ai.schemas import EvidenceAnswer, EvidenceClaim, KnowledgeChunk, KnowledgeMatch


def _match(*, chunk_id: str = "document:policy:0", text: str = "Для доступа к VPN используйте корпоративный клиент.") -> KnowledgeMatch:
    return KnowledgeMatch(
        chunk=KnowledgeChunk(
            id=chunk_id,
            service="VPN",
            title="Инструкция по VPN",
            text=text,
            keywords=["vpn", "доступ"],
            escalation_team="Service Desk L1",
        ),
        score=0.9,
    )


def _answer(**overrides) -> EvidenceAnswer:
    data = {
        "answer": "Для доступа к VPN используйте корпоративный клиент.",
        "claims": [{
            "text": "Для доступа к VPN используйте корпоративный клиент.",
            "source_id": "document:policy:0",
            "quote": "Для доступа к VPN используйте корпоративный клиент.",
        }],
        "source_ids": ["document:policy:0"],
        "confidence": 0.91,
        "needs_operator": False,
        "reason": "Ответ найден в инструкции",
    }
    data.update(overrides)
    return EvidenceAnswer.model_validate(data)


def test_valid_claim_is_accepted_and_sources_are_derived() -> None:
    result = EvidenceValidator().validate(_answer(), [_match()])

    assert result.accepted is True
    assert result.source_ids == ["document:policy:0"]
    assert result.reason is None


def test_unknown_source_is_rejected() -> None:
    answer = _answer(claims=[EvidenceClaim(
        text="Используйте корпоративный клиент.",
        source_id="invented.source",
        quote="Используйте корпоративный клиент.",
    )])

    assert EvidenceValidator().validate(answer, [_match()]).reason == "unknown_source"


def test_quote_must_be_exactly_present_after_whitespace_normalization() -> None:
    valid = _answer(claims=[EvidenceClaim(
        text="Для доступа к VPN используйте корпоративный клиент.",
        source_id="document:policy:0",
        quote="Для доступа к VPN\nиспользуйте   корпоративный клиент.",
    )])
    invalid = _answer(
        answer="VPN разрешён с личного компьютера.",
        claims=[EvidenceClaim(
            text="VPN разрешён с личного компьютера.",
            source_id="document:policy:0",
            quote="VPN разрешён с личного компьютера.",
        )],
    )

    validator = EvidenceValidator()
    source = _match(text="Для доступа к VPN\nиспользуйте   корпоративный клиент.")
    assert validator.validate(valid, [source]).accepted is True
    assert validator.validate(invalid, [source]).reason == "quote_not_found"


def test_claim_text_must_appear_in_visible_answer() -> None:
    answer = _answer(claims=[EvidenceClaim(
        text="Сотруднику положена компенсация.",
        source_id="document:policy:0",
        quote="Для доступа к VPN используйте корпоративный клиент.",
    )])

    assert EvidenceValidator().validate(answer, [_match()]).reason == "uncovered_claim"


def test_low_confidence_and_secret_like_content_are_rejected() -> None:
    validator = EvidenceValidator()

    assert validator.validate(_answer(confidence=0.4), [_match()]).reason == "low_confidence"
    secret = _answer(answer="Пароль: Qwerty123!", claims=[])
    assert validator.validate(secret, [_match()]).reason == "sensitive_content"


def test_novel_uncited_substantive_sentence_is_rejected() -> None:
    answer = _answer(answer=(
        "Для доступа к VPN используйте корпоративный клиент. "
        "Личные устройства разрешены всем сотрудникам."
    ))

    assert EvidenceValidator().validate(answer, [_match()]).reason == "unsupported_claim"
