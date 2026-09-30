from datetime import timedelta, timezone
from html import escape
import secrets
from urllib.parse import quote

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.security import hash_password, hash_token, new_token, utc_now, verify_password
from app.models.auth import AuthSession, EmailToken, User
from app.repositories.auth import AuthRepository
from app.schemas.auth import ChangePasswordRequest, EmployeeRegister, LoginRequest, OperatorRegister, ResetPasswordRequest
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


class InvalidCurrentPassword(AuthError):
    pass


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
        # The invite link itself proves the operator controls this mailbox.
        return self._register(payload, "operator", verified=True)

    def _register(self, payload, role: str, *, verified: bool = False) -> User:
        if self.repository.get_user_by_email(payload.email):
            raise DuplicateEmail()
        user = User(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            department=payload.department,
            password_hash=hash_password(payload.password),
            role=role,
            email_verified_at=utc_now() if verified else None,
        )
        try:
            self.repository.add_user(user)
        except IntegrityError as exc:
            self.repository.session.rollback()
            raise DuplicateEmail() from exc
        if verified:
            return user
        try:
            self._send_action(user, "verify_email")
        except Exception as exc:
            raise EmailDeliveryFailed(user) from exc
        return user

    # «Отправить ещё раз» cannot flood a mailbox: one email a minute, five an hour, per address.
    EMAIL_COOLDOWN = timedelta(seconds=60)
    EMAIL_HOURLY_LIMIT = 5

    def _may_send(self, user: User, purpose: str) -> bool:
        now = utc_now()
        sent = [moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
                for moment in self.repository.email_token_times(user.id, purpose, now - timedelta(hours=1))]
        if sent and now - max(sent) < self.EMAIL_COOLDOWN:
            return False
        return len(sent) < self.EMAIL_HOURLY_LIMIT

    def _send_action(self, user: User, purpose: str) -> None:
        self.repository.invalidate_email_tokens(user.id, purpose)
        raw_token = f"{secrets.randbelow(1_000_000):06d}" if purpose == "verify_email" else new_token()
        lifetime = timedelta(minutes=15) if purpose == "verify_email" else timedelta(hours=1)
        token = EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw_token),
            expires_at=utc_now() + lifetime,
        )
        self.repository.add_email_token(token)
        safe_name = escape(user.first_name)
        if purpose == "verify_email":
            subject = f"Код подтверждения HelpFlow: {raw_token}"
            intro = "Введите этот код в HelpFlow. Код действует 15 минут и используется один раз."
            action_url = f"{self.app_public_url}/verify-email?email={quote(user.email)}"
            text = f"Здравствуйте, {user.first_name}!\n\n{intro}\n\nКод: {raw_token}"
            html = f"<p>Здравствуйте, {safe_name}!</p><p>{escape(intro)}</p><p style=\"font-size:28px;font-weight:700;letter-spacing:6px\">{raw_token}</p>"
        else:
            subject = "Восстановление пароля HelpFlow"
            intro = "Используйте ссылку для смены пароля. Она действует 1 час."
            action_url = f"{self.app_public_url}/reset-password?token={quote(raw_token)}"
            text = f"Здравствуйте, {user.first_name}!\n\n{intro}\n\n{action_url}"
            html = f"<p>Здравствуйте, {safe_name}!</p><p>{escape(intro)}</p><p><a href=\"{escape(action_url)}\">Продолжить</a></p>"
        self.email_sender.send(EmailPayload(
            recipient=user.email,
            subject=subject,
            text=text,
            html=html,
            action_url=action_url,
        ))

    def resend_verification(self, email: str) -> None:
        user = self.repository.get_user_by_email(email)
        # Too soon is skipped silently: the answer must not tell whether the address is registered.
        if user and user.email_verified_at is None and self._may_send(user, "verify_email"):
            self._send_action(user, "verify_email")

    def verify_email(self, email: str, raw_token: str) -> User:
        candidate = self.repository.get_user_by_email(email)
        if candidate is None:
            raise InvalidOrExpiredToken()
        token = self.repository.consume_email_token(
            hash_token(raw_token), "verify_email", user_id=candidate.id,
        )
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
        if user and user.is_active and self._may_send(user, "reset_password"):
            self._send_action(user, "reset_password")

    def reset_password(self, payload: ResetPasswordRequest) -> None:
        token = self.repository.consume_email_token(hash_token(payload.token), "reset_password")
        if token is None:
            raise InvalidOrExpiredToken()
        user = self.repository.get_user(token.user_id)
        if user is None:
            raise InvalidOrExpiredToken()
        user.password_hash = hash_password(payload.password)
        user.must_change_password = False
        self.repository.revoke_all_sessions(user.id)
        self.repository.session.commit()

    def change_password(
        self, user: User, payload: ChangePasswordRequest, *, current_token_hash: str | None = None,
    ) -> None:
        if not verify_password(user.password_hash, payload.current_password):
            raise InvalidCurrentPassword()
        user.password_hash = hash_password(payload.password)
        user.must_change_password = False
        user.revision += 1
        self.repository.revoke_all_sessions(user.id, except_token_hash=current_token_hash)
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
        expires_at = utc_now() + ttl
        session = AuthSession(user_id=user.id, token_hash=hash_token(raw_token), expires_at=expires_at,
                              user_agent=user_agent, ip_hash=ip_hash)
        self.repository.add_session(session)
        user.last_login_at = utc_now()
        self.repository.session.commit()
        return user, raw_token, expires_at

    def logout(self, raw_token: str) -> None:
        session = self.repository.get_session_by_token_hash(hash_token(raw_token))
        if session is not None and session.revoked_at is None:
            self.repository.revoke_session(session)
