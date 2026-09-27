"""Deterministic retrieval over the approved HelpFlow knowledge corpus."""

from __future__ import annotations

import re

from .schemas import KnowledgeChunk, KnowledgeMatch

TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
MIN_SCORE = 0.18


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(text)}


def _normalized_phrase(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.casefold()))


class KnowledgeRetriever:
    def __init__(self, chunks: list[KnowledgeChunk]):
        self._chunks = tuple(chunks)

    def search(
        self,
        query: str,
        playbook_id: str | None,
        limit: int = 4,
    ) -> list[KnowledgeMatch]:
        query_tokens = _tokens(query)
        if not query_tokens or limit < 1:
            return []

        matches: list[KnowledgeMatch] = []
        prefix = f"{playbook_id}." if playbook_id else ""
        query_phrase = _normalized_phrase(query)
        for chunk in self._chunks:
            title_tokens = _tokens(chunk.title)
            body_tokens = _tokens(chunk.text)
            keyword_tokens = _tokens(" ".join(chunk.keywords))
            all_tokens = title_tokens | body_tokens | keyword_tokens
            overlap = len(query_tokens & all_tokens) / len(query_tokens)
            title_overlap = len(query_tokens & title_tokens) / len(query_tokens)
            keyword_overlap = len(query_tokens & keyword_tokens) / len(query_tokens)
            title_phrase = _normalized_phrase(chunk.title)
            body_phrase = _normalized_phrase(chunk.text)
            keyword_phrases = [_normalized_phrase(keyword) for keyword in chunk.keywords]
            exact_phrase_bonus = 0.25 if query_phrase and (
                query_phrase in title_phrase
                or query_phrase in body_phrase
                or any(query_phrase in keyword for keyword in keyword_phrases)
            ) else 0.0
            exact_title_bonus = 0.15 if query_phrase == title_phrase else 0.0
            playbook_bonus = (
                0.20 if overlap > 0 and prefix and chunk.id.startswith(prefix) else 0.0
            )
            score = min(1.0, (
                overlap * 0.45
                + title_overlap * 0.25
                + keyword_overlap * 0.15
                + exact_phrase_bonus
                + exact_title_bonus
                + playbook_bonus
            ))
            if score >= MIN_SCORE:
                matches.append(KnowledgeMatch(chunk=chunk, score=score))

        return sorted(matches, key=lambda match: (-match.score, match.chunk.id))[:limit]
