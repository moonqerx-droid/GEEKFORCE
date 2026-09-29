"""«Что ты умеешь?» lists the scenarios and the company documents that are loaded right now."""

import pytest

from helpflow_ai import TriageEngine, rules


@pytest.mark.parametrize("text", [
    "что ты умеешь?", "Что ты умеешь", "помощь", "/help", "help", "что ты можешь?",
    "на какие вопросы ты отвечаешь?", "какие вопросы тебе можно задать?", "привет, что ты умеешь?",
    "чем можешь помочь?", "о чём тебя можно спросить?",
])
def test_help_phrases_are_recognised(text):
    assert rules.conversation_intent(text) == "help"


@pytest.mark.parametrize("text", ["не работает принтер", "что ты умеешь делать с принтером, он не печатает"])
def test_a_problem_is_not_a_help_request(text):
    assert rules.conversation_intent(text) != "help"


def test_the_answer_lists_scenarios_and_the_loaded_documents(kb):
    engine = TriageEngine(kb)
    engine.set_company_fragments([
        {"source_id": "document:vacation:0", "title": "Отпуска и больничные — Отпуска", "text": "Отпуск — 28 дней."},
        {"source_id": "document:vacation:1", "title": "Отпуска и больничные — Больничные", "text": "Сообщите до 10:00."},
        {"source_id": "document:rules:0", "title": "Положение о премиях", "text": "Премия раз в квартал."},
    ])
    text = engine.capabilities()

    assert "VPN и удалённый доступ" in text and "принтер" in text
    assert text.count("Отпуска и больничные") == 1  # one line per document, not per section
    assert "Сколько дней отпуска положено?" in text
    assert "• Положение о премиях" in text  # an uploaded document without a sample question
    assert "unknown" not in text


def test_without_documents_the_answer_says_nothing_about_them(kb):
    assert "документам компании" not in TriageEngine(kb).capabilities()
