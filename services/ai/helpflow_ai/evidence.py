"""Fail-closed validation for claims produced by a language model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import EvidenceAnswer, KnowledgeMatch

_SPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?", re.UNICODE)
_SENSITIVE_RE = re.compile(
    r"(?:парол(?:ь|я)|password|api[_ -]?key|токен|token|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_CREDENTIAL_REQUEST_RE = re.compile(
    r"(?:сообщ\w*|пришл\w*|отправ\w*|назов\w*|введ\w*|покаж\w*|скажи\w*)"
    r"[^.!?\n]{0,40}(?:парол\w*|токен\w*|секрет\w*|код\w* подтвержден\w*)|"
    r"(?:какой|укажите)\s+(?:у вас\s+)?(?:парол\w*|токен\w*)",
    re.IGNORECASE,
)
_UNSAFE_INSTRUCTION_RE = re.compile(
    r"отключ\w*[^.!?\n]{0,30}(?:антивирус\w*|защит\w*|фаервол\w*)|"
    r"удал\w*[^.!?\n]{0,30}(?:системн\w* файл\w*|все файл\w*|данн\w*)|"
    r"обойд\w*[^.!?\n]{0,40}(?:защит\w*|ограничен\w*|политик\w*)",
    re.IGNORECASE,
)


def normalize_evidence_text(value: str) -> str:
    """Normalize layout differences without weakening exact quote checks."""
    return _SPACE_RE.sub(" ", value).strip().casefold()


@dataclass(frozen=True)
class EvidenceValidation:
    accepted: bool
    reason: str | None = None
    source_ids: list[str] = field(default_factory=list)


class EvidenceValidator:
    def __init__(self, *, minimum_confidence: float = 0.65, maximum_length: int = 1200):
        self.minimum_confidence = minimum_confidence
        self.maximum_length = maximum_length

    def validate(
        self,
        answer: EvidenceAnswer,
        matches: list[KnowledgeMatch],
        *,
        prepared_message: str | None = None,
    ) -> EvidenceValidation:
        message = answer.answer.strip()
        if len(message) > self.maximum_length:
            return EvidenceValidation(False, "message_too_long")
        if answer.confidence < self.minimum_confidence:
            return EvidenceValidation(False, "low_confidence")
        if _SENSITIVE_RE.search(message):
            return EvidenceValidation(False, "sensitive_content")
        if _CREDENTIAL_REQUEST_RE.search(message):
            return EvidenceValidation(False, "credential_request")
        if _UNSAFE_INSTRUCTION_RE.search(message):
            return EvidenceValidation(False, "unsafe_instruction")

        sources = {match.chunk.id: match.chunk.text for match in matches}
        claimed_ids = [claim.source_id for claim in answer.claims]
        requested_ids = [*answer.source_ids, *claimed_ids]
        if any(source_id not in sources for source_id in requested_ids):
            return EvidenceValidation(False, "unknown_source")

        # Older providers returned only source_ids. They remain safe solely for
        # the exact deterministic message selected by the rules engine.
        if not answer.claims:
            if (
                prepared_message
                and answer.source_ids
                and normalize_evidence_text(message) == normalize_evidence_text(prepared_message)
            ):
                return EvidenceValidation(True, source_ids=_unique(answer.source_ids))
            return EvidenceValidation(False, "content_mismatch")

        normalized_answer = normalize_evidence_text(message)
        for claim in answer.claims:
            normalized_claim = normalize_evidence_text(claim.text)
            if normalized_claim not in normalized_answer:
                return EvidenceValidation(False, "uncovered_claim")
            if normalize_evidence_text(claim.quote) not in normalize_evidence_text(sources[claim.source_id]):
                return EvidenceValidation(False, "quote_not_found")

        claim_texts = [normalize_evidence_text(claim.text) for claim in answer.claims]
        for sentence in _substantive_sentences(message):
            normalized_sentence = normalize_evidence_text(sentence)
            if not any(
                normalized_sentence in claim_text or claim_text in normalized_sentence
                for claim_text in claim_texts
            ):
                return EvidenceValidation(False, "unsupported_claim")

        return EvidenceValidation(True, source_ids=_unique(claimed_ids))


def _substantive_sentences(message: str) -> list[str]:
    sentences = []
    for match in _SENTENCE_RE.findall(message):
        sentence = match.strip()
        words = re.findall(r"[a-zа-яё0-9]+", sentence, re.IGNORECASE)
        # Very short conversational glue does not assert a company fact.
        if len(words) >= 4 and not sentence.endswith("?"):
            sentences.append(sentence)
    return sentences


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
