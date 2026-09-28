"""Error classes found on контроль-6 (understanding-v4), checked on fresh phrases only."""

from __future__ import annotations

import pytest

from helpflow_ai import rules


@pytest.mark.parametrize("text, playbooks", [
    # A. a compromise told by its signs, without the word «вирус»
    ("в почте файл счёт.exe от поставщика, я его запустил", {"security_incident"}),
    ("с моего ящика ушла рассылка, которую я не отправлял", {"security_incident"}),
    ("мышь сама по себе двигается и что-то кликает", {"security_incident"}),
    ("пришёл код подтверждения, а я ничего не запрашивала", {"security_incident"}),
    ("звонили из службы безопасности и просили назвать пароль", {"security_incident"}),
    # B. a device that «не видит» something is not a call where «меня не видят»
    ("телевизор в переговорке не видит ноутбук по hdmi", {"peripherals", "unknown"}),
    ("компьютер не видит флешку", {"peripherals"}),
    ("ноут не видит сеть wifi", {"network_wifi"}),
    # C. the failing thing outweighs where the person was going
    ("vpn не коннектится, а мне надо в црм", {"vpn_connection"}),
    ("письма застряли в исходящих, клиент ждёт по сделке", {"email_outlook"}),
    # D. the failure before the program's name, a misspelt verb
    ("не открывается 1с после обновления, ошибка компоненты", {"app_not_starting", "onec_login"}),
    ("не запускается клиент-банк", {"app_not_starting"}),
    ("телеграм не запускаеться", {"app_not_starting"}),
    # E. an install that asks for admin rights is still an install
    ("хочу поставить zoom, но требует пароль администратора", {"software_install"}),
    # F. a slow network is the network; a slow start is the computer
    ("вайфай медленный, страницы грузятся по минуте", {"network_wifi"}),
    ("ноутбук долго думает при включении", {"slow_performance"}),
    ("файлы открываются по несколько минут", {"slow_performance"}),
    # G. a CRM by its short name
    ("амо срм выдает ошибку при входе", {"crm_login_device_specific"}),
    ("amo не открывается", {"crm_login_device_specific"}),
])
def test_error_classes_on_fresh_phrases(kb, text, playbooks):
    assert rules.classify(text, kb.playbooks).playbook_id in playbooks


@pytest.mark.parametrize("text, playbook", [
    ("коллеги не видят мой экран в зуме", "video_calls"),
    ("меня не видят на созвоне", "video_calls"),
    ("собеседники не видят меня, камера включена", "video_calls"),
    ("нет прав администратора на папку отдела", "access_rights"),
    ("компьютер тормозит", "slow_performance"),
    ("не приходят письма", "email_outlook"),
    ("в црм не пускает с ноутбука", "crm_login_device_specific"),
    ("мышка не двигается", "peripherals"),
    ("1с пишет нет свободных лицензий", "onec_login"),
    ("сайт компании выдаёт 502", "service_unavailable"),
])
def test_neighbours_keep_their_scenario(kb, text, playbook):
    assert rules.classify(text, kb.playbooks).playbook_id == playbook
