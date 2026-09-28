"""Typos and word forms must not change what the assistant understands."""

from __future__ import annotations

import pytest

from helpflow_ai import rules
from helpflow_ai.understanding import morph


@pytest.fixture(autouse=True)
def vocabulary(kb):
    morph.use_playbooks(kb.playbooks)


@pytest.mark.parametrize("typed, meant", [
    ("открыватся", "открывается"),
    ("ранботало", "работало"),
    ("сигодня", "сегодня"),
    ("пароьл", "пароль"),
    ("принтр", "принтер"),
    ("пичатает", "печатает"),
    ("запрешен", "запрещен"),
])
def test_obvious_typos_are_corrected(typed, meant):
    assert morph.correct(typed) == meant


@pytest.mark.parametrize("text", [
    "ошибка 0x80070005",
    "outlook exchange",
    "Контур.Диадок",
    "не работает",
    "пишет «сессия истекла»",
])
def test_known_words_codes_and_latin_are_left_alone(text):
    assert morph.correct(rules.normalize(text)) == rules.normalize(text)


def test_keywords_match_other_word_forms(kb):
    printer = kb.get("printer")
    assert rules.score_playbook(rules.normalize("документ висит в очереди печати"), printer) > 0


def test_request_with_typos_is_classified_like_the_clean_one(kb):
    clean = rules.classify("Вчера всё работало, сегодня не могу зайти в систему с ноутбука, а с телефона открывается", kb.playbooks)
    typos = rules.classify("Вчера всё ранботало, сигодня не могу зайти в систему с ноутбука, а с телефона открыватся", kb.playbooks)
    assert typos.playbook_id == clean.playbook_id == "crm_login_device_specific"
