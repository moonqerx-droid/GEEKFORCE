import re

import pytest

from app.repositories.auth import AuthRepository
from app.schemas.auth import EmployeeRegister
from app.services.auth import AuthService, EmailDeliveryFailed, InvalidOrExpiredToken
from app.services.email import MemoryEmailSender


def payload():
    return EmployeeRegister(
        first_name="Анна", last_name="Иванова", email="anna@example.ru", department="it",
        password="StrongPass7", password_confirmation="StrongPass7", accepted_terms=True,
    )


def code_from(sender: MemoryEmailSender) -> str:
    return re.search(r"\b\d{6}\b", sender.messages[-1].text).group(0)


def test_registration_sends_verification_and_token_is_single_use(db_session):
    sender = MemoryEmailSender()
    service = AuthService(AuthRepository(db_session), sender, "http://localhost:5173")

    user = service.register_employee(payload())
    code = code_from(sender)
    service.verify_email(payload().email, code)

    assert user.email_verified_at is not None
    with pytest.raises(InvalidOrExpiredToken):
        service.verify_email(payload().email, code)

    assert "15 минут" in sender.messages[-1].text


def test_registration_survives_delivery_failure(db_session):
    class FailingSender:
        def send(self, message):
            raise RuntimeError("smtp unavailable")

    service = AuthService(AuthRepository(db_session), FailingSender(), "http://localhost:5173")
    with pytest.raises(EmailDeliveryFailed):
        service.register_employee(payload())

    db_session.expire_all()
    assert AuthRepository(db_session).get_user_by_email("anna@example.ru") is not None
