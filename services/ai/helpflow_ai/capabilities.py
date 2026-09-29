"""«Что ты умеешь?»: what the assistant can do, built from its scenarios and the documents
the support lead has actually uploaded — a new document shows up here the moment it is ready."""

from __future__ import annotations

from collections.abc import Iterable

# Short names for the scenario list; a scenario missing here is shown by its own title.
_SCENARIO_LABELS = {
    "password_login": "вход в учётную запись и пароль",
    "email_outlook": "почта и Outlook",
    "vpn_connection": "VPN и удалённый доступ",
    "network_wifi": "интернет и Wi-Fi",
    "printer": "принтер и сканер",
    "peripherals": "мышь, клавиатура, монитор",
    "video_calls": "видеозвонки: Teams, Zoom, Телемост",
    "slow_performance": "медленный компьютер или программа",
    "app_not_starting": "программа не запускается или выдаёт ошибку",
    "software_install": "установка программ",
    "access_rights": "доступ к папкам и системам",
    "crm_login_device_specific": "вход в рабочую систему (CRM)",
    "onec_login": "вход в 1С",
    "service_unavailable": "недоступен рабочий сервис или сайт",
}
# Hand-off scenarios are listed separately: there the assistant acts at once, it does not troubleshoot.
_AT_ONCE = ("security_incident", "mass_incident", "credentials_request")

# A sample question for the demo documents; any other document is listed by its title alone.
_DOCUMENT_EXAMPLES = {
    "Отпуска и больничные": "Сколько дней отпуска положено?",
    "Регламент командировок": "Какие суточные за рубежом?",
    "Правила паролей": "Раз в сколько дней менять пароль?",
    "Инструкция по VPN": "Что значит ошибка 809?",
    "Рабочее место и оборудование": "Как получить второй монитор?",
    "Информационная безопасность": "Можно ли подключить найденную флешку?",
    "Офис: пропуска, переговорные, парковка": "Как заказать пропуск гостю?",
    "Программы и доступы": "Как быстро выдают доступ к папке?",
    "Корпоративная почта": "Какой максимальный размер вложения?",
    "Техподдержка: часы работы и сроки": "Как быстро ответят на срочное обращение?",
}


def document_titles(fragment_titles: Iterable[str]) -> list[str]:
    """«Правила паролей — Требования к паролю» → «Правила паролей», each document once."""
    titles: list[str] = []
    for title in fragment_titles:
        name = title.split(" — ", 1)[0].strip()
        if name and name not in titles:
            titles.append(name)
    return sorted(titles)


def describe(playbooks: Iterable, fragment_titles: Iterable[str]) -> str:
    ids = [playbook.id for playbook in playbooks]
    titles = {playbook.id: playbook.title for playbook in playbooks}
    scenarios = [_SCENARIO_LABELS.get(pid, titles[pid].lower()) for pid in ids
                 if pid != "unknown" and pid not in _AT_ONCE]
    lines = [
        "Вот что я умею.",
        "",
        "Разбираю технические проблемы по шагам — по одному шагу, с проверкой результата:",
        *(f"• {name}" for name in scenarios),
        "",
        "Сразу, без шагов, передаю специалисту: подозрение на взлом или фишинг, сбой у многих "
        "коллег, просьбы сообщить чужой или служебный пароль.",
    ]
    documents = document_titles(fragment_titles)
    if documents:
        lines += ["", "Отвечаю на вопросы по документам компании и показываю цитату:"]
        for name in documents:
            example = _DOCUMENT_EXAMPLES.get(name)
            lines.append(f"• {name}" + (f" — например, «{example}»" if example else ""))
    lines += [
        "",
        "Если ответа в документах нет, честно скажу об этом и передам вопрос специалисту — "
        "гадать не буду. Если шаги не помогли, специалист получит всю историю, пересказывать не придётся.",
        "",
        "Просто опишите проблему или задайте вопрос своими словами — можно с опечатками и эмоциями.",
    ]
    return "\n".join(lines)
