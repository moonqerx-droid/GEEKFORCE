from app.repositories.conversations import ConversationRepository


def test_repository_preserves_message_history(db_session):
    repository = ConversationRepository(db_session)
    item = repository.create()

    repository.add_message(item.id, role="user", content="Первая")
    repository.add_message(item.id, role="assistant", content="Вторая")

    loaded = repository.get(item.id)
    assert [message.content for message in loaded.messages] == ["Первая", "Вторая"]


def test_repository_returns_none_for_unknown_id(db_session):
    repository = ConversationRepository(db_session)

    assert repository.get("missing") is None


def test_repository_preserves_step_outcome(db_session):
    repository = ConversationRepository(db_session)
    item = repository.create()

    repository.add_step_result(
        item.id,
        code="check_vpn",
        instruction="Проверьте VPN",
        outcome="not_helped",
    )

    loaded = repository.get(item.id)
    assert loaded.steps[0].position == 0
    assert loaded.steps[0].outcome == "not_helped"
