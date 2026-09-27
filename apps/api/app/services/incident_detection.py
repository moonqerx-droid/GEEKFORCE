from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import ceil
import re
from typing import Iterable


TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
STOP_WORDS = frozenset({
    "а", "без", "бы", "в", "все", "всех", "для", "до", "и", "из", "или",
    "как", "к", "ли", "мне", "мы", "на", "не", "но", "о", "от", "по", "при",
    "с", "со", "у", "что", "это", "я",
    "a", "an", "and", "for", "from", "in", "is", "not", "of", "on", "or", "the", "to",
    "http", "https", "меня", "отвечает", "ошибка", "ошибку", "проблема", "работает",
    "сервис", "сервера",
})
EXCLUDED_SERVICES = frozenset({"", "не определен", "не определено", "unknown"})


@dataclass(frozen=True)
class IncidentFingerprint:
    service: str
    weighted_tokens: dict[str, int]


@dataclass(frozen=True)
class SimilarityResult:
    score: float
    evidence_tokens: list[str]


def _tokens(value: str | None) -> list[str]:
    normalized = (value or "").casefold().replace("ё", "е")
    tokens = []
    for token in TOKEN_RE.findall(normalized):
        if len(token) <= 1 or token in STOP_WORDS:
            continue
        tokens.append("недоступен" if token.startswith("недоступ") else token)
    return tokens


def _put(tokens: dict[str, int], values: Iterable[str], weight: int) -> None:
    for token in values:
        tokens[token] = max(tokens.get(token, 0), weight)


def build_fingerprint(conversation) -> IncidentFingerprint | None:
    playbook_id = str(getattr(conversation, "playbook_id", "") or "").casefold()
    service_tokens = _tokens(getattr(conversation, "service", None))
    service = " ".join(service_tokens)
    if playbook_id in {"unknown", "security_incident"} or service in EXCLUDED_SERVICES:
        return None

    weighted: dict[str, int] = {}
    _put(weighted, service_tokens, 3)
    _put(weighted, _tokens(getattr(conversation, "summary", None)), 2)
    for symptom in getattr(conversation, "symptoms", None) or []:
        _put(weighted, _tokens(str(symptom)), 2)

    known_facts = getattr(conversation, "known_facts", None) or {}
    error_tokens = _tokens(str(known_facts.get("error_text", "")))
    _put(weighted, (token for token in error_tokens if any(char.isdigit() for char in token)), 3)
    _put(weighted, (token for token in error_tokens if not any(char.isdigit() for char in token)), 2)

    for message in getattr(conversation, "messages", None) or []:
        if str(getattr(message, "role", "")) == "user":
            _put(weighted, _tokens(getattr(message, "content", "")), 1)
            break

    if not weighted:
        return None
    return IncidentFingerprint(service=service, weighted_tokens=weighted)


def similarity(left: IncidentFingerprint, right: IncidentFingerprint) -> SimilarityResult:
    if left.service != right.service:
        return SimilarityResult(score=0.0, evidence_tokens=[])
    universe = set(left.weighted_tokens) | set(right.weighted_tokens)
    intersection_weights = {
        token: min(left.weighted_tokens.get(token, 0), right.weighted_tokens.get(token, 0))
        for token in universe
        if token in left.weighted_tokens and token in right.weighted_tokens
    }
    intersection = sum(intersection_weights.values())
    union = sum(
        max(left.weighted_tokens.get(token, 0), right.weighted_tokens.get(token, 0))
        for token in universe
    )
    evidence = sorted(intersection_weights, key=lambda token: (-intersection_weights[token], token))
    return SimilarityResult(score=intersection / union if union else 0.0, evidence_tokens=evidence)


def recompute_signature(fingerprints: list[IncidentFingerprint]) -> list[str]:
    if not fingerprints:
        return []
    minimum_presence = ceil(len(fingerprints) / 2)
    presence = Counter(token for item in fingerprints for token in item.weighted_tokens)
    max_weights = {
        token: max(item.weighted_tokens.get(token, 0) for item in fingerprints)
        for token in presence
    }
    service_tokens = {token for item in fingerprints for token in _tokens(item.service)}
    error_codes = {token for token in presence if any(char.isdigit() for char in token)}
    kept = {
        token for token, count in presence.items()
        if count >= minimum_presence or token in service_tokens or token in error_codes
    }
    return sorted(kept, key=lambda token: (-max_weights[token], token))
