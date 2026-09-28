"""Deterministic text understanding used without an LLM and as its safety net."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .schemas import Playbook, Question, QuestionKind, Urgency
from .understanding import morph

URGENCY_ORDER = [Urgency.LOW, Urgency.MEDIUM, Urgency.HIGH, Urgency.CRITICAL]
MAX_FREE_TEXT_FACT = 300
# Playbooks that must win whenever they match: safety before convenience.
PRIORITY_PLAYBOOKS = ("security_incident", "mass_incident", "credentials_request")
# When several problems are reported, these go first: the rest often depends on them.
ROOT_CAUSE_PLAYBOOKS = ("network_wifi", "vpn_connection")
# Handled first among the rest when time is short: a call cannot wait.
TIME_CRITICAL_PLAYBOOKS = ("video_calls",)
# Playbooks whose service name is refined from the text (e.g. CRM vs "рабочая система").
GENERIC_SERVICE_PLAYBOOKS = {
    "service_unavailable", "mass_incident", "access_rights", "unknown", "crm_login_device_specific",
    "slow_performance",
}

SERVICE_ALIASES: dict[str, list[str]] = {
    "CRM": ["crm", "црм", "срм", "битрикс", "bitrix", "amocrm", "salesforce"],
    "Почта": ["почт", "outlook", "аутлук", "exchange"],
    "VPN": ["vpn", "впн"],
    "1С": ["1с", "1c"],
    "Jira": ["jira", "джир"],
    "Confluence": ["confluence", "конфлюенс"],
    "Корпоративный портал": ["портал"],
    "Zoom": ["zoom", "зум"],
    "Teams": ["teams", "тимс"],
    "Сеть": ["wi-fi", "wifi", "вай-фай", "вайфай", "интернет"],
}

# Things a user can name when no playbook fits. Generic words like "компьютер"
# are left out on purpose: "беда с компом" is still an ambiguous request.
DEVICE_ALIASES: dict[str, list[str]] = {
    "Мышь": ["мыш"],
    "Клавиатура": ["клавиатур", "клава", "клаву", "клавой"],
    "Монитор": ["монитор"],
    "Принтер": ["принтер", "мфу"],
    "Сканер": ["сканер"],
    "Проектор": ["проектор"],
    "Док-станция": ["док-станц", "докстанц"],
    "Веб-камера": ["веб-камер", "вебк"],
    "Excel": ["excel", "эксель", "ексель"],
    "Word": ["word", "ворд"],
    "Браузер": ["браузер", "chrome", "хром"],
    "Телефония": ["ip-телефон", "sip"],
}

# stem -> noun used in the urgency reason
_MEETINGS = {
    "встреч": "встреча",
    "совещан": "совещание",
    "презентац": "презентация",
    "созвон": "созвон",
    "планерк": "планёрка",
    "переговор": "переговоры",
    "собеседован": "собеседование",
    "звонок с клиент": "звонок с клиентом",
}
_NOT_URGENT_RE = r"не срочн\w*|когда будет время|не горит|без спешки"
_TIME_RE = re.compile(r"через\s+(\d+|пару|несколько|полчаса|час)\s*(минут\w*|мин|час\w*)?")

_YES_RE = re.compile(r"^(да|ага|угу|есть|конечно|yes|ok|ок|так точно|верно|подключ|работает|включ)")
_NO_RE = re.compile(r"^(нет|неа|no\b|не\b|ни\b|отключ|выключ)")
_UNKNOWN_RE = re.compile(r"(не знаю|не уверен|без понятия|\bхз\b|не помню)")
_GREETING_RE = re.compile(
    r"^(?:привет|здравствуйте|здравствуй|добрый день|доброе утро|добрый вечер|"
    r"хай|hello|hi)(?:\s+(?:бот|helpflow))?$"
)
_THANKS_RE = re.compile(r"^(?:спасибо|благодарю|спс|thanks|thank you)(?:\s+большое)?$")
_HELP_RE = re.compile(
    r"^(?:помощь|помоги|что ты умеешь|как ты можешь помочь|чем ты можешь помочь|help)$"
)
_OPERATOR_REQUEST_RE = re.compile(
    r"(?:позов|приглас|соедин|переключ|дайте|хочу|нужен|нужна).*"
    r"(?:оператор|специалист|поддержк|жив\w* человек|человек)"
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def is_greeting_only(text: str) -> bool:
    """True only for a standalone greeting, never for a greeting plus an issue."""
    cleaned = re.sub(r"[^\w\s-]", " ", normalize(text))
    return bool(_GREETING_RE.fullmatch(normalize(cleaned)))


def conversation_intent(text: str) -> str | None:
    """Recognize short dialogue-control phrases without consuming triage facts."""
    cleaned = normalize(re.sub(r"[^\w\s-]", " ", text))
    if is_greeting_only(cleaned):
        return "greeting"
    if _THANKS_RE.fullmatch(cleaned):
        return "thanks"
    if _HELP_RE.fullmatch(cleaned):
        return "help"
    if _OPERATOR_REQUEST_RE.search(cleaned):
        return "operator"
    return None


def understand(text: str) -> str:
    """Normalized text with typos fixed: what every detector below should read."""
    return morph.correct(normalize(text))


def contains(norm_text: str, keyword: str) -> bool:
    """Word-prefix match: 'парол' matches 'пароль', '500' does not match '1500'.

    Also matches other word forms: «очередь печати» finds «в очереди печати».
    """
    keyword = normalize(keyword)
    if re.search(r"(?<!\w)" + re.escape(keyword), norm_text):
        return True
    lemma_keyword = morph.lemmatize(keyword)
    if re.search(r"(?<!\w)" + re.escape(lemma_keyword), morph.lemmatize(norm_text)):
        return True
    return " " in keyword and _phrase_re(keyword).search(norm_text) is not None


@lru_cache(maxsize=2048)
def _phrase_re(keyword: str) -> re.Pattern[str]:
    """«подозрительн письм» = «подозрительное письмо»: every longer word of a phrase is a
    stem; short ones («к», «от», «у») stay whole words."""
    parts = [re.escape(word) + (r"\w*" if len(word) >= 4 else r"(?!\w)") for word in keyword.split(" ")]
    return re.compile(r"(?<!\w)" + " ".join(parts))


def _keyword_weight(keyword: str) -> int:
    # Multi-word phrases and error codes are stronger evidence than a single stem.
    return 2 if (" " in keyword or keyword.isdigit()) else 1


# «никто в офисе не может»: a collective subject with a few words before the verb.
_NOBODY_CAN_RE = re.compile(r"(?<!\w)никто(?: \S+){1,3} не (?:может|могут|получается|работает)(?!\w)")


def score_playbook(norm_text: str, playbook: Playbook) -> int:
    score = sum(_keyword_weight(kw) for kw in playbook.keywords if contains(norm_text, kw))
    if playbook.id == "mass_incident" and _NOBODY_CAN_RE.search(norm_text):
        score += 2
    return score


@dataclass(frozen=True)
class Classification:
    playbook_id: str
    confidence: float


def classify(text: str, playbooks: list[Playbook]) -> Classification:
    norm = understand(text)
    scores = {pb.id: score_playbook(norm, pb) for pb in playbooks}
    for priority_id in PRIORITY_PLAYBOOKS:
        if scores.get(priority_id, 0) > 0:
            return Classification(priority_id, 0.9)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_id, best = ranked[0]
    if best == 0:
        return Classification("unknown", 0.3)
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    confidence = min(0.95, 0.55 + 0.1 * best)
    if runner_up == best:
        confidence -= 0.15
    return Classification(best_id, round(confidence, 2))


# --- several problems in one message ----------------------------------------

_CLAUSE_SPLIT_RE = re.compile(r"[.,;:!?\n]+")
_CONJUNCTION_SPLIT_RE = re.compile(
    r"\s+(?:а\s+(?:еще|ещё|также|вдобавок)|и\s+(?:еще|ещё)|(?:еще|ещё)\s+и|да\s+и|плюс|также|а|и|но)\s+",
    re.IGNORECASE,
)
FAILURE_RE = _FAILURE_RE = re.compile(
    r"(?<!\w)(?:не|нет|ни)(?!\w)|отвал|пропа|ошибк|слома|глюч|тормоз|лага|вылета|завис|упал|"
    r"лежит|прерыва|разрыва|без доступа|замят|зажев|сбо[ий]"
)


# "ошибка 403", "пишет «Сессия истекла»": details of a neighbouring problem, not a problem.
_DETAIL_RE = re.compile(r"^(?:пишет|выда[её]т|показывает|ошибка|error|код|сообщение)(?!\w)|^[«\"“\d]")


def split_clauses(text: str) -> list[tuple[str, bool]]:
    """Split a message into clauses; the flag says whether the clause reports a failure.

    "Не работает почта и интернет": the bare "интернет" inherits the failure.
    "Почта и интернет не работают": a single noun before the conjunction shares it too.
    Error texts and codes never count as a failure on their own.
    """
    clauses: list[tuple[str, bool]] = []
    for segment in _CLAUSE_SPLIT_RE.split(text):
        parts: list[list] = []  # [text, failing, is_detail]
        for part in _CONJUNCTION_SPLIT_RE.split(f" {segment} "):
            part = part.strip()
            if not part:
                continue
            detail = bool(_DETAIL_RE.search(normalize(part)))
            failing = not detail and bool(_FAILURE_RE.search(normalize(part)))
            if parts and not detail and not failing and parts[-1][1] and len(part.split()) <= 3:
                failing = True
            parts.append([part, failing, detail])
        for current, following in zip(parts, parts[1:]):
            if not current[1] and not current[2] and following[1] and len(current[0].split()) == 1:
                current[1] = True
        clauses += [(part, failing) for part, failing, _ in parts]
    return clauses


def plan_issues(text: str, playbooks: list[Playbook], best_id: str,
                urgent: bool = False) -> list[tuple[str, str]]:
    """Problems found in the text as (playbook_id, evidence), in the order to handle them.

    A clause mentioning the best playbook belongs to it ("Outlook просит пароль" is one
    mail problem). Any other clause becomes a separate problem only if it reports a failure,
    so "VPN подключен" stays a fact.
    """
    candidates = [pb for pb in playbooks if pb.id not in ("unknown", *PRIORITY_PLAYBOOKS)]
    found: dict[str, str] = {}
    best_fails = False
    for clause, failing in split_clauses(text):
        norm = understand(clause)
        scores = {pb.id: score_playbook(norm, pb) for pb in candidates}
        if scores.get(best_id, 0) > 0:
            owner = best_id
            best_fails = best_fails or failing
        elif failing and scores and max(scores.values()) > 0:
            owner = max(scores, key=scores.get)
        else:
            continue
        found.setdefault(owner, clause)
    if not best_fails and len(found) > (1 if best_id in found else 0):
        # The best match rests on details only («ошибка 403» next to "CRM не работает"):
        # the text describes one problem, not several.
        return [(best_id, "")]
    found.setdefault(best_id, "")
    # First the root cause, then a call that cannot wait; otherwise the best match.
    # The rest follows in the order the user wrote it.
    first = [pid for pid in ROOT_CAUSE_PLAYBOOKS if pid in found]
    if urgent:
        first += [pid for pid in TIME_CRITICAL_PLAYBOOKS if pid in found]
    order = [*(first or [best_id]), *found]
    return [(pid, found[pid]) for pid in dict.fromkeys(order)]


def detect_service(text: str, playbook: Playbook) -> str:
    if playbook.id not in GENERIC_SERVICE_PLAYBOOKS:
        return playbook.service
    norm = understand(text)
    for service, aliases in SERVICE_ALIASES.items():
        if any(contains(norm, alias) for alias in aliases):
            return service
    return playbook.service


def detect_subject(text: str) -> str | None:
    """What the user is talking about, when it is named explicitly."""
    norm = understand(text)
    for subject, aliases in {**SERVICE_ALIASES, **DEVICE_ALIASES}.items():
        if any(contains(norm, alias) for alias in aliases):
            return subject
    return None


def detect_symptoms(text: str, playbook: Playbook) -> list[str]:
    norm = understand(text)
    return [
        label
        for label, hints in playbook.symptoms_hints.items()
        if any(contains(norm, hint) for hint in hints)
    ]


def max_urgency(*levels: Urgency) -> Urgency:
    return max(levels, key=URGENCY_ORDER.index)


def _time_pressure_reasons(norm: str) -> list[str]:
    meeting = next((noun for stem, noun in _MEETINGS.items() if contains(norm, stem)), None)
    time_match = _TIME_RE.search(norm)
    if meeting and time_match:
        return [f"{meeting} {time_match.group(0)}"]
    if time_match:
        return [f"нужно решить {time_match.group(0)}"]
    if meeting:
        return [f"скоро {meeting}"]
    return []


def detect_urgency(text: str, playbook: Playbook) -> tuple[Urgency, str]:
    """Return urgency and a human-readable reason."""
    norm = understand(text)
    if playbook.id == "security_incident":
        return Urgency.CRITICAL, "возможный инцидент информационной безопасности"
    if playbook.id == "mass_incident":
        return Urgency.CRITICAL, "проблема затрагивает нескольких сотрудников"
    if re.search(r"клиент\w* не могут|клиенты жалуются|продажи стоят", norm):
        return Urgency.CRITICAL, "проблема затрагивает клиентов"

    not_urgent = re.search(_NOT_URGENT_RE, norm)
    norm = re.sub(_NOT_URGENT_RE, " ", norm)  # "не срочно" must not trigger "срочн"
    reasons = _time_pressure_reasons(norm)
    if re.search(r"срочн|горит|asap|асап|немедленно|прямо сейчас|очень нужно", norm):
        reasons.append("пользователь отмечает срочность")
    if re.search(r"не могу работать|работа стоит|вообще ничего не|совсем не работает|клиент ждет", norm):
        reasons.append("работа сотрудника остановлена")

    if reasons:
        return max_urgency(Urgency.HIGH, playbook.default_urgency), "; ".join(reasons)
    if not_urgent:
        return Urgency.LOW, "пользователь указал, что вопрос не срочный"
    return playbook.default_urgency, "стандартный приоритет для этого типа проблем"


# --- fact extraction -------------------------------------------------------

_FACT_PATTERNS: list[tuple[str, str, str]] = [
    # (fact, value, regex over normalized text); first match per fact wins
    ("other_device_works", "yes",
     r"(с|на|через) (телефон|смартфон|мобильн|друг\w* (компьютер|ноутбук|устройств))\w*,? "
     r"(все |всё )?(работает|норм|открывается|заходит|пускает|ок)"),
    ("since_when", "вчера работало, сегодня нет", r"вчера (все |всё )?работал\w*"),
    ("since_when", "с сегодняшнего дня", r"с утра|сегодня"),
    ("recurring", "yes", r"\b(опять|снова|в который раз|уже не первый раз)\b"),
    ("vpn", "no", r"без (vpn|впн)|(vpn|впн) (не |от|вы)\w*|не подключ\w* (к )?(vpn|впн)"),
    ("vpn", "yes", r"(через|по|подключен\w* к|включен\w*) (vpn|впн)|(vpn|впн) (подключен|включен|работает)"),
    ("location", "remote", r"из дома|\bдома\b|удаленк|удаленно"),
    ("location", "office", r"в офисе|на работе"),
    ("colleagues_affected", "yes", r"у коллег (тоже|так же|также)|у всех|никто не может|ни у кого"),
    ("colleagues_affected", "no", r"у коллег (все |всё )?работает|только у меня"),
    ("account_locked", "yes", r"заблокир"),
    ("internet_works", "no", r"нет интернета|интернет не работает|не работает интернет"),
    ("internet_works", "yes", r"интернет (работает|есть)"),
    ("mail_client", "outlook", r"outlook|аутлук"),
    ("call_app", "zoom", r"zoom|\bзум"),
    ("call_app", "teams", r"teams|тимс"),
    ("call_app", "telemost", r"телемост"),
    ("headset", "yes", r"наушник|гарнитур"),
    ("entered_credentials", "yes", r"вв(е|ё)л\w* (свой )?пароль|ввела пароль"),
    ("password_changed_recently", "yes", r"\w*мен\w*л\w* пароль"),
    ("device", "laptop", r"ноут"),
    ("device", "desktop", r"(с|на) (компьютер|пк|компе)"),
    ("had_access_before", "yes",
     r"(пропал|исчез|отобрали|слетел)\w* доступ|доступ\w* (пропал|исчез|слетел)|был доступ|больше нет доступа"),
    ("had_access_before", "no",
     r"(нуж\w*|дайте|дать|выда\w*|откро\w*|открыть|предостав\w*) доступ|нов\w* сотрудник"),
]

# "доступ к папке бухгалтерии на общем диске" -> "папке бухгалтерии на общем диске"
_RESOURCE_RE = re.compile(
    r"доступ\w*\s+(?:к|ко|в|во|на)\s+(.+?)"
    r"(?=\s*[,.!?;:(]|\s+(?:пишет|выдает|выдаёт|горит|срочно|пожалуйста|плиз|пж)\b|$)",
    re.IGNORECASE,
)
_ERROR_CODE_RE = re.compile(r"(?<!\d)([45]\d\d)(?!\d)")
_QUOTED_RE = re.compile(r"[«\"“]([^»\"”]{3,200})[»\"”]")
_ERROR_PHRASE_RE = re.compile(
    r"(?:пишет|выдает|выдаёт|показывает|ошибка|error|сообщение)\s*:?\s*([^.!?\n]{3,200})",
    re.IGNORECASE,
)


def extract_facts(text: str) -> dict[str, str]:
    """Pull normalized facts out of free text."""
    norm = understand(text)
    facts: dict[str, str] = {}
    for fact, value, pattern in _FACT_PATTERNS:
        if fact not in facts and re.search(pattern, norm):
            facts[fact] = value
    error_text = extract_error_text(text)
    if error_text:
        facts["error_text"] = error_text
    resource = _RESOURCE_RE.search(text)
    if resource:
        facts["resource"] = resource.group(1).strip()[:MAX_FREE_TEXT_FACT]
    return facts


def extract_error_text(text: str) -> str | None:
    quoted = _QUOTED_RE.search(text)
    if quoted:
        return quoted.group(1).strip()
    phrase = _ERROR_PHRASE_RE.search(text)
    if phrase:
        return phrase.group(1).strip(" ,;:")[:MAX_FREE_TEXT_FACT]
    code = _ERROR_CODE_RE.search(text)
    if code:
        return f"ошибка {code.group(1)}"
    return None


def parse_answer(question: Question, text: str) -> str:
    """Turn the user's reply to a specific question into a fact value."""
    norm = understand(text)
    if question.kind == QuestionKind.YES_NO:
        return _parse_yes_no(norm, question.invert)
    if question.kind == QuestionKind.CHOICE:
        for value, keywords in question.options.items():
            if any(contains(norm, kw) for kw in keywords):
                return value
        return "unknown" if _UNKNOWN_RE.search(norm) else text.strip()[:MAX_FREE_TEXT_FACT]
    if _UNKNOWN_RE.search(norm):
        return "unknown"
    if question.fact == "error_text":
        if _NO_MESSAGE_RE.fullmatch(norm.strip(" .!")):
            return NO_ERROR_MESSAGE
        return extract_error_text(text) or text.strip()[:MAX_FREE_TEXT_FACT]
    return text.strip()[:MAX_FREE_TEXT_FACT]


