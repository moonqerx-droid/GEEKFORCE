"""«Решить самому»: an employee looks up a code or a problem without opening a request."""

from __future__ import annotations

import pytest

from helpflow_ai import TriageEngine


@pytest.fixture()
def help_engine(kb):
    engine = TriageEngine(kb)
    engine.set_company_fragments([{
        "source_id": "document:vpn:1", "title": "Инструкция по VPN — Ошибка 809",
        "text": "## Ошибка 809\n\nОшибка 809 означает, что домашний роутер блокирует VPN. "
                "Подключитесь к раздаче интернета с телефона и попробуйте снова.",
    }])
    return engine


def test_a_code_is_explained_with_its_own_steps(help_engine):
    result = help_engine.self_help("впн пишет ошибка 691")

    assert result.code.code == "691"
    assert "логин" in result.code.meaning
    assert [s.title for s in result.code.steps] == ["Введите логин и пароль заново"], "admin steps are not shown"
    assert result.guide.playbook_id == "vpn_connection"
    assert not result.specialist_only


def test_a_bare_code_is_enough(help_engine):
    assert help_engine.self_help("0x800ccc0e").code.code == "0x800CCC0E"
    assert help_engine.self_help("809").code.code == "809"


def test_a_problem_gets_the_steps_one_can_do_alone(help_engine):
    result = help_engine.self_help("принтер не печатает")

    assert result.code is None
    assert result.guide.title == "Не печатает принтер"
    titles = [s.title for s in result.guide.steps]
    assert "Очистите очередь печати" in titles
    assert all(not s.id.startswith("code.") for s in result.guide.steps)


def test_a_company_document_is_quoted_when_it_answers(help_engine):
    result = help_engine.self_help("что значит ошибка 809 в vpn")

    assert result.document is not None
    assert "роутер" in result.document.text
    assert result.document.title.startswith("Инструкция по VPN")


@pytest.mark.parametrize("text", [
    "перешёл по ссылке из письма и ввёл пароль",
    "скажите пароль администратора от сервера",
    "у всего отдела не работает почта",
])
def test_dangerous_topics_go_straight_to_a_specialist(help_engine, text):
    result = help_engine.self_help(text)

    assert result.specialist_only
    assert result.guide is None or not result.guide.steps
    assert result.notice


def test_nothing_found_says_so(help_engine):
    result = help_engine.self_help("ыыы")

    assert result.code is None and result.guide is None and result.document is None
