from datetime import timedelta

from app.core.security import utc_now
from app.models.auth import EmailToken, User
from app.repositories.auth import AuthRepository


def test_repository_normalizes_email_lookup(db_session):
    repository = AuthRepository(db_session)
    user = User(first_name="Анна", last_name="Иванова", email="anna@example.ru",
                department="it", password_hash="hash", role="employee")
    repository.add_user(user)
    assert repository.get_user_by_email(" ANNA@EXAMPLE.RU ").id == user.id


def test_email_token_is_consumed_only_once(db_session):
    repository = AuthRepository(db_session)
    user = User(first_name="Анна", last_name="Иванова", email="anna@example.ru",
                department="it", password_hash="hash", role="employee")
    repository.add_user(user)
    token = EmailToken(user_id=user.id, purpose="verify_email", token_hash="a" * 64,
                       expires_at=utc_now() + timedelta(hours=1))
    repository.add_email_token(token)

    assert repository.consume_email_token("a" * 64, "verify_email") is not None
    assert repository.consume_email_token("a" * 64, "verify_email") is None