# «нет», «ничего не пишет»: the answer to «есть ли сообщение об ошибке?», not its text.
NO_ERROR_MESSAGE = "сообщения об ошибке нет"
_NO_MESSAGE_RE = re.compile(
    r"(?:нет|неа|нету|ничего|никакого|никаких)(?:\s+(?:ошибки|ошибок|сообщения|сообщений|не пишет|не показывает|не выдает))?"
    r"|(?:ошибки|сообщения) нет|ничего не (?:пишет|показывает|выдает|появляется)|просто не работает"
)


def quick_replies(question: Question) -> list[str]:
    """One-tap answers for a closed question; each one parses back to its own option."""
    if question.kind == QuestionKind.YES_NO:
        return ["Да", "Нет", "Не знаю"]
    if question.kind == QuestionKind.CHOICE:
        labels = [
            question.option_labels.get(value) or keywords[0].capitalize()
            for value, keywords in question.options.items()
        ]
        return [*labels, "Не знаю"] if question.offer_dont_know else labels
    return []


def _parse_yes_no(norm: str, invert: bool) -> str:
    if _UNKNOWN_RE.search(norm):
        return "unknown"
    if _NO_RE.search(norm) or re.search(r"\bне (работает|подключ|открыва|включ)", norm):
        answer = "no"
    elif _YES_RE.search(norm):
        answer = "yes"
    else:
        return "unknown"
    if invert:
        return "no" if answer == "yes" else "yes"
    return answer


