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


@pytest.mark.parametrize("text, expected", [
    ("С телефона CRM открывается, с ноутбука нет", "yes"),
    ("с телефона всё работает", "yes"),
    ("через телефон битрикс нормально открывается", "yes"),
    ("с телефона не открывается", None),
    ("с телефона тоже не работает", None),
])
def test_other_device_works_is_found_with_a_word_in_between(text, expected):
    assert rules.extract_facts(text).get("other_device_works") == expected


@pytest.mark.parametrize("text, expected", [
    ("работаю удалённо", "remote"),
    ("сижу дома", "remote"),
    ("не удалось подключиться к удалённому серверу", None),
])
def test_remote_work_is_not_read_from_a_remote_server(text, expected):
    assert rules.extract_facts(text).get("location") == expected

# --- ported from the codex/nlu branch, measured on контроль-3/4 before keeping ---------

@pytest.mark.parametrize("text", [
    "никто в офисе не может зайти в crm",
    "никто из отдела не могут открыть почту",
])
def test_nobody_can_with_words_in_between_is_a_mass_outage(kb, text):
    assert rules.classify(text, kb.playbooks).playbook_id == "mass_incident"


@pytest.mark.parametrize("text, keyword", [
    ("подозрительное письмо с архивом", "подозрительн письм"),
    ("пришла подозрительная ссылка", "подозрительн ссылк"),
])
def test_every_long_word_of_a_phrase_keyword_is_a_stem(text, keyword):
    assert rules.contains(rules.normalize(text), keyword)


@pytest.mark.parametrize("slang, plain", [
    ("учётка залочена", "учетная запись заблокирована"),
    ("инет пропадает", "интернет пропадает"),
    ("впн не конектится", "впн не подключается"),
    ("не пускает в винду", "не пускает в windows"),
])
def test_it_slang_becomes_plain_words(slang, plain):
    assert morph.correct(rules.normalize(slang)) == plain


@pytest.mark.parametrize("text, playbook", [
    ("форти клиент пишет ошибка аутентификации", "vpn_connection"),
    ("инет пропадает каждые десять минут", "network_wifi"),
    ("учётка залочена", "password_login"),
])
def test_slang_requests_reach_their_scenario_on_rules_alone(kb, text, playbook):
    assert rules.classify(text, kb.playbooks).playbook_id == playbook


def test_typos_inside_examples_do_not_become_vocabulary(kb):
    from helpflow_ai.schemas import Playbook

    typo_example = Playbook(id="typo_demo", title="Пароль", service="Учётная запись", keywords=["пароль"],
                            examples=["пороль слетел", "пачта не работает"])
    morph.use_playbooks([*kb.playbooks, typo_example])
    try:
        assert morph.correct("пороль") == "пароль"
        assert morph.correct("пачта") == "почта"
    finally:
        morph.use_playbooks(kb.playbooks)
