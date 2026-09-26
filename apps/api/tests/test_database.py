from app.models.conversation import Conversation, Message, TroubleshootingStep


def test_conversation_and_messages_persist(db_session):
    conversation = Conversation(status="NEW")
    conversation.messages.append(Message(role="user", content="Не работает CRM"))
    conversation.steps.append(
        TroubleshootingStep(
            code="check_vpn",
            instruction="Проверьте VPN",
            outcome="not_helped",
            position=0,
        )
    )

    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)

    assert conversation.id is not None
    assert conversation.messages[0].content == "Не работает CRM"
    assert conversation.steps[0].outcome == "not_helped"