# «Не нашёл, где это», «требует пароль администратора»: the step could not be done.
_CANNOT_RE = re.compile(
    r"не (?:могу|получается|выходит) (?:найти|открыть|сделать|выполнить|нажать|понять)|"
    r"не наш(?:ел|ла|ли)|где (?:это|найти|находится|искать)|как (?:это )?(?:сделать|найти|открыть)|"
    r"не понима|не понял|нет (?:такого|такой|такой кнопки|прав)|не вижу (?:такого|такой|кнопк|пункт)|"
    r"(?:требует|просит|нужны) (?:права|прав|пароль администратора|администратор)"
)


def parse_step_outcome(text: str) -> str | None:
    """A typed result of a troubleshooting step: helped / not_helped / cannot_perform."""
    if _CANNOT_RE.search(understand(text)):
        return "cannot_perform"
    solved = parse_confirmation(text)
    if solved is None:
        return None
    return "helped" if solved else "not_helped"


def parse_confirmation(text: str) -> bool | None:
    """Interpret the answer to 'is the problem solved?'. None = unclear."""
    norm = understand(text)
    if _UNKNOWN_RE.search(norm):
        return None
    if re.search(r"не (помог|работает|решен|получ|восстанов|открыва|заработал|пуска|входит|выходит|могу|видит|печата|грузит)|"
                 r"все еще|все равно|по-прежнему|опять|так и не|\bнет\b", norm):
        return False
    answer = _parse_yes_no(norm, invert=False)
    if answer == "yes" or re.search(
        r"помогл|заработал|восстанов|получилось|решен|работает|"
        r"все (?:ок|окей|хорошо|норм\w*|отлично|супер)|\bнорм\w*\b|\bок\b|спасибо|благодарю", norm,
    ):
        return True
    if answer == "no":
        return False
    return None
