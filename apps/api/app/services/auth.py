from datetime import timedelta
from html import escape
from urllib.parse import quote

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.security import hash_password, hash_token, new_token, utc_now, verify_password
from app.models.auth import AuthSession, EmailToken, User
from app.repositories.auth import AuthRepository
from app.schemas.auth import EmployeeRegister, LoginRequest, OperatorRegister, ResetPasswordRequest
from app.services.email import EmailPayload, EmailSender


class AuthError(Exception):
    pass


class DuplicateEmail(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


class EmailNotVerified(AuthError):
    pass


class InvalidOrExpiredToken(AuthError):
    pass


class InvalidInvite(AuthError):
    pass


class EmailDeliveryFailed(AuthError):
    def __init__(self, user: User):
        super().__init__("email delivery failed")
        self.user = user


class AuthService:
    def __init__(self, repository: AuthRepository, email_sender: EmailSender, app_public_url: str):
        self.repository = repository
        self.email_sender = email_sender
        self.app_public_url = app_public_url.rstrip("/")

    def register_employee(self, payload: EmployeeRegister) -> User:
        return self._register(payload, "employee")

    def register_operator(self, payload: OperatorRegister) -> User:
        if self.repository.consume_invite(hash_token(payload.invite_token), payload.email) is None:
            raise InvalidInvite()
        return self._register(payload, "operator")

    def _register(self, payload, role: str) -> User:
        if self.repository.get_user_by_email(payload.email):
            raise DuplicateEmail()
        user = User(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            department=payload.department,
            password_hash=hash_password(payload.password),
            role=role,
        )
        try:
            self.repository.add_user(user)
        except IntegrityError as exc:
            self.repository.session.rollback()
            raise DuplicateEmail() from exc
        try:
            self._send_action(user, "verify_email")
        except Exception as exc:
            raise EmailDeliveryFailed(user) from exc
        return user

    def _send_action(self, user: User, purpose: str) -> None:
        self.repository.invalidate_email_tokens(user.id, purpose)
        raw_token = new_token()
        lifetime = timedelta(hours=24 if purpose == "verify_email" else 1)
        token = EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw_token),
            expires_at=utc_now() + lifetime,
        )
        self.repository.add_email_token(token)
        page = "verify-email" if purpose == "verify_email" else "reset-password"
        action_url = f"{self.app_public_url}/{page}?token={quote(raw_token)}"
        safe_name = escape(user.first_name)
        if purpose == "verify_email":
            subject = "Подтвердите email в HelpFlow"
            intro = "Подтвердите адрес, чтобы начать работу с HelpFlow. Ссылка действует 24 часа."
        else:
            subject = "Восстановление пароля HelpFlow"
            intro = "Используйте ссылку для смены пароля. Она действует 1 час."
        self.email_sender.send(EmailPayload(
            recipient=user.email,
            subject=subject,
            text=f"Здравствуйте, {user.first_name}!\n\n{intro}\n\n{action_url}",
            html=f"<p>Здравствуйте, {safe_name}!</p><p>{escape(intro)}</p><p><a href=\"{escape(action_url)}\">Продолжить</a></p>",
            action_url=action_url,
        ))

    def resend_verification(self, email: str) -> None:
        user = self.repository.get_user_by_email(email)
        if user and user.email_verified_at is None:
            self._send_action(user, "verify_email")

    def verify_email(self, raw_token: str) -> User:
        token = self.repository.consume_email_token(hash_token(raw_token), "verify_email")
        if token is None:
            raise InvalidOrExpiredToken()
        user = self.repository.get_user(token.user_id)
        if user is None:
            raise InvalidOrExpiredToken()
        user.email_verified_at = utc_now()
        self.repository.session.commit()
        return user

    def request_password_reset(self, email: str) -> None:
        user = self.repository.get_user_by_email(email)
        if user and user.is_active:
            self._send_action(user, "reset_password")

    def reset_password(self, payload: ResetPasswordRequest) -> None:
        token = self.repository.consume_email_token(hash_token(payload.token), "reset_password")
        if token is None:
            raise InvalidOrExpiredToken()
        user = self.repository.get_user(token.user_id)
        if user is None:
            raise InvalidOrExpiredToken()
        user.password_hash = hash_password(payload.password)
        self.repository.revoke_all_sessions(user.id)
        self.repository.session.commit()

    def login(self, payload: LoginRequest, *, user_agent: str | None = None, ip_hash: str | None = None):
        user = self.repository.get_user_by_email(payload.email)
        if user is None or not user.is_active or not verify_password(user.password_hash, payload.password):
            raise InvalidCredentials()
        if user.email_verified_at is None:
            raise EmailNotVerified()
        settings = get_settings()
        raw_token = new_token()
        ttl = timedelta(days=settings.remembered_session_ttl_days) if payload.remember_me else timedelta(hours=settings.session_ttl_hours)
        session = AuthSession(user_id=user.id, token_hash=hash_token(raw_token), expires_at=utc_now() + ttl,
                              user_agent=user_agent, ip_hash=ip_hash)
        self.repository.add_session(session)
        user.last_login_at = utc_now()
        self.repository.session.commit()
        return user, raw_token, session.expires_at

    def logout(self, raw_token: str) -> None:
        session = self.repository.get_session_by_token_hash(hash_token(raw_token))
        if session is not None and session.revoked_at is None:
            self.repository.revoke_session(session)
