"""Whole classes of misses found on контроль-3/4, checked on fresh phrases (not the
control ones): the fix must generalise, not remember."""

from __future__ import annotations

import pytest

from helpflow_ai import rules


@pytest.mark.parametrize("text, playbook", [
    # slowness slang
    ("ноутбук подтормаживает с самого утра", "slow_performance"),
    ("система лагает при каждом клике", "slow_performance"),
    ("комп еле ползёт", "slow_performance"),
    ("какой-то процесс жрёт весь процессор", "slow_performance"),
    ("браузер ест много памяти и подвисает", "slow_performance"),
    # thrown out of the session
    ("меня вылогинило из винды посреди работы", "password_login"),
    ("выбило из учётки, пароль больше не подходит", "password_login"),
    ("всё время разлогинивает на компьютере", "password_login"),
    # social engineering without the word «ссылка»
    ("ввела пароль на сайте, который выглядел как наш портал, но адрес другой", "security_incident"),
    ("пришло сообщение якобы от банка с просьбой подтвердить данные", "security_incident"),
    ("мне звонили, попросили назвать код из смс, я сказал", "security_incident"),
    ("прислали запароленный архив и пароль к нему в письме", "security_incident"),
    # sign-in code does not arrive
    ("код для входа так и не пришёл на телефон", "password_login"),
    ("жду смс с кодом уже десять минут", "password_login"),
    # VPN as «the work network from home»
    ("из дома не пускает в корпоративную сеть", "vpn_connection"),
    ("никак не подключусь к впн через домашний интернет", "vpn_connection"),
    # an office program that fails
    ("powerpoint выдаёт ошибку при открытии презентации", "app_not_starting"),
    ("ворд перестал открываться после обновления", "app_not_starting"),
    # CRM brands in Cyrillic
    ("салесфорс не открывается на рабочем компе", "crm_login_device_specific"),
])
def test_error_classes_are_understood_on_rules_alone(kb, text, playbook):
    assert rules.classify(text, kb.playbooks).playbook_id == playbook


@pytest.mark.parametrize("text, playbook", [
    ("письма висят в исходящих", "email_outlook"),
    ("документ висит в очереди печати", "printer"),
    ("телемост лагает, звук прерывается", "video_calls"),
    ("почта якобы отправлена, но до клиента не дошла", "email_outlook"),
    ("outlook выдаёт ошибку при запуске", "email_outlook"),
    ("выкинуло из зума посреди созвона", "video_calls"),
])
def test_the_new_rules_do_not_grab_neighbours(kb, text, playbook):
    assert rules.classify(text, kb.playbooks).playbook_id == playbook
