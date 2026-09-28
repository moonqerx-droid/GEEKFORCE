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
    r"уч[её]тн\w* запис|парол|токен|секрет",
    re.IGNORECASE,
)
_ACCESS_CONTROL = re.compile(
    r"(?:выда\w*|предостав\w*|получ\w*|измен\w*|расшир\w*|запрос\w*)"
    r"[^.!?\n]{0,40}(?:доступ\w*|прав\w*)|"
    r"(?:доступ\w*|прав\w*)[^.!?\n]{0,40}(?:администратор\w*|финансов\w*|crm\b)",
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
_HOW_TO = re.compile(
    r"\bкак\s+(?:настроить|включить|сделать|создать|добавить|получить|подключить(?:ся)?|"
    r"распечатать|сохранить|сменить|изменить|архивировать|заархивировать|закрепить|размыть)",
    re.IGNORECASE,
)
_GENERAL_HOW_TO_TOPICS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("outlook_auto_reply", re.compile(r"(?:автоответ|автоматическ\w* ответ).*outlook|outlook.*(?:автоответ|автоматическ\w* ответ)", re.IGNORECASE)),
    ("teams_background", re.compile(r"teams.*(?:фон|размыть)|(?:фон|размыть).*teams", re.IGNORECASE)),
    ("excel_freeze", re.compile(r"excel.*(?:закреп|строк|столб)|(?:закреп|строк|столб).*excel", re.IGNORECASE)),
    ("print_pdf", re.compile(r"(?:печат|распечат|сохран).*pdf|pdf.*(?:печат|распечат|сохран)", re.IGNORECASE)),
    ("wallpaper", re.compile(r"(?:обои|фон)\s+(?:рабоч\w*\s+)?стол|сменить\s+обои", re.IGNORECASE)),
    ("zip_folder", re.compile(r"(?:архив|заархив|zip|сжат).*папк|папк.*(?:архив|zip|сжат)", re.IGNORECASE)),
    ("shared_calendar", re.compile(r"(?:общ|совместн)\w*\s+календар|календар.*(?:общ|совместн)", re.IGNORECASE)),
    ("screenshot", re.compile(r"скрин|снимок\s+экрана|screenshot", re.IGNORECASE)),
    ("second_monitor", re.compile(r"(?:втор|дополнительн|внешн)\w*\s+(?:монитор|экран|дисплей)|проектор", re.IGNORECASE)),
)
_HARD_HOW_TO_BLOCK = re.compile(
    r"зарплат|преми|финанс|юрид|персональн\w* данн|безопасност|антивирус|"
    r"уч[её]тн\w* запис|парол|токен|секрет",
    re.IGNORECASE,
)


_RULES_QUESTION = re.compile(
    r"(?:что\s+сказано|что\s+говорится|что\s+написано)\s+в\s+\w*|"
    r"(?:по\s+(?:правилам|регламенту|политике|положению|инструкции))|"
    r"(?:согласно|в\s+соответствии\s+с)\s+\w*|"
    r"(?:какие|каковы|какое|какой)\s+(?:требовани\w*|правил\w*|срок\w*|норм\w*|лимит\w*)|"
    r"(?:как\s+часто|сколько\s+(?:символов|дней|раз|рублей)|можно\s+ли|нужно\s+ли|положено\s+ли)",
    re.IGNORECASE,
)


_QUESTION_WORDS = re.compile(
    r"^(?:а\s+|и\s+)?(?:как|что|какой|какая|какие|каким|какое|каков\w*|сколько|когда|кто|где|куда|"
    r"откуда|зачем|можно ли|нужно ли|надо ли|положен\w*|разрешен\w*|минимальн\w*|максимальн\w*|"
    r"до какого|за сколько|раз в сколько)(?![-\w])|(?<![-\w])(?:сколько|какой|какие|можно ли|нужно ли)(?![-\w])"
)
_MEANING_QUESTION = re.compile(r"что\s+(?:значит|означает)|что\s+это\s+за\s+ошибк")
# Failure words: a question built around them is a complaint («почему не работает…»).
_COMPLAINT = re.compile(
    r"\bне\s+(?:работа|подключ|открыва|печата|запуска|грузит|загружа|приход|отправля|пуска|"
    r"вид|слыш|могу|получа|включа|заход|синхрониз)|ошибк|сломал|завис|тормоз|вылета|пропал|"
    r"отвал|глюч|лаг|что\s+делать|почему|не\s+так|помогите"
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
        if _SENSITIVE.search(query) or _ACCESS_CONTROL.search(query) or _DESTRUCTIVE.search(query):
            return AnswerRoute.OPERATOR
        if _LOW_RISK.search(query):
            return AnswerRoute.GENERAL
        return AnswerRoute.OPERATOR

    @staticmethod
    def is_information_question(query: str) -> bool:
        """«Сколько суточных за границей?», «Какой VPN-клиент ставить?» — a question to answer,
        not a problem to troubleshoot. «Почему не подключается VPN?» is a complaint."""
        text = query.strip().lower().replace("ё", "е")
        if _MEANING_QUESTION.search(text):
            return True  # «что значит ошибка 809?» asks for an explanation
        if not (text.endswith("?") or _QUESTION_WORDS.search(text)):
            return False
        return not _COMPLAINT.search(text)

    @staticmethod
    def asks_about_rules(query: str) -> bool:
        """«Какие требования к паролю?», «что сказано в регламенте…» — a question about
        company rules, answered from documents, not a complaint to troubleshoot."""
        return bool(_RULES_QUESTION.search(query))

    def procedural_route(self, query: str, playbook_id: str | None) -> AnswerRoute | None:
        """Classify explicit how-to requests before incident diagnostics start."""
        known_topic = self.general_how_to_topic(query) and self.is_information_question(query)
        if not (_HOW_TO.search(query) or known_topic):
            return None
        topic = self.general_how_to_topic(query)
        if _ACCESS_CONTROL.search(query) or _DESTRUCTIVE.search(query) or _HARD_HOW_TO_BLOCK.search(query):
            return AnswerRoute.OPERATOR
        if playbook_id == "vpn_connection":
            return AnswerRoute.PLAYBOOK
        if topic is not None:
            return AnswerRoute.GENERAL
        if _SENSITIVE.search(query):
            return AnswerRoute.OPERATOR
        return AnswerRoute.OPERATOR

    @staticmethod
    def general_how_to_topic(query: str) -> str | None:
        return next((name for name, pattern in _GENERAL_HOW_TO_TOPICS if pattern.search(query)), None)

    @staticmethod
    def requires_verified_source(query: str) -> bool:
        """Whether clarification cannot make an unsourced answer safe."""
        return bool(
            _SENSITIVE.search(query)
            or _ACCESS_CONTROL.search(query)
            or _DESTRUCTIVE.search(query)
        )
