"""Deterministic text understanding used without an LLM and as its safety net."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import dropwhile, takewhile

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
    "CRM": ["crm", "црм", "срм", "битрикс", "bitrix", "amocrm", "salesforce", "салесфорс"],
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
    r"^(?:(?:привет|здравствуйте|добрый день)\s+)?(?:"
    r"помощь|помоги|help|команды|меню|возможности|"
    r"что ты (?:умеешь|можешь|знаешь)|что умеешь|что можешь|что ты умеешь делать|"
    r"(?:как|чем) ты можешь помочь|чем можешь помочь|чем ты полезен|"
    r"(?:какие|на какие) вопросы (?:тебе |ты )?(?:можно задать|можно задавать|отвечаешь|можешь ответить|понимаешь)|"
    r"о ч[её]м (?:тебя можно спросить|можно спросить)|что у тебя можно спросить|"
    r"расскажи (?:о себе|что умеешь)|кто ты"
    r")$"
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
    if _OPERATOR_REQUEST_RE.search(cleaned) or _asks_only_for_a_person(cleaned):
        return "operator"
    return None


# «живого человека дайте»: the person first, the verb after.
_PERSON_THEN_VERB_RE = re.compile(
    r"(?<!\w)(?:специалист|оператор|живо\w* человек|человек|админ)\w*(?: \S+){0,2} "
    r"(?:позов|пригласите|дайте|давайте|соедин|нужен|нужна|нужно|подключ)"
)
_PERSON_RE = re.compile(r"^(?:специалист|оператор|человек|сотрудник поддержки|поддержк|админ)\w*$")
# Words that only add pressure or politeness around the person asked for.
_FILLER = frozenset(
    "срочно очень пожалуйста плиз пж мне нам живого живой живым скорее быстрее быстро прошу "
    "ну уже эй а и с со к ко нужен нужна нужно".split()
)


def _asks_only_for_a_person(cleaned: str) -> bool:
    """«СРОЧНО СПЕЦИАЛИСТА», «оператора!», «специалиста пожалуйста, очень срочно»: nothing but the
    person asked for and words around it. «Специалист сказал перезагрузить» names no request."""
    if _PERSON_THEN_VERB_RE.search(cleaned):
        return True
    rest = [word for word in cleaned.split() if word not in _FILLER]
    return len(rest) == 1 and bool(_PERSON_RE.match(rest[0]))


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
    lemma_keyword = morph.lemmatize_verbs_with_person(keyword)
    if re.search(r"(?<!\w)" + re.escape(lemma_keyword), morph.lemmatize_verbs_with_person(norm_text)):
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
_NOBODY_CAN_RE = re.compile(
    r"(?<!\w)никто(?: \S+){1,3} не (?:может|могут|получается|работает)(?!\w)|"
    r"(?<!\w)ни у кого(?: \S+){1,3} (?:не|нет)(?!\w)")


# «программа учёта не запускается»: a program named with a word or two before the failure.
_PROGRAM_FAILS_RE = re.compile(
    r"(?<!\w)(?:программ|приложени|word|ворд|excel|эксель|powerpoint|пауэрпоинт|acrobat|акробат|reader)\w*"
    r"(?: \S+){0,3} (?:не (?:запуска|открыва|устанавлива|стартует)|перестал\w* (?:запуска|открыва)|"
    r"выда\w* ошибк|закрыва|вылета|краш)|"
    r"не (?:получается|удается|могу) (?:установить|обновить) (?:\S+ )?(?:обновлени|программ|приложени)"
)


# «в 1с кончились лицензии»: 1С and a sign-in sign anywhere in the message.
_ONEC_RE = re.compile(r"(?<!\w)1[сc](?!\w)")
_ONEC_LOGIN_RE = re.compile(
    r"лиценз|сеанс|авториз|парол|логин|списк\w* баз|баз\w*(?: \S+){0,2} в списке|"
    r"(?:не вижу|нет|пропал\w*)(?: \S+){0,2} баз")


def score_playbook(norm_text: str, playbook: Playbook) -> int:
    score = sum(_keyword_weight(kw) for kw in playbook.keywords if contains(norm_text, kw))
    if playbook.id == "mass_incident" and _NOBODY_CAN_RE.search(norm_text):
        score += 2
    if playbook.id == "app_not_starting" and _PROGRAM_FAILS_RE.search(norm_text):
        score += 2
    if playbook.id == "onec_login" and _ONEC_RE.search(norm_text) and _ONEC_LOGIN_RE.search(norm_text):
        score += 3  # «1с просит пароль» is about 1С, not the Windows password
    if playbook.id == "slow_performance" and _SLOW_SUBJECT_RE.search(norm_text):
        score += 2
    if playbook.id == "security_incident" and _social_engineering(norm_text):
        score += 3
    if playbook.id == "vpn_connection" and _REMOTE_RE.search(norm_text) and _WORK_NETWORK_RE.search(norm_text):
        score += 3
    if playbook.id == "password_login" and _DEVICE_LOGIN_RE.search(norm_text):
        score += 2
    if playbook.id == "security_incident" and _ANTIVIRUS_EVENT_RE.search(norm_text):
        score += 2
    asker = _password_asker(norm_text)
    if asker is not None and playbook.id == asker:
        score += 2
    if playbook.id == "credentials_request" and _SOMEONES_CREDENTIALS_RE.search(norm_text):
        score += 3
    if playbook.id == "software_install" and _software_request(norm_text):
        score += 2
    if playbook.id == "security_incident" and _COMPROMISE_SIGN_RE.search(norm_text):
        score += 3
    if playbook.id == "network_wifi" and _SLOW_NETWORK_RE.search(norm_text):
        score += 3
    if (playbook.id == "app_not_starting" and _FAILS_TO_START_RE.search(norm_text)
            and not _NOT_A_LOCAL_PROGRAM_RE.search(norm_text)):
        score += 2
    if playbook.id == "software_install" and _INSTALL_NEEDS_ADMIN_RE.search(norm_text):
        score += 3
    if (playbook.id == "credentials_request" and _INSTALL_NEEDS_ADMIN_RE.search(norm_text)
            and not _ASKS_FOR_IT_RE.search(norm_text)):
        return 0  # «установка требует пароль администратора» describes the installer, asks nothing
    if playbook.id == "vpn_connection" and _VPN_FAILS_RE.search(norm_text):
        score += 2  # «впн не цепляется, а мне в црм»: the VPN fails, the CRM is only the goal
    return score


# Signs of a compromise without the word «вирус»: a program in an attachment, mail sent in
# the person's name, a cursor that moves by itself, a code nobody asked for, a «security» call.
_COMPROMISE_SIGN_RE = re.compile(
    r"(?<!\w)exe(?!\w)|\.(?:exe|scr|bat|js|vbs)(?!\w)|"
    r"(?:от моего имени|с моего (?:ящика|адреса|почты|аккаунта))(?: \S+){0,4} (?:разосл|ушл|рассыл|отправ)|"
    r"(?:мыш\w*|курсор)(?: \S+){0,1} сам\w*(?: по себе)? (?:бега|двига|кликает|открывает|нажима)|"
    r"(?:код\w*|смс)[^.!?]{0,40}(?:(?:хотя|а) я? ?(?:ничего |никуда )?не (?:запрашивал|входил|заходил|просил))|"
    r"(?:звон|позвонил)\w*[^.!?]{0,20} (?:из |от )?[«\"]?служб\w* безопасност"
)
# «вайфай медленный», «интернет еле работает»: the network is slow, not the computer.
_SLOW_NETWORK_RE = re.compile(
    r"(?<!\w)(?:wi-fi|wifi|вай-фай|вайфай|вай фай|интернет|сеть)\w*(?: \S+){0,1} "
    r"(?:тормоз|медлен|лага|еле|очень медлен|плохо работает)"
)
# «не запускается клиент-банк», «телеграм не запускается»: any program but the computer itself.
_FAILS_TO_START_RE = re.compile(
    r"(?<!\w)(?!комп|ноут|пк(?!\w)|windows|винд|систем|сервер|сайт|портал)[\w-]+ не запуска|"
    r"не запуска\w* (?!комп|ноут|windows|винд)[\w-]+|"
    r"после обновлени\w*[^.!?]{0,40}не (?:запуска|открыва|работа)|не (?:запуска|открыва)\w*[^.!?]{0,40}после обновлени"
)
_ASKS_FOR_IT_RE = re.compile(r"(?<!\w)(?:дай|дайте|скаж|подскаж|пришл|скинь|скиньте|сообщ|какой)\w*(?: \S+){0,2} парол")
_VPN_FAILS_RE = re.compile(
    r"(?<!\w)(?:vpn|впн|впэн|forticlient|anyconnect)\w*(?: \S+){0,2} (?:не |отвал|пада|слетает|рвется)")
# A call app has its own scenario; «сервер недоступен» points at the service, not the program.
_NOT_A_LOCAL_PROGRAM_RE = re.compile(
    r"(?<!\w)(?:teams|тимс|zoom|зум|телемост|демонстрац|созвон|встреч|сервер|сервис)")
# «установить слак, а он просит права админа»: an install, not an access request.
_INSTALL_NEEDS_ADMIN_RE = re.compile(
    r"(?:установ|постав|скача)\w*[^.!?]{0,50}(?:прав\w* (?:админ|администратор)|парол\w* (?:админ|администратор))"
)


# «антивирус нашёл/заблокировал/удалил…»: an event, not a question about the antivirus.
_ANTIVIRUS_EVENT_RE = re.compile(
    r"(?:антивирус|защитник)\w*(?: \S+){0,2} (?:наш[её]л|обнаружил|заблокировал|удалил|ругает|орет|"
    r"пишет|сработал|помест|предупрежд|карантин)")
# «аутлук просит пароль»: the program that asks owns the problem, not the Windows password.
_ASKS_PASSWORD_RE = re.compile(
    r"(?<!\w)(outlook|аутлук|почт\w*|vpn|впн|forticlient|anyconnect|teams|zoom|зум)"
    r"(?: \S+){0,2} (?:просит|спрашивает|требует|запрашивает)(?: \S+){0,2} парол")
_ASKER_PLAYBOOK = {"outlook": "email_outlook", "аутлук": "email_outlook", "vpn": "vpn_connection",
                   "впн": "vpn_connection", "forticlient": "vpn_connection", "anyconnect": "vpn_connection",
                   "teams": "video_calls", "zoom": "video_calls", "зум": "video_calls"}


def _password_asker(norm_text: str) -> str | None:
    match = _ASKS_PASSWORD_RE.search(norm_text)
    if not match:
        return None
    word = match.group(1)
    return "email_outlook" if word.startswith("почт") else _ASKER_PLAYBOOK.get(word)


# «не получается зайти на ноутбук»: signing in to the device itself.
_DEVICE_LOGIN_RE = re.compile(
    r"(?:войти|зайти|вход\w*|попасть)(?: \S+){0,2} (?:в|на) (?:рабоч\w* )?"
    r"(?:ноут\w*|комп\w*|windows|учетн\w* запис\w*)")
# «доступы от админки», «пароль и логин у общего ящика»: someone else's or a shared account.
_SOMEONES_CREDENTIALS_RE = re.compile(
    r"(?:логин|парол|доступы|креды)\w*(?: \S+){0,3} (?:от|у|к) (?:\S+ ){0,2}"
    r"(?:админк|сервер|баз|общ|служебн|сайт|роутер|чуж|коллег|ящик)")
# «прошу установить на ноутбук zoom», «нужен notion»: a program to install.
_INSTALL_ASK_RE = re.compile(r"(?:прошу|хочу|нужно|надо|можно)(?: \S+){0,3} (?:установить|поставить)(?!\w)")
_NEED_PROGRAM_RE = re.compile(r"(?<!\w)нужн?(?:ен|на|но|а) ([a-z][\w+.-]+)")
_NOT_PROGRAMS = frozenset("vpn crm wifi wi-fi outlook exchange jira confluence sharepoint 1c bitrix amocrm "
                          "salesforce email e-mail mail".split())


def _software_request(norm_text: str) -> bool:
    if _INSTALL_ASK_RE.search(norm_text):
        return True
    return any(name not in _NOT_PROGRAMS for name in _NEED_PROGRAM_RE.findall(norm_text))


# «система лагает», «комп висит»: the computer itself is slow (a call that lags is not).
_SLOW_SUBJECT_RE = re.compile(
    r"(?<!\w)(?:комп|компьютер|ноут|ноутбук|систем|windows|браузер|хром|chrome)\w*(?: \S+){0,2} "
    r"(?:лага\w*|висит|виснет|тупит)")


# Credentials or codes handed over where something looked off: phishing without a link.
_GIVEAWAY_RE = re.compile(
    r"(?:вв[её]л\w*|указал\w*|продиктова\w*|назва\w*|сказал\w*|сообщил\w*)(?: \S+){0,4} "
    r"(?:парол\w*|логин\w*|данн\w*|код\w*)")
_SUSPICIOUS_RE = re.compile(
    r"странн|подозрит|похож\w* на наш|выглядел\w* как|поддельн|фейк|незнаком|якобы|адрес друг|звонил|позвонил")
_PRETEND_RE = re.compile(r"якобы (?:от|из)(?!\w)")


# «по ссылке просят ввести пароль»: a link that asks for credentials is phishing too.
_LINK_ASKS_RE = re.compile(
    r"(?:по ссылке|перейти|перейдите|пройти по)[^.!?]{0,60}"
    r"(?:ввести|подтвердить|указать|обновить|сообщить) (?:\S+ ){0,2}(?:парол|логин|данн|код|реквизит)")


def _social_engineering(norm_text: str) -> bool:
    if _PRETEND_RE.search(norm_text) or _LINK_ASKS_RE.search(norm_text):
        return True
    return bool(_GIVEAWAY_RE.search(norm_text) and _SUSPICIOUS_RE.search(norm_text))


# «из дома не пускает в корпоративную сеть»: the work network from outside is VPN.
_REMOTE_RE = re.compile(r"из дома|\bдома\b|домашн|удален\w*|из командировки|не в офисе")
_WORK_NETWORK_RE = re.compile(r"(?:корпоративн|рабоч)\w* сет")


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
    reasons = _urgency_reasons(norm)
    if reasons:
        return max_urgency(Urgency.HIGH, playbook.default_urgency), "; ".join(reasons)
    if not_urgent:
        return Urgency.LOW, "пользователь указал, что вопрос не срочный"
    return playbook.default_urgency, "стандартный приоритет для этого типа проблем"


def urgency_signal(text: str) -> tuple[Urgency, str] | None:
    """Only what the words say about urgency, without a scenario's default: «срочно, дайте
    специалиста» is HIGH, «клиенты не могут оплатить» CRITICAL, a plain message None."""
    norm = understand(text)
    if re.search(r"клиент\w* не могут|клиенты жалуются|продажи стоят", norm):
        return Urgency.CRITICAL, "проблема затрагивает клиентов"
    reasons = _urgency_reasons(norm)
    return (Urgency.HIGH, "; ".join(reasons)) if reasons else None


def _urgency_reasons(norm: str) -> list[str]:
    norm = re.sub(_NOT_URGENT_RE, " ", norm)  # "не срочно" must not trigger "срочн"
    reasons = _time_pressure_reasons(norm)
    if _URGENT_WORDS_RE.search(norm):
        reasons.append("пользователь отмечает срочность")
    if _DEADLINE_RE.search(norm):
        reasons.append("срок сегодня")
    if _WAITING_RE.search(norm):
        reasons.append("сотрудник долго ждёт ответа")
    # A bare «ничего не работает» stays ambiguous, not urgent (the case's own example).
    if re.search(r"не могу работать|работа стоит|вообще ничего не|совсем не работает|клиент ждет|"
                 r"вс[её] (?:легло|упало|встало)", norm):
        reasons.append("работа сотрудника остановлена")
    return reasons


_URGENT_WORDS_RE = re.compile(
    r"срочн|горит|горим|аврал|пожар|(?<!\w)sos(?!\w)|asap|асап|немедленно|прямо сейчас|"
    r"очень (?:нужно|надо)|побыстрее|как можно (?:скорее|быстрее)|"
    r"(?:помогите|ответьте|сделайте|почините|пожалуйста)\s+быстрее"
)
# «дедлайн сегодня до 18:00», «отчёт в налоговую — последний день».
_DEADLINE_RE = re.compile(
    r"(?:сегодня|дедлайн)[^.!?]{0,25}до \d{1,2}(?:[:.]\d{2})?|последний день|дедлайн сегодня|сдать сегодня"
)
# «жду уже час», «сколько можно ждать»: waiting long for an answer is urgent in itself.
_WAITING_RE = re.compile(r"жду уже|уже \S+ жду|сколько (?:можно )?ждать|никто не отвечает|до сих пор никто")


# --- fact extraction -------------------------------------------------------

_FACT_PATTERNS: list[tuple[str, str, str]] = [
    # (fact, value, regex over normalized text); first match per fact wins
    ("other_device_works", "yes",
     # Up to two words may sit in between («с телефона CRM открывается»), but never «не».
     r"(с|на|через) (телефон|смартфон|мобильн|друг\w* (компьютер|ноутбук|устройств))\w*,?"
     r"(?: (?!не\b|тоже\b)[\w-]+){0,2},? (все |всё )?(работает|норм\w*|открывается|заходит|пускает|ок)"),
    ("since_when", "вчера работало, сегодня нет", r"вчера (все |всё )?работал\w*"),
    ("since_when", "с сегодняшнего дня", r"с утра|сегодня"),
    ("recurring", "yes", r"\b(опять|снова|в который раз|уже не первый раз)\b"),
    ("vpn", "no", r"без (vpn|впн)|(vpn|впн) (не |от|вы)\w*|не подключ\w* (к )?(vpn|впн)"),
    ("vpn", "yes", r"(через|по|подключен\w* к|включен\w*) (vpn|впн)|(vpn|впн) (подключен|включен|работает)"),
    # «удаленно», not «к удаленному серверу»
    ("location", "remote", r"из дома|\bдома\b|удаленк|\bудаленно\b"),
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
    software = _software(text)
    if software:
        facts["software"] = software
    return facts


# «нужно установить visio», «поставьте мне пожалуйста microsoft project», «лицензия на офис».
_INSTALL_RE = re.compile(
    r"(?:установ(?:ить|ите)|постав(?:ить|ьте)|лицензи\w*\s+на)\s+((?:\S+\s*){1,4})", re.IGNORECASE)
_NOT_A_NAME = frozenset("мне мой мою нам пожалуйста плиз программу программа приложение софт на в во для "
                        "рабочий рабочую рабочем компьютер комп ноутбук новый новую".split())


def _software(text: str) -> str | None:
    """The program asked for: up to two words after the install verb, without filler."""
    match = _INSTALL_RE.search(text)
    if not match:
        return None
    words = [w.strip(",.!?;:«»\"") for w in match.group(1).split()]
    words = list(dropwhile(lambda w: w.lower() in _NOT_A_NAME, words))
    name = list(takewhile(lambda w: w and w.lower() not in _NOT_A_NAME, words))[:2]
    return " ".join(name)[:MAX_FREE_TEXT_FACT] or None


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
