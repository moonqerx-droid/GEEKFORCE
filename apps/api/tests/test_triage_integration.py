"""Exercise the production dependency and the teammate's actual knowledge base."""

import pytest


def send(client, cid, text):
    response = client.post(f"/api/conversations/{cid}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_urgent_crm_uses_knowledge_base_and_confirms_resolution(client):
    cid = client.post("/api/conversations").json()["id"]
    first = send(client, cid, "Не могу войти в CRM с ноутбука, через 20 минут встреча")
    assert first["urgency"] == "high"
    assert first["status"] == "CLARIFYING"
    current = send(client, cid, "Ошибка соединения, VPN не подключен")
    assert current["current_step"]["code"] == "connect_vpn"
    result = client.post(f"/api/conversations/{cid}/step-result", json={"outcome": "helped"}).json()
    assert result["status"] == "VERIFYING"
    assert send(client, cid, "Не знаю, проверяю")["status"] == "VERIFYING"
    assert send(client, cid, "Да, заработало")["status"] == "RESOLVED"


@pytest.mark.parametrize("incident_text", ["Перешел по фишинговой ссылке", "CRM не работает у всех коллег"])
def test_critical_incident_escalates_immediately_with_context(client, incident_text):
    cid = client.post("/api/conversations").json()["id"]
    result = send(client, cid, incident_text)
    assert result["status"] == "ESCALATED"
    assert result["urgency"] == "critical"
    assert result["escalation_card"]["original_request"] == incident_text
    assert result["escalation_card"]["recommended_team"]
    assert result["escalation_card"]["current_result"]
    assert client.get("/api/operator/tickets").json()[0]["id"] == cid


def test_failed_confirmation_advances_without_repeating_steps(client):
    cid = client.post("/api/conversations").json()["id"]
    send(client, cid, "CRM не работает, срочно. VPN подключен, ошибка 403")
    current = client.get(f"/api/conversations/{cid}").json()
    if current["status"] == "CLARIFYING":
        current = send(client, cid, "Да")
    seen = set()
    while current["status"] == "TROUBLESHOOTING":
        code = current["current_step"]["code"]
        assert code not in seen
        seen.add(code)
        result = client.post(f"/api/conversations/{cid}/step-result", json={"outcome": "helped"})
        assert result.json()["status"] == "VERIFYING"
        current = send(client, cid, "Нет, не работает")
        assert len(seen) <= 10
    assert current["status"] == "ESCALATED"
    assert current["escalation_card"]["performed_steps"]


def test_cannot_perform_is_translated_and_persisted(client):
    cid = client.post("/api/conversations").json()["id"]
    send(client, cid, "CRM не работает, срочно")
    send(client, cid, "Ошибка 403")
    result = client.post(f"/api/conversations/{cid}/step-result", json={"outcome": "cannot_perform"})
    assert result.status_code == 200
    assert result.json()["completed_steps"][0]["outcome"] == "cannot_perform"


def test_normal_priority_remains_api_compatible(client):
    cid = client.post("/api/conversations").json()["id"]
    result = send(client, cid, "Не работает VPN")
    assert result["urgency"] == "normal"


def test_decision_failure_rolls_back_entire_turn(client, monkeypatch):
    from app.api.routes.conversations import get_triage_engine

    cid = client.post("/api/conversations").json()["id"]
    def fail(context):
        raise RuntimeError("decision unavailable")
    monkeypatch.setattr(get_triage_engine(), "decide", fail)
    with pytest.raises(RuntimeError, match="decision unavailable"):
        send(client, cid, "Не работает CRM")
    result = client.get(f"/api/conversations/{cid}").json()
    assert result["status"] == "NEW"
    assert result["messages"] == []


def test_legacy_conversation_can_continue_after_upgrade(client, db_session):
    from app.models import Conversation

    legacy = Conversation()
    db_session.add(legacy)
    db_session.commit()
    cid = legacy.id
    send(client, cid, "Не работает CRM")
    assert send(client, cid, "Ошибка соединения")["current_step"]["code"] == "check_vpn"


def test_context_survives_a_new_database_session(client, db_session):
    cid = client.post("/api/conversations").json()["id"]
    send(client, cid, "Не работает CRM")
    db_session.expunge_all()
    result = send(client, cid, "Ошибка 403")
    assert result["status"] == "CLARIFYING"
    assert "VPN" in result["messages"][-1]["content"]
    db_session.expunge_all()
    result = send(client, cid, "Нет")
    assert result["known_facts"]["vpn"] == "no"


def test_unknown_confirmation_containing_works_does_not_resolve(client):
    cid = client.post("/api/conversations").json()["id"]
    send(client, cid, "CRM не работает, срочно")
    send(client, cid, "Ошибка 403")
    client.post(f"/api/conversations/{cid}/step-result", json={"outcome": "helped"})
    assert send(client, cid, "Не знаю, работает ли сейчас")["status"] == "VERIFYING"


@pytest.mark.parametrize("followup,playbook", [
    ("Теперь выяснил: CRM не работает у всех коллег", "mass_incident"),
    ("Перед этим перешел по фишинговой ссылке", "security_incident"),
])
def test_critical_information_in_clarification_escalates(client, followup, playbook):
    cid = client.post("/api/conversations").json()["id"]
    original = "Не работает CRM"
    send(client, cid, original)
    result = send(client, cid, followup)
    assert result["status"] == "ESCALATED"
    assert result["playbook_id"] == playbook
    assert result["urgency"] == "critical"
    assert result["escalation_card"]["original_request"] == original
    assert result["escalation_card"]["known_facts"]["critical_update"] == followup


def test_greeting_then_specific_issue_selects_real_playbook(client):
    cid = client.post("/api/conversations").json()["id"]
    greeting = send(client, cid, "Привет")
    assert greeting["status"] == "NEW"
    assert greeting["playbook_id"] is None
    assert greeting["messages"][-1]["content"] == (
        "Привет! Я помогу разобраться с технической проблемой. "
        "Опишите, пожалуйста, что не работает или какое сообщение об ошибке вы видите."
    )
    result = send(client, cid, "Не могу войти в CRM, через 20 минут встреча")
    assert result["playbook_id"] == "crm_login_device_specific"
    assert result["service"] == "CRM"
    assert result["urgency"] == "high"
    assert result["escalation_card"] is None


def test_greeting_with_an_issue_starts_diagnostics_immediately(client):
    cid = client.post("/api/conversations").json()["id"]

    result = send(client, cid, "Привет, не работает VPN")

    assert result["status"] == "CLARIFYING"
    assert result["playbook_id"] == "vpn_connection"


def test_capability_question_does_not_start_fake_diagnostics(client):
    cid = client.post("/api/conversations").json()["id"]

    result = send(client, cid, "Что ты умеешь?")

    assert result["status"] == "NEW"
    assert result["playbook_id"] is None
    assert "опишите проблему" in result["messages"][-1]["content"].lower()
    assert "специалист" in result["messages"][-1]["content"].lower()


def test_thanks_does_not_consume_pending_technical_answer(client):
    cid = client.post("/api/conversations").json()["id"]
    pending = send(client, cid, "Не работает VPN")
    asked_before = list(pending["messages"])

    thanked = send(client, cid, "Спасибо")

    assert thanked["status"] == "CLARIFYING"
    assert thanked["known_facts"] == pending["known_facts"]
    assert "пожалуйста" in thanked["messages"][-1]["content"].lower()
    assert len(thanked["messages"]) == len(asked_before) + 2
    answered = send(client, cid, "Пишет ошибка соединения")
    assert "соединения" in answered["known_facts"]["error_text"]


def test_natural_operator_request_escalates_from_active_dialogue(client):
    cid = client.post("/api/conversations").json()["id"]
    send(client, cid, "Не работает VPN")

    result = send(client, cid, "Позовите, пожалуйста, живого специалиста")

    assert result["status"] == "ESCALATED"
    assert result["escalation_card"]["escalation_reason"] == "пользователь запросил специалиста"
    assert "передано специалисту" in result["messages"][-1]["content"].lower()
