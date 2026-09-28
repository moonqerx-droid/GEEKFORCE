"""One-tap answers to clarifying questions: each button must mean what it says."""

from __future__ import annotations

import pytest

from helpflow_ai.rules import parse_answer
from helpflow_ai.schemas import QuestionKind


def all_questions(kb):
    for playbook in kb.playbooks:
        for question in playbook.questions:
            yield playbook.id, question


def test_yes_no_questions_offer_yes_no_and_dont_know(engine, kb):
    playbook_id, question = next(
        (pid, q) for pid, q in all_questions(kb) if q.kind == QuestionKind.YES_NO and not q.invert
    )
    assert engine.quick_replies(playbook_id, question.fact) == ["Да", "Нет", "Не знаю"]


def test_every_reply_parses_back_to_its_own_answer(engine, kb):
    checked = 0
    for playbook_id, question in all_questions(kb):
        replies = engine.quick_replies(playbook_id, question.fact)
        if question.kind == QuestionKind.TEXT:
            assert replies == []
            continue
        if question.kind == QuestionKind.YES_NO:
            yes, no = ("no", "yes") if question.invert else ("yes", "no")
            expected = [yes, no, "unknown"]
        else:
            expected = [*question.options.keys(), *(["unknown"] if question.offer_dont_know else [])]
        assert [parse_answer(question, reply) for reply in replies] == expected, (playbook_id, question.fact, replies)
        checked += 1
    assert checked >= 5


def test_choice_replies_read_as_answers_not_as_internal_codes(engine):
    replies = engine.quick_replies("email_outlook", "mail_client")
    assert replies[:2] == ["В программе Outlook", "В браузере"]


@pytest.mark.parametrize("playbook_id, fact", [("email_outlook", "error_text"), ("email_outlook", "nope"), ("missing", "x")])
def test_free_text_and_unknown_questions_have_no_buttons(engine, playbook_id, fact):
    assert engine.quick_replies(playbook_id, fact) == []
