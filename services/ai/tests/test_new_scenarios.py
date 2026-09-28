"""Scenarios added in answers-v2: 1С sign-in, peripherals, programs that fail, installs."""

from __future__ import annotations

import pytest

from helpflow_ai import DecisionAction, rules


@pytest.mark.parametrize("text, software", [
    ("нужно установить visio", "visio"),
    ("поставьте мне пожалуйста microsoft project", "microsoft project"),
    ("можно мне поставить телеграм на рабочий комп?", "телеграм"),
    ("установите пожалуйста 7-zip", "7-zip"),
])
def test_the_program_to_install_is_noted(text, software):
    assert rules.extract_facts(text).get("software") == software


@pytest.mark.parametrize("text, playbook", [
    ("1с пишет нет свободной лицензии", "onec_login"),
    ("в 1с сегодня опять не хватило лицензий", "onec_login"),
    ("открываю 1с, а базы бухгалтерии в списке нет", "onec_login"),
    ("хочу себе поставить draw.io", "software_install"),
    ("1с тормозит при проведении документов", "slow_performance"),
    ("1с не отвечает, сервер недоступен", "service_unavailable"),
    ("у всех лежит 1с", "mass_incident"),
    ("дайте пароль от 1с администратора", "credentials_request"),
    ("мышка не реагирует", "peripherals"),
    ("клавиатура печатает только английские буквы", "peripherals"),
    ("тимс не запускается, а скоро созвон", "video_calls"),
    ("outlook вылетает при запуске", "email_outlook"),
    ("программа учёта не запускается", "app_not_starting"),
    ("нужно установить visio", "software_install"),
    ("не могу установить соединение с впн", "vpn_connection"),
])
def test_new_scenarios_do_not_steal_old_ones(kb, text, playbook):
    assert rules.classify(text, kb.playbooks).playbook_id == playbook


def test_install_request_ends_with_the_admins_and_names_the_program(simulate):
    sim = simulate("нужно установить visio")
    assert sim.decision.action == DecisionAction.STEP and sim.decision.step.id == "software_catalog"

    decision = sim.step_result("not_helped")

    assert decision.action == DecisionAction.ESCALATE
    assert "«visio»" in decision.message


def test_1c_license_goes_to_1c_admins_after_one_safe_step(simulate):
    sim = simulate("1с пишет нет свободной лицензии")
    assert sim.decision.step.id == "close_1c_everywhere"

    decision = sim.step_result("not_helped")

    assert decision.action == DecisionAction.ESCALATE
    assert decision.escalation_team == "Администраторы 1С"
    assert "Освобождение лицензий 1С на сервере" in decision.message
