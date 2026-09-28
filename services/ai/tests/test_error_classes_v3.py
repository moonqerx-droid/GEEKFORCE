"""Error classes found on контроль-5 (answers-v3), checked on fresh phrases only."""

from __future__ import annotations

import pytest

from helpflow_ai import rules
from helpflow_ai.understanding import morph


@pytest.mark.parametrize("text, playbook", [
    # A. a synonym or slang word inside a key phrase
    ("не получается зайти на ноутбук после выходных", "password_login"),
    ("не могу залогиниться в комп, пишет ошибку", "password_login"),
    ("программы открываются целую вечность", "slow_performance"),
    ("скиньте доступы от сервера базы", "credentials_request"),
    # B. two scenarios, the context decides
    ("антивирус удалил файл из вложения", "security_incident"),
    ("защитник windows нашёл угрозу в загрузках", "security_incident"),
    ("1с требует пароль, а я не знаю какой", "onec_login"),
    ("в письме просят перейти по ссылке и подтвердить пароль от почты", "security_incident"),
    # C. words in between, another order
    ("ни у кого в отделе продаж не работает почта", "mass_incident"),
    ("какой пароль и логин у общего ящика отдела", "credentials_request"),
    ("прошу установить на ноутбук программу zoom", "software_install"),
    ("не удаётся установить обновление приложения, выдаёт ошибку", "app_not_starting"),
    # D. missing words of a class
    ("компьютер заблокирован, требуют выкуп в биткоинах", "security_incident"),
    ("внутренний сайт компании не открывается ни на одном устройстве", "service_unavailable"),
    ("вики не грузится", "service_unavailable"),
    ("нужен notion для работы с командой", "software_install"),
    # E. a lemma must not merge «I» and «they»
    ("не вижу общую папку в проводнике", "access_rights"),
])
def test_error_classes_on_fresh_phrases(kb, text, playbook):
    assert rules.classify(text, kb.playbooks).playbook_id == playbook


@pytest.mark.parametrize("text, playbook", [
    ("аутлук просит пароль каждый час", "email_outlook"),
    ("outlook просит ввести пароль снова и снова", "email_outlook"),
    ("база 1с не открывается, сервер не найден", "service_unavailable"),
    ("у меня нет доступа к общему диску", "access_rights"),
    ("забыл пароль от своей учётки", "password_login"),
    ("нужен vpn для работы из дома", "vpn_connection"),
    ("не могу установить соединение с впн", "vpn_connection"),
    ("меня не видят на созвоне", "video_calls"),
    ("впн просит пароль при каждом подключении", "vpn_connection"),
    ("письмо не отправляется, выдаёт ошибку", "email_outlook"),
])
def test_neighbours_keep_their_scenario(kb, text, playbook):
    assert rules.classify(text, kb.playbooks).playbook_id == playbook


def test_person_is_kept_when_matching_verbs():
    morph.use_playbooks([])
    assert morph.lemmatize_verbs_with_person("не вижу") != morph.lemmatize_verbs_with_person("не видят")
    assert morph.lemmatize_verbs_with_person("не работает") == morph.lemmatize_verbs_with_person("не работают")
