from __future__ import annotations

import pytest

from helpflow_ai import (
    AnswerKind,
    ConversationContext,
    DecisionAction,
    KnowledgeBase,
    KnowledgeChunk,
    TriageEngine,
)


@pytest.mark.parametrize(("question", "expected_fragment"), [
    (
        "Как настроить автоответ в Outlook на время отпуска?",
        "автоматические ответы",
    ),
    (
        "Как размыть фон во время звонка в Teams?",
        "эффекты",
    ),
    (
        "Как закрепить верхнюю строку в Excel?",
        "закрепить области",
    ),
    (
        "Как распечатать документ в PDF?",
        "печать",
    ),
    (
        "Как сменить обои рабочего стола?",
        "персонализация",
    ),
    (
        "Как архивировать папку в zip?",
        "сжать",
    ),
    (
        "Как добавить общий календарь в Outlook?",
        "календарь",
    ),
])
def test_safe_how_to_gets_labelled_general_guidance(kb, question: str, expected_fragment: str) -> None:
    engine = TriageEngine(kb)
    analysis = engine.analyze(question)

    decision = engine.decide(ConversationContext(
        original_request=question,
        playbook_id=analysis.recommended_playbook,
        urgency=analysis.urgency,
    ))

    assert decision.action == DecisionAction.STEP
    assert decision.answer_kind == AnswerKind.GENERAL
    assert decision.message.startswith("Общая рекомендация — не правило компании.")
    assert expected_fragment in decision.message.casefold()


def test_vpn_how_to_stays_in_approved_playbook(kb) -> None:
    question = "Как подключиться к VPN-клиенту?"
    engine = TriageEngine(kb)
    analysis = engine.analyze(question)

    decision = engine.decide(ConversationContext(
        original_request=question,
        playbook_id=analysis.recommended_playbook,
        urgency=analysis.urgency,
    ))

    assert analysis.recommended_playbook == "vpn_connection"
    assert decision.answer_kind == AnswerKind.PLAYBOOK
    assert decision.step is None or not decision.step.id.startswith("general.")


@pytest.mark.parametrize("question", [
    "Сколько дней отпуска мне положено в этом году?",
    "Как рассчитывается моя зарплата и премия?",
    "Как получить права администратора в CRM?",
    "Как отключить антивирус на рабочем ноутбуке?",
    "Как удалить системные файлы, чтобы освободить место?",
    "Какие персональные данные обо мне хранит компания?",
])
def test_forbidden_unsourced_how_to_goes_to_human(kb, question: str) -> None:
    engine = TriageEngine(kb)
    analysis = engine.analyze(question)

    decision = engine.decide(ConversationContext(
        original_request=question,
        playbook_id=analysis.recommended_playbook,
        urgency=analysis.urgency,
    ))

    assert decision.action == DecisionAction.ESCALATE
    assert decision.answer_kind == AnswerKind.HANDOFF


def test_document_answer_exposes_exact_citation(kb) -> None:
    document = KnowledgeChunk(
        id="document:leave:0",
        service="HR",
        title="Положение об отпусках",
        text="Ежегодный отпуск составляет 28 календарных дней.",
        keywords=["отпуск"],
        escalation_team="HR",
    )
    engine = TriageEngine(KnowledgeBase(kb.playbooks, [*kb.chunks, document]))

    decision = engine.decide(ConversationContext(
        original_request="Сколько дней ежегодного отпуска?",
        playbook_id="unknown",
    ))

    assert decision.answer_kind == AnswerKind.DOCUMENT
    assert [citation.model_dump() for citation in decision.citations] == [{
        "source_id": document.id,
        "title": document.title,
        "quote": document.text,
    }]


def test_runtime_company_fragments_follow_adapter_contract(kb) -> None:
    engine = TriageEngine(kb)
    engine.set_company_fragments([{
        "source_id": "document:travel-policy:3",
        "title": "Положение о командировках",
        "text": "Суточные согласуются до начала командировки.",
    }])

    decision = engine.decide(ConversationContext(
        original_request="Когда согласуются суточные для командировки?",
        playbook_id="unknown",
    ))

    assert decision.answer_kind == AnswerKind.DOCUMENT
    assert decision.citations[0].source_id == "document:travel-policy:3"

    engine.set_company_fragments([])
    without_document = engine.decide(ConversationContext(
        original_request="Когда согласуются суточные для командировки?",
        playbook_id="unknown",
    ))
    assert without_document.answer_kind == AnswerKind.HANDOFF
