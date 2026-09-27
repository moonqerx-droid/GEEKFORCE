from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUserDependency
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.auth import AuthRepository
from app.schemas.auth import (
    CurrentUser, EmployeeRegister, ForgotPasswordRequest, LoginRequest, OperatorRegister,
    ResetPasswordRequest, TokenRequest, VerifyEmailRequest,
)
from app.services.auth import (
    AuthService, DuplicateEmail, EmailDeliveryFailed, EmailNotVerified, InvalidCredentials,
    InvalidInvite, InvalidOrExpiredToken,
)
from app.services.email import EmailSender, MemoryEmailSender, SmtpEmailSender
from app.services.rate_limit import InMemoryRateLimiter, RateLimitExceeded


def require_trusted_origin(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        raise HTTPException(status_code=403, detail="Untrusted origin")


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    dependencies=[Depends(require_trusted_origin)],
)
_rate_limiter = InMemoryRateLimiter()


def get_email_sender() -> EmailSender:
    settings = get_settings()
    if not settings.smtp_username or not settings.smtp_password or not settings.smtp_from_email:
        return MemoryEmailSender()
    return SmtpEmailSender(
        host=settings.smtp_host, port=settings.smtp_port, username=settings.smtp_username,
        password=settings.smtp_password, from_email=settings.smtp_from_email,
        from_name=settings.smtp_from_name, security=settings.smtp_security,
    )


def get_auth_service(
    db: Annotated[Session, Depends(get_db)],
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> AuthService:
    return AuthService(AuthRepository(db), sender, get_settings().app_public_url)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post("/register", response_model=CurrentUser, status_code=status.HTTP_201_CREATED)
def register(payload: EmployeeRegister, service: AuthServiceDependency):
    try:
        return service.register_employee(payload)
    except DuplicateEmail as exc:
        raise error(409, "duplicate_email", "Пользователь с таким email уже существует") from exc
    except EmailDeliveryFailed as exc:
        raise error(503, "email_delivery_failed", "Аккаунт создан, но письмо не отправлено") from exc


@router.post("/operator/register", response_model=CurrentUser, status_code=status.HTTP_201_CREATED)
def register_operator(payload: OperatorRegister, service: AuthServiceDependency):
    try:
        return service.register_operator(payload)
    except InvalidInvite as exc:
        raise error(400, "invalid_invite", "Приглашение недействительно или истекло") from exc
    except DuplicateEmail as exc:
        raise error(409, "duplicate_email", "Пользователь с таким email уже существует") from exc


@router.post("/login", response_model=CurrentUser)
def login(payload: LoginRequest, request: Request, response: Response, service: AuthServiceDependency):
    client_host = request.client.host if request.client else "unknown"
    try:
        _rate_limiter.check(
            "login",
            f"{client_host}:{payload.email}",
            limit=5,
            window=timedelta(minutes=10),
        )
    except RateLimitExceeded as exc:
        raise error(429, "rate_limited", "Слишком много попыток. Повторите позже") from exc
    try:
        user, raw_token, expires_at = service.login(payload, user_agent=request.headers.get("user-agent"))
    except InvalidCredentials as exc:
        raise error(401, "invalid_credentials", "Неверный email или пароль") from exc
    except EmailNotVerified as exc:
        raise error(403, "email_not_verified", "Подтвердите email перед входом") from exc
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name, raw_token, expires=expires_at, httponly=True,
        secure=settings.cookie_secure, samesite="lax", path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, service: AuthServiceDependency):
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        service.logout(raw_token)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=CurrentUser)
def me(user: CurrentUserDependency):
    return user


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: VerifyEmailRequest, service: AuthServiceDependency):
    try:
        service.verify_email(payload.email, payload.code)
    except InvalidOrExpiredToken as exc:
        raise error(400, "invalid_or_expired_code", "Код недействителен или истёк") from exc


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend(payload: ForgotPasswordRequest, service: AuthServiceDependency):
    service.resend_verification(payload.email)
    return {"code": "verification_requested"}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotPasswordRequest, service: AuthServiceDependency):
    try:
        service.request_password_reset(payload.email)
    except Exception:
        pass
    return {"code": "password_reset_requested"}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, service: AuthServiceDependency):
    try:
        service.reset_password(payload)
    except InvalidOrExpiredToken as exc:
        raise error(400, "invalid_or_expired_token", "Ссылка недействительна или истекла") from exc
