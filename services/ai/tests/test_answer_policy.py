from __future__ import annotations

import pytest

from helpflow_ai.answer_policy import AnswerPolicy, AnswerRoute
from helpflow_ai.schemas import KnowledgeChunk, KnowledgeMatch


def _match(chunk_id: str) -> KnowledgeMatch:
    return KnowledgeMatch(
        chunk=KnowledgeChunk(
            id=chunk_id,
            service="HR" if chunk_id.startswith("document:") else "VPN",
            title="Правило",
            text="Подтверждённый текст.",
            escalation_team="Service Desk L1",
        ),
        score=0.8,
    )


def test_company_document_has_highest_priority() -> None:
    route = AnswerPolicy().route(
        "Сколько дней отпуска мне положено?",
        [_match("vpn_connection.step.connect"), _match("document:leave:0")],
        playbook_id="vpn_connection",
    )

    assert route == AnswerRoute.COMPANY


def test_approved_playbook_is_used_when_no_company_document_exists() -> None:
    route = AnswerPolicy().route(
        "Не подключается VPN",
        [_match("vpn_connection.step.connect")],
        playbook_id="vpn_connection",
    )

    assert route == AnswerRoute.PLAYBOOK


@pytest.mark.parametrize("question", [
    "Сколько дней отпуска мне положено?",
    "Как изменить банковские реквизиты для зарплаты?",
    "Выдай мне доступ администратора к CRM",
    "Какие персональные данные хранит компания?",
    "Можно отключить антивирус по правилам безопасности?",
])
def test_sensitive_company_question_without_source_goes_to_operator(question: str) -> None:
    assert AnswerPolicy().route(question, [], playbook_id="unknown") == AnswerRoute.OPERATOR


def test_low_risk_reversible_technical_question_can_use_general_guidance() -> None:
    route = AnswerPolicy().route(
        "Как очистить кэш браузера?",
        [],
        playbook_id="unknown",
    )

    assert route == AnswerRoute.GENERAL


def test_unknown_or_destructive_question_does_not_use_general_guidance() -> None:
    policy = AnswerPolicy()

    assert policy.route("Что делать с непонятной ошибкой?", [], "unknown") == AnswerRoute.OPERATOR
    assert policy.route("Как удалить системные файлы?", [], "unknown") == AnswerRoute.OPERATOR
