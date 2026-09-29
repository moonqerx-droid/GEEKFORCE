#!/usr/bin/env python3
"""Run the jury's first-turn scenarios against a live HelpFlow API."""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import NamedTuple

import httpx


class Case(NamedTuple):
    slug: str
    title: str
    message: str
    statuses: tuple[str, ...]
    answer_kinds: tuple[str, ...]
    playbooks: tuple[str, ...]
    urgency: str | None = None
    assistant_contains: tuple[str, ...] = ()


CASES = (
    Case(
        "case-example",
        "Пример из кейса",
        (
            "У меня опять всё сломалось. Вчера всё работало, сегодня не могу зайти в рабочую "
            "систему. Через телефон открывается, с ноутбука нет. Мне через 20 минут на встречу"
        ),
        ("CLARIFYING", "TROUBLESHOOTING"),
        ("playbook",),
        ("crm_login_device_specific",),
        "high",
    ),
    Case(
        "simple-password",
        "Простое обращение",
        "Забыл пароль от почты",
        ("CLARIFYING", "TROUBLESHOOTING"),
        ("playbook",),
        ("password_login",),
    ),
    Case(
        "ambiguous",
        "Неоднозначное обращение",
        "Ничего не работает",
        ("CLARIFYING",),
        ("playbook",),
        ("unknown",),
    ),
    Case(
        "multiple-symptoms",
        "Несколько симптомов",
        "Outlook не синхронизируется, а ещё в Zoom нет звука и интернет постоянно отваливается",
        ("CLARIFYING", "TROUBLESHOOTING"),
        ("playbook",),
        ("network_wifi",),
        assistant_contains=("outlook", "zoom", "следом"),
    ),
    Case(
        "access-request",
        "Новый доступ",
        "Нужен доступ к папке бухгалтерии на общем диске",
        ("ESCALATED",),
        ("handoff",),
        ("access_rights",),
    ),
    Case(
        "urgent-teams",
        "Срочный звонок",
        "Через 5 минут звонок с клиентом, не запускается Teams, горит!",
        ("TROUBLESHOOTING",),
        ("playbook",),
        ("video_calls",),
        "high",
    ),
    Case(
        "outlook-how-to",
        "Безопасный how-to",
        # A safe how-to no company document covers («автоответ» is in the demo mail rules now).
        "Как закрепить верхнюю строку в Excel?",
        ("TROUBLESHOOTING",),
        ("general",),
        ("unknown", "app_not_starting"),
        assistant_contains=("общая рекомендация",),
    ),
    Case(
        "company-policy",
        "Политика компании",
        "Сколько дней отпуска мне положено?",
        ("ESCALATED", "TROUBLESHOOTING"),
        ("handoff", "document"),
        ("unknown",),
    ),
    Case(
        "phishing",
        "Фишинг",
        "Перешёл по ссылке из странного письма и ввёл пароль на сайте",
        ("ESCALATED",),
        ("handoff",),
        ("security_incident",),
        "critical",
        ("отключ",),
    ),
)


def assistant_message(state: dict) -> dict:
    return next(
        (message for message in reversed(state.get("messages", [])) if message.get("role") == "assistant"),
        {},
    )


def validate_case(case: Case, state: dict) -> list[str]:
    assistant = assistant_message(state)
    answer_kind = assistant.get("answer_kind") or state.get("answer_kind")
    content = str(assistant.get("content", "")).casefold()
    errors = []
    if state.get("status") not in case.statuses:
        errors.append(f"status={state.get('status')!r}, ожидалось {case.statuses}")
    if answer_kind not in case.answer_kinds:
        errors.append(f"answer_kind={answer_kind!r}, ожидалось {case.answer_kinds}")
    if state.get("playbook_id") not in case.playbooks:
        errors.append(f"playbook={state.get('playbook_id')!r}, ожидалось {case.playbooks}")
    if case.urgency and state.get("urgency") != case.urgency:
        errors.append(f"urgency={state.get('urgency')!r}, ожидалось {case.urgency!r}")
    missing = [fragment for fragment in case.assistant_contains if fragment.casefold() not in content]
    if missing:
        errors.append(f"ответ не содержит: {', '.join(missing)}")
    return errors


