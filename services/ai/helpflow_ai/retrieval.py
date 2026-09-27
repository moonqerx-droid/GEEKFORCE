"""Deterministic retrieval over the approved HelpFlow knowledge corpus."""

from __future__ import annotations

import re

from .schemas import KnowledgeChunk, KnowledgeMatch

TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
MIN_SCORE = 0.18


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(text)}


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
        for chunk in self._chunks:
            chunk_tokens = _tokens(" ".join([chunk.title, chunk.text, *chunk.keywords]))
            overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
            playbook_bonus = (
                0.30 if overlap > 0 and prefix and chunk.id.startswith(prefix) else 0.0
            )
            score = min(1.0, overlap + playbook_bonus)
            if score >= MIN_SCORE:
                matches.append(KnowledgeMatch(chunk=chunk, score=score))

        return sorted(matches, key=lambda match: (-match.score, match.chunk.id))[:limit]
