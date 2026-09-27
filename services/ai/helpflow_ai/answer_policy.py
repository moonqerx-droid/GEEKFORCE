"""Choose the safest available source tier for an incoming question."""

from __future__ import annotations

import re
from enum import Enum

from .schemas import KnowledgeMatch


class AnswerRoute(str, Enum):
    COMPANY = "company"
    PLAYBOOK = "playbook"
    GENERAL = "general"
    OPERATOR = "operator"


_SENSITIVE = re.compile(
    r"отпуск|зарплат|компенсац|командиров|кадров|hr\b|юрид|договор|финанс|"
    r"реквизит|персональн\w* данн|политик|регламент|безопасност|антивирус|"
    r"доступ|прав[ао] администратор|уч[её]тн\w* запис|парол|токен|секрет",
    re.IGNORECASE,
)
_DESTRUCTIVE = re.compile(
    r"удал(?:ить|и)|форматир|сброс(?:ить)?|отключ(?:ить|и)|реестр|system32|"
    r"стереть|обойти|взлом",
    re.IGNORECASE,
)
_LOW_RISK = re.compile(
    r"кэш|cache|cookie|браузер|обновить страниц|перезапуст|перезагруз|"
    r"подключен(?:ие|а)|интернет|wi-?fi|верси[яю]|закрыть и открыть",
    re.IGNORECASE,
)


class AnswerPolicy:
    """Company evidence wins; unsupported risky questions always reach a human."""

    def route(
        self,
        query: str,
        matches: list[KnowledgeMatch],
        playbook_id: str | None,
    ) -> AnswerRoute:
        if any(match.chunk.id.startswith("document:") for match in matches):
            return AnswerRoute.COMPANY
        if matches and playbook_id and playbook_id != "unknown":
            return AnswerRoute.PLAYBOOK
        if _SENSITIVE.search(query) or _DESTRUCTIVE.search(query):
            return AnswerRoute.OPERATOR
        if _LOW_RISK.search(query):
            return AnswerRoute.GENERAL
        return AnswerRoute.OPERATOR

    @staticmethod
    def requires_verified_source(query: str) -> bool:
        """Whether clarification cannot make an unsourced answer safe."""
        return bool(_SENSITIVE.search(query) or _DESTRUCTIVE.search(query))