def validate_document_probe(state: dict) -> list[str]:
    assistant = assistant_message(state)
    answer_kind = assistant.get("answer_kind") or state.get("answer_kind")
    if answer_kind != "document":
        return [f"answer_kind={answer_kind!r}, ожидалось 'document'"]
    citations = assistant.get("citations") or []
    if not citations:
        return ["нет цитаты корпоративного документа"]
    if not all(str(item.get("source_id", "")).startswith("document:") for item in citations):
        return ["источник цитаты не является корпоративным документом"]
    return []


def login(client: httpx.Client, email: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    response.raise_for_status()


def run_question(client: httpx.Client, message: str) -> tuple[dict, float]:
    created = client.post("/api/conversations")
    created.raise_for_status()
    conversation_id = created.json()["id"]
    started = time.perf_counter()
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": message},
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    return response.json(), elapsed_ms


def discover_document_question(
    base_url: str,
    admin_email: str,
    password: str,
    timeout: float,
) -> str | None:
    with httpx.Client(base_url=base_url, timeout=timeout) as admin:
        try:
            login(admin, admin_email, password)
            listing = admin.get("/api/admin/knowledge/documents")
            listing.raise_for_status()
        except httpx.HTTPError:
            return None
        ready = next((item for item in listing.json() if item.get("status") == "ready"), None)
        if ready is None:
            return None
        detail = admin.get(f"/api/admin/knowledge/documents/{ready['id']}")
        detail.raise_for_status()
        chunk = next((item for item in detail.json().get("chunks", []) if item.get("text")), None)
        if chunk is None:
            return None
        words = re.findall(r"[A-Za-zА-Яа-яЁё0-9-]+", chunk["text"])
        terms = " ".join(words[:12])
        return f"Что сказано в документе «{ready['title']}» про {terms}?"


def print_result(title: str, state: dict, elapsed_ms: float, errors: list[str]) -> None:
    assistant = assistant_message(state)
    content = " ".join(str(assistant.get("content", "")).split())
    if len(content) > 180:
        content = content[:177] + "..."
    answer_kind = assistant.get("answer_kind") or state.get("answer_kind") or "—"
    verdict = "OK" if not errors else "FAIL"
    print(
        f"[{verdict}] {title}: {elapsed_ms:.1f} ms | {state.get('status')} | "
        f"{answer_kind} | {content}"
    )
    for error in errors:
        print(f"       ↳ {error}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="ivan@helpflow.demo")
    parser.add_argument("--admin-email", default="admin@helpflow.demo")
    parser.add_argument("--password", default="DemoPass123")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--document-question")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures = 0
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout) as employee:
        try:
            login(employee, args.email, args.password)
        except httpx.HTTPError as error:
            print(f"Не удалось войти демо-сотрудником: {error}", file=sys.stderr)
            return 2

        for case in CASES:
            try:
                state, elapsed_ms = run_question(employee, case.message)
                errors = validate_case(case, state)
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                state, elapsed_ms, errors = {}, 0.0, [f"ошибка API: {error}"]
            print_result(case.title, state, elapsed_ms, errors)
            failures += bool(errors)

        document_question = args.document_question or discover_document_question(
            args.base_url.rstrip("/"), args.admin_email, args.password, args.timeout,
        )
        if document_question:
            try:
                state, elapsed_ms = run_question(employee, document_question)
                errors = validate_document_probe(state)
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                state, elapsed_ms, errors = {}, 0.0, [f"ошибка API: {error}"]
            print_result("Корпоративный документ", state, elapsed_ms, errors)
            failures += bool(errors)
        else:
            print("[SKIP] Корпоративный документ: активных ready-документов нет или админ недоступен")

    print(f"Итог: {len(CASES) + bool(document_question)} проверок, ошибок: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
