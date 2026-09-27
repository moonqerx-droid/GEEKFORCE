from datetime import timedelta

from app.core.security import utc_now
from app.models.auth import AuthSession, EmailToken, OperatorInvite, User
from app.models.conversation import Conversation


def test_user_session_tokens_and_owned_conversation_persist(db_session):
    user = User(
        first_name="Анна",
        last_name="Иванова",
        email="anna@example.ru",
        department="it",
        password_hash="hash",
        role="employee",
    )
    db_session.add(user)
    db_session.flush()

    conversation = Conversation(owner_id=user.id)
    session = AuthSession(
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=utc_now() + timedelta(hours=12),
    )
    token = EmailToken(
        user_id=user.id,
        purpose="verify_email",
        token_hash="b" * 64,
        expires_at=utc_now() + timedelta(hours=1),
    )
    invite = OperatorInvite(
        email="operator@example.ru",
        token_hash="c" * 64,
        expires_at=utc_now() + timedelta(days=1),
    )
    db_session.add_all([conversation, session, token, invite])
    db_session.commit()

    assert conversation.owner.email == "anna@example.ru"
    assert session.user.role == "employee"
    assert token.user_id == user.id
    assert invite.used_at is None
