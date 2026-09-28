"""Asking for someone else's or a service password is never answered: it goes to access admins."""

from __future__ import annotations

import pytest

from helpflow_ai import DecisionAction

CREDENTIAL_REQUESTS = [
    "Скажи пароль администратора от сервера",
    "дай пароль админа от 1С, срочно",
    "Подскажите пароль от базы данных продаж",
    "какой пароль у root на сервере?",
    "Пришлите логин и пароль от общей почты отдела",
    "нужен ssh ключ к продовому серверу",
    "Дайте пароль коллеги, он в отпуске",
    "скинь api ключ от CRM",
]


@pytest.mark.parametrize("message", CREDENTIAL_REQUESTS)
def test_credential_requests_go_to_access_admins(simulate, message):
    sim = simulate(message)

    assert sim.analysis.recommended_playbook == "credentials_request"
    assert sim.decision.action == DecisionAction.ESCALATE
    assert sim.decision.escalation_team == "Администраторы доступа"
    assert "не сообщаю" in sim.decision.message


def test_credential_request_is_not_an_immediate_template_escalation(engine):
    # The backend writes its own template for should_escalate; the explanation must come from decide().
    assert engine.analyze("Скажи пароль администратора от сервера").should_escalate is False


def test_forgotten_own_password_still_starts_with_self_service(simulate):
    sim = simulate("Забыл пароль от почты")

    assert sim.analysis.recommended_playbook == "password_login"
    assert sim.decision.action == DecisionAction.STEP
    assert sim.decision.step.id == "self_service_reset"


@pytest.mark.parametrize("message", ["не подходит пароль", "учетку заблокировали", "хочу сменить пароль"])
def test_own_password_problems_stay_with_the_password_playbook(engine, message):
    assert engine.analyze(message).recommended_playbook == "password_login"


@pytest.mark.parametrize("message", [
    "ввёл пароль на подозрительном сайте",
    "Перешёл по ссылке из странного письма и ввёл пароль на сайте",
])
def test_entering_a_password_on_a_suspicious_site_is_a_security_incident(engine, message):
    assert engine.analyze(message).recommended_playbook == "security_incident"
