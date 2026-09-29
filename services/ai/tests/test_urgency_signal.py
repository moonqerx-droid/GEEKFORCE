"""Urgency the employee states in any message, without a scenario's default level."""

import pytest

from helpflow_ai import rules
from helpflow_ai.schemas import Urgency


@pytest.mark.parametrize("text", [
    "срочно дайте мне специалиста", "СРОЧНО!!!", "очень надо, помогите", "аврал, ничего не работает",
    "дедлайн сегодня до 18:00", "помогите быстрее", "SOS не могу войти", "пожар, всё легло",
    "отчёт в налоговую сегодня последний день", "жду уже час, ответьте",
    "у меня созвон с клиентом через 5 минут", "без этого не могу работать",
])
def test_urgent_words_are_heard(text):
    assert rules.urgency_signal(text)[0] == Urgency.HIGH


@pytest.mark.parametrize("text", [
    "скорее всего проблема в принтере", "не срочно", "на следующей неделе посмотрите",
    "комп стал работать быстрее", "сегодня принтер не печатает", "дайте специалиста",
])
def test_ordinary_words_are_not_urgency(text):
    assert rules.urgency_signal(text) is None


def test_clients_affected_is_critical():
    assert rules.urgency_signal("позовите человека, клиенты не могут оплатить")[0] == Urgency.CRITICAL
