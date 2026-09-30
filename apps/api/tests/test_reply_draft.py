"""The specialist's first reply is drafted from the card and from what helped colleagues."""

from app.core.security import utc_now
from app.models.conversation import Conversation, Message, TroubleshootingStep
from tests.test_admin_conversations import add_user


def handed_over(db_session, owner, playbook="vpn_connection", **overrides):
    values = {"status": "ESCALATED", "playbook_id": playbook, "summary": "Не подключается VPN",
              "escalated_at": utc_now(), **overrides}
    conversation = Conversation(workflow_version="triage-v1", owner_id=owner.id, **values)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(Message(conversation_id=conversation.id, role="user", content="впн не работает"))
    return conversation


def test_draft_greets_by_name_lists_what_was_tried_and_says_it_is_urgent(client, db_session):
    employee = add_user(db_session, "emp-draft", "employee")
    conversation = handed_over(db_session, employee, urgency="high", urgency_reason="встреча через 20 минут")
    db_session.add(TroubleshootingStep(conversation_id=conversation.id, code="restart", position=1,
                                       instruction="Перезапустите VPN-клиент. Затем подключитесь снова.",
                                       outcome="not_helped"))
    db_session.commit()

    draft = client.get(f"/api/operator/tickets/{conversation.id}/draft").json()

    assert draft["text"].startswith("Мария, здравствуйте! Это Тест, специалист поддержки.")
    assert "встреча через 20 минут" in draft["text"]
    assert "«Перезапустите VPN-клиент»" in draft["text"]
    assert draft["based_on"] is None


def test_draft_suggests_what_helped_a_colleague_with_the_same_problem(client, db_session):
    employee = add_user(db_session, "emp-draft2", "employee")
    solved = handed_over(db_session, employee, status="RESOLVED", resolved_by="operator", resolved_at=utc_now())
    db_session.add(Message(conversation_id=solved.id, role="operator",
                           content="Обращение закрыто. Итог: Обновлены сертификаты VPN-клиента"))
    current = handed_over(db_session, employee)
    db_session.commit()

    draft = client.get(f"/api/operator/tickets/{current.id}/draft").json()

    assert "В похожем случае помогло: Обновлены сертификаты VPN-клиента." in draft["text"]
    assert draft["based_on"] == solved.id
