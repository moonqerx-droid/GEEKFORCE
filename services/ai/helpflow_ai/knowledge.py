"""Loads approved troubleshooting playbooks and knowledge articles."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schemas import ErrorCode, KnowledgeChunk, Playbook, Step

FALLBACK_PLAYBOOK_ID = "unknown"
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KB_DIR = _REPO_ROOT / "knowledge-base"


class KnowledgeBaseError(RuntimeError):
    """Raised when playbooks are missing or malformed."""


class KnowledgeBase:
    def __init__(
        self,
        playbooks: list[Playbook],
        chunks: list[KnowledgeChunk] | None = None,
        error_codes: list[ErrorCode] | None = None,
    ):
        playbooks = _with_code_steps(playbooks, error_codes or [])
        ids = [playbook.id for playbook in playbooks]
        duplicates = {pid for pid in ids if ids.count(pid) > 1}
        if duplicates:
            raise KnowledgeBaseError(f"Duplicate playbook ids: {sorted(duplicates)}")
        if FALLBACK_PLAYBOOK_ID not in ids:
            raise KnowledgeBaseError(f"Playbook '{FALLBACK_PLAYBOOK_ID}' is required")
        self._playbooks = {playbook.id: playbook for playbook in playbooks}
        approved_chunks = chunks if chunks is not None else _playbook_chunks(playbooks)
        chunk_ids = [chunk.id for chunk in approved_chunks]
        chunk_duplicates = {chunk_id for chunk_id in chunk_ids if chunk_ids.count(chunk_id) > 1}
        if chunk_duplicates:
            raise KnowledgeBaseError(f"Duplicate chunk ids: {sorted(chunk_duplicates)}")
        self._chunks = tuple(approved_chunks)
        self._error_codes: dict[str, ErrorCode] = {}
        for entry in error_codes or []:
            for code in entry.codes:
                if code in self._error_codes:
                    raise KnowledgeBaseError(f"Error code {code} is described twice")
                self._error_codes[code] = entry

    @classmethod
    def load(cls, kb_dir: str | Path | None = None) -> "KnowledgeBase":
        root = Path(kb_dir or os.getenv("HELPFLOW_KB_DIR") or DEFAULT_KB_DIR)
        playbook_dir = root / "playbooks"
        files = sorted(playbook_dir.glob("*.yaml"))
        if not files:
            raise KnowledgeBaseError(f"No playbooks found in {playbook_dir}")
        playbooks = [_load_playbook(path) for path in files]
        article_chunks: list[KnowledgeChunk] = []
        for path in sorted((root / "articles").glob("*.yaml")):
            article_chunks.extend(_load_articles(path))
        error_codes = [entry for path in sorted((root / "error-codes").glob("*.yaml"))
                       for entry in _load_error_codes(path)]
        return cls(playbooks, [*_playbook_chunks(playbooks), *article_chunks], error_codes)

    @property
    def playbooks(self) -> list[Playbook]:
        return list(self._playbooks.values())

    @property
    def chunks(self) -> list[KnowledgeChunk]:
        return list(self._chunks)

    def get(self, playbook_id: str | None) -> Playbook:
        """Return the playbook or the fallback one for unknown ids."""
        return self._playbooks.get(playbook_id or "", self._playbooks[FALLBACK_PLAYBOOK_ID])

    def has(self, playbook_id: str) -> bool:
        return playbook_id in self._playbooks

    def error_code(self, code: str) -> ErrorCode | None:
        from .rules import canonical_code

        return self._error_codes.get(canonical_code(code))

    def find_error_code(self, codes: list[str], prefer: str | None = None) -> tuple[str, ErrorCode] | None:
        """The first known code of a message; one of the current scenario wins over others."""
        known = [(code, self._error_codes[code]) for code in codes if code in self._error_codes]
        if not known:
            return None
        return next(((code, entry) for code, entry in known if entry.playbook == prefer), known[0])


def _load_error_codes(path: Path) -> list[ErrorCode]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        default = data.get("playbook")
        return [ErrorCode.model_validate({"playbook": default, **item}) for item in data.get("codes", [])]
    except (yaml.YAMLError, ValidationError, AttributeError) as error:
        raise KnowledgeBaseError(f"Invalid error codes {path.name}: {error}") from error


def _with_code_steps(playbooks: list[Playbook], error_codes: list[ErrorCode]) -> list[Playbook]:
    """Each code's steps join its scenario, shown only when the message has that code."""
    by_id = {playbook.id: playbook for playbook in playbooks}
    extra: dict[str, list[Step]] = {}
    for entry in error_codes:
        if entry.playbook not in by_id:
            raise KnowledgeBaseError(f"Error code {entry.code}: unknown playbook {entry.playbook}")
        for step in entry.steps:
            extra.setdefault(entry.playbook, []).append(step.model_copy(update={
                "id": f"{entry.step_prefix}{step.id}",
                "when": {**step.when, "error_code": entry.codes},
            }))
    return [playbook.model_copy(update={"steps": [*extra.get(playbook.id, []), *playbook.steps]})
            if playbook.id in extra else playbook for playbook in playbooks]


def _load_playbook(path: Path) -> Playbook:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Playbook.model_validate(data)
    except (yaml.YAMLError, ValidationError) as error:
        raise KnowledgeBaseError(f"Invalid playbook {path.name}: {error}") from error


def _load_articles(path: Path) -> list[KnowledgeChunk]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise TypeError("article file must contain a YAML list")
        return [KnowledgeChunk.model_validate(item) for item in data]
    except (OSError, TypeError, yaml.YAMLError, ValidationError) as error:
        raise KnowledgeBaseError(f"Invalid article {path.name}: {error}") from error


def _playbook_chunks(playbooks: list[Playbook]) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for playbook in playbooks:
        common = {
            "service": playbook.service,
            "keywords": playbook.keywords,
            "escalation_team": playbook.escalation_team,
        }
        for question in playbook.questions:
            chunks.append(
                KnowledgeChunk(
                    id=f"{playbook.id}.question.{question.fact}",
                    title=f"Уточнение: {playbook.title}",
                    text=question.text,
                    safety_notice=playbook.safety_notice,
                    **common,
                )
            )
        for step in playbook.steps:
            chunks.append(
                KnowledgeChunk(
                    id=f"{playbook.id}.step.{step.id}",
                    title=step.title,
                    text=step.instruction,
                    safety_notice=playbook.safety_notice,
                    **common,
                )
            )
        if playbook.safety_notice:
            chunks.append(
                KnowledgeChunk(
                    id=f"{playbook.id}.safety",
                    title=f"Безопасность: {playbook.title}",
                    text=playbook.safety_notice,
                    safety_notice=playbook.safety_notice,
                    **common,
                )
            )
    return chunks
