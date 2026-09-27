from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import utc_now
from app.models.auth import AuthSession, EmailToken, OperatorInvite, User


class AuthRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_user(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        return self.session.scalar(select(User).where(User.email == normalized))

    def add_user(self, user: User) -> User:
        user.email = user.email.strip().lower()
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def add_session(self, auth_session: AuthSession) -> AuthSession:
        self.session.add(auth_session)
        self.session.commit()
        self.session.refresh(auth_session)
        return auth_session

    def get_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return self.session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))

    def revoke_session(self, auth_session: AuthSession) -> None:
        auth_session.revoked_at = utc_now()
        self.session.commit()

    def revoke_all_sessions(self, user_id: str, *, except_token_hash: str | None = None) -> None:
        conditions = [AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)]
        if except_token_hash is not None:
            conditions.append(AuthSession.token_hash != except_token_hash)
        self.session.execute(update(AuthSession).where(*conditions).values(revoked_at=utc_now()))
        self.session.commit()

    def add_email_token(self, token: EmailToken) -> EmailToken:
        self.session.add(token)
        self.session.commit()
        self.session.refresh(token)
        return token

    def invalidate_email_tokens(self, user_id: str, purpose: str) -> None:
        self.session.execute(
            update(EmailToken)
            .where(
                EmailToken.user_id == user_id,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
            )
            .values(used_at=utc_now())
        )
        self.session.commit()

    def consume_email_token(
        self, token_hash: str, purpose: str, *, user_id: str | None = None,
    ) -> EmailToken | None:
        conditions = [
                EmailToken.token_hash == token_hash,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > utc_now(),
        ]
        if user_id is not None:
            conditions.append(EmailToken.user_id == user_id)
        token = self.session.scalar(select(EmailToken).where(*conditions))
        if token is None:
            return None
        token.used_at = utc_now()
        self.session.commit()
        return token

    def consume_invite(self, token_hash: str, email: str) -> OperatorInvite | None:
        invite = self.session.scalar(
            select(OperatorInvite).where(
                OperatorInvite.token_hash == token_hash,
                OperatorInvite.email == email.strip().lower(),
                OperatorInvite.used_at.is_(None),
                OperatorInvite.expires_at > utc_now(),
            )
        )
        if invite is None:
            return None
        invite.used_at = utc_now()
        self.session.commit()
        return invite
