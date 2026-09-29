"""Asking for a person, however it is worded, goes straight to a specialist."""

import pytest

from helpflow_ai import rules


@pytest.mark.parametrize("text", [
    "срочно дайте мне специалиста", "СРОЧНО СПЕЦИАЛИСТА", "оператора!", "срочно нужен человек",
    "позовите специалиста срочно", "соедините с оператором, горит", "специалиста пожалуйста, очень срочно",
    "живого человека дайте", "хочу поговорить с человеком", "специалист нужен", "человека!",
])
def test_asking_for_a_person_is_recognised(text):
    assert rules.conversation_intent(text) == "operator"


@pytest.mark.parametrize("text", [
    "специалист сказал перезагрузить компьютер", "не работает поддержка сайта",
    "человек не может войти в crm", "принтер не печатает, срочно", "срочно",
])
def test_other_messages_are_not_a_request_for_a_person(text):
    assert rules.conversation_intent(text) != "operator"
