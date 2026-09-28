"""Meaning-based matching corrects keywords only when it is clearly more certain."""

from __future__ import annotations

import pytest

from helpflow_ai import TriageEngine


class FakeIndex:
    """Stands in for the embedding model: returns a fixed ranking per text."""

    def __init__(self, rankings):
        self.rankings = rankings

    def rank(self, text):
        return self.rankings.get(text)


def engine_with(kb, rankings):
    return TriageEngine(kb, semantic=FakeIndex(rankings))


def test_meaning_rescues_slang_the_keywords_miss(kb):
    engine = engine_with(kb, {"комп жутко тупит": [("slow_performance", 0.95), ("printer", 0.62)]})
    assert engine.analyze("комп жутко тупит").recommended_playbook == "slow_performance"


def test_meaning_overrides_a_weak_keyword_match_by_a_clear_margin(kb):
    text = "компютер не видит принтер"
    engine = engine_with(kb, {text: [("printer", 0.99), ("slow_performance", 0.68)]})
    assert engine.analyze(text).recommended_playbook == "printer"


def test_a_tiny_lead_does_not_override_the_keywords(kb):
    text = "в офисе нет интернета на моём компе, у соседа есть"
    engine = engine_with(kb, {text: [("vpn_connection", 0.81), ("network_wifi", 0.79)]})
    assert engine.analyze(text).recommended_playbook == "network_wifi"


def test_keyword_safety_scenarios_are_never_overridden(kb):
    text = "антивирус ругается на файл из почты, я его открыл"
    engine = engine_with(kb, {text: [("email_outlook", 0.99), ("security_incident", 0.5)]})
    assert engine.analyze(text).recommended_playbook == "security_incident"


def test_a_mass_outage_is_not_inferred_from_meaning_alone(kb):
    text = "в офисе нет интернета на моём компе"
    engine = engine_with(kb, {text: [("mass_incident", 0.95), ("network_wifi", 0.6)]})
    assert engine.analyze(text).recommended_playbook == "network_wifi"


def test_confident_meaning_can_raise_a_safety_scenario(kb):
    text = "скинь пароль от админки сервера"
    engine = engine_with(kb, {text: [("credentials_request", 0.83), ("password_login", 0.64)]})
    assert engine.analyze(text).recommended_playbook == "credentials_request"


@pytest.mark.parametrize("ranking", [None, []])
def test_without_the_model_the_rules_decide(kb, ranking):
    engine = engine_with(kb, {"принтер не печатает": ranking})
    assert engine.analyze("принтер не печатает").recommended_playbook == "printer"
