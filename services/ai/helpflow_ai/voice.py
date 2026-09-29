"""How the assistant sounds to the employee: plain words, one human sentence where it helps.

Internal team codes («Service Desk L1 (оргтехника)») are for specialists; the employee
reads «специалисту по оргтехнике». A frustrated or recurring complaint gets one short
acknowledgement before the first question or step — once, never on every turn.
"""

from __future__ import annotations

import re

from .answer_policy import AnswerPolicy

# Team code → how to say «передаю …» to the employee.
_TEAM_FOR_EMPLOYEE = {
    "service desk l1": "специалисту поддержки",
    "service desk l1 (оргтехника)": "специалисту по оргтехнике",
    "service desk l2": "инженеру поддержки",
    "service desk l2 (рабочие места)": "инженеру по рабочим местам",
    "service desk l2 (учётные записи)": "специалисту по учётным записям",
    "service desk l2 (учетные записи)": "специалисту по учётным записям",
    "администраторы доступа": "администраторам доступа",
    "администраторы почты": "администраторам почты",
    "администраторы прикладных систем": "администраторам рабочих систем",
    "дежурный инженер": "дежурному инженеру",
    "дежурный инженер (инциденты)": "дежурному инженеру",
    "отдел информационной безопасности": "в отдел информационной безопасности",
    "сетевые администраторы": "сетевым администраторам",
}

_FRUSTRATED = re.compile(
    r"задолбал|достал|бесит|надоел|сколько можно|невозможно работать|кошмар|"
    r"ничего не работает|вообще ничего|опять вс[её]|снова вс[её]|!!!|\?!",
    re.IGNORECASE,
)
_RECURRING = re.compile(r"(?<!\w)(опять|снова|в который раз|уже не первый раз)(?!\w)", re.IGNORECASE)


def to_whom(team: str) -> str:
    """«специалисту по оргтехнике» for «Service Desk L1 (оргтехника)»; unknown codes stay generic."""
    return _TEAM_FOR_EMPLOYEE.get(team.strip().lower(), "специалисту поддержки")


def acknowledgement(text: str) -> str:
    """One sentence that shows the employee was heard, or "" when plain business is best."""
    if _FRUSTRATED.search(text) or _shouting(text):
        return "Понимаю, это выбивает из работы — разберёмся."
    if _RECURRING.search(text) and not AnswerPolicy.is_information_question(text):
        # «Опять не печатает» is a recurring problem; «можно использовать пароль снова?» is a question.
        return "Жаль, что это повторяется — отмечу это для специалиста."
    return ""


def _shouting(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 12 and sum(ch.isupper() for ch in letters) / len(letters) > 0.7
