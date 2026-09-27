"""Adapter from ready company documents to chunks the AI retriever can use.

Not wired into TriageEngine here: the integration picks `as_engine_chunk()` or the
fields it needs. Source ids have the form `document:<document_id>:<position>`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories.knowledge import KnowledgeRepository

DEFAULT_SERVICE = "Документы компании"
DEFAULT_TEAM = "Service Desk L1"
_TOKEN = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_STOP_WORDS = frozenset({
    "и", "в", "во", "на", "не", "по", "с", "со", "к", "ко", "о", "об", "от", "до", "за", "из", "для",
    "что", "как", "если", "или", "а", "но", "это", "the", "and", "for", "of", "to", "in",
})


@dataclass(frozen=True)
class CompanyKnowledgeChunk:
    id: str
    document_id: str
    position: int
    title: str
    text: str
    service: str
    keywords: tuple[str, ...]
    heading: str | None
    source_filename: str

    def as_engine_chunk(self) -> dict:
        """Fields of helpflow_ai.schemas.KnowledgeChunk, ready for validation."""
        return {
            "id": self.id,
            "service": self.service,
            "title": self.title,
            "text": self.text,
            "keywords": list(self.keywords),
            "escalation_team": DEFAULT_TEAM,
        }


def source_id(document_id: str, position: int) -> str:
    return f"document:{document_id}:{position}"


def company_knowledge_chunks(session: Session) -> list[CompanyKnowledgeChunk]:
    """Every chunk of every ready document, oldest document first, by position."""
    result = []
    for document, chunk in KnowledgeRepository(session).ready_chunks():
        heading = (chunk.chunk_metadata or {}).get("heading")
        title = f"{document.title} — {heading}" if heading and heading != document.title else document.title
        result.append(CompanyKnowledgeChunk(
            id=source_id(document.id, chunk.position),
            document_id=document.id,
            position=chunk.position,
            title=title,
            text=chunk.text,
            service=document.service or DEFAULT_SERVICE,
            keywords=_keywords(title),
            heading=heading,
            source_filename=document.original_filename,
        ))
    return result


def _keywords(title: str) -> tuple[str, ...]:
    tokens = (token.casefold().replace("ё", "е") for token in _TOKEN.findall(title))
    return tuple(dict.fromkeys(token for token in tokens if len(token) > 2 and token not in _STOP_WORDS))
