"""Loads troubleshooting playbooks from knowledge-base/playbooks/*.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schemas import Playbook

FALLBACK_PLAYBOOK_ID = "unknown"
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KB_DIR = _REPO_ROOT / "knowledge-base"


class KnowledgeBaseError(RuntimeError):
    """Raised when playbooks are missing or malformed."""


class KnowledgeBase:
    def __init__(self, playbooks: list[Playbook]):
        ids = [playbook.id for playbook in playbooks]
        duplicates = {pid for pid in ids if ids.count(pid) > 1}
        if duplicates:
            raise KnowledgeBaseError(f"Duplicate playbook ids: {sorted(duplicates)}")
        if FALLBACK_PLAYBOOK_ID not in ids:
            raise KnowledgeBaseError(f"Playbook '{FALLBACK_PLAYBOOK_ID}' is required")
        self._playbooks = {playbook.id: playbook for playbook in playbooks}

    @classmethod
    def load(cls, kb_dir: str | Path | None = None) -> "KnowledgeBase":
        root = Path(kb_dir or os.getenv("HELPFLOW_KB_DIR") or DEFAULT_KB_DIR)
        playbook_dir = root / "playbooks"
        files = sorted(playbook_dir.glob("*.yaml"))
        if not files:
            raise KnowledgeBaseError(f"No playbooks found in {playbook_dir}")
        return cls([_load_playbook(path) for path in files])

    @property
    def playbooks(self) -> list[Playbook]:
        return list(self._playbooks.values())

    def get(self, playbook_id: str | None) -> Playbook:
        """Return the playbook or the fallback one for unknown ids."""
        return self._playbooks.get(playbook_id or "", self._playbooks[FALLBACK_PLAYBOOK_ID])

    def has(self, playbook_id: str) -> bool:
        return playbook_id in self._playbooks


def _load_playbook(path: Path) -> Playbook:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Playbook.model_validate(data)
    except (yaml.YAMLError, ValidationError) as error:
        raise KnowledgeBaseError(f"Invalid playbook {path.name}: {error}") from error
