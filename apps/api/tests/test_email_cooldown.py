"""«Отправить ещё раз» cannot flood a mailbox or be used to find registered addresses."""

from datetime import timedelta

from app.api.routes.auth import get_email_sender
from app.main import app
from app.models.auth import EmailToken
from app.services.email import MemoryEmailSender

REGISTRATION = {
    "first_name": "Анна", "last_name": "Иванова", "email": "anna@example.ru",
    "department": "it", "password": "StrongPass7", "password_confirmation": "StrongPass7",
    "accepted_terms": True,
}


def outbox():
    sent = MemoryEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sent
    return sent


def test_resend_right_after_registration_sends_nothing_more(client):
    sent = outbox()
    assert client.post("/api/auth/register", json=REGISTRATION).status_code == 201
    for _ in range(5):
        reply = client.post("/api/auth/resend-verification", json={"email": "anna@example.ru"})
        assert reply.status_code == 202
        assert reply.json()["retry_after"] == 60
    assert len(sent.messages) == 1  # the registration email only


def test_after_a_minute_the_code_can_be_sent_again(client, db_session):
    sent = outbox()
    client.post("/api/auth/register", json=REGISTRATION)
    for token in db_session.query(EmailToken).all():
        token.created_at = token.created_at - timedelta(seconds=61)
    db_session.commit()

    client.post("/api/auth/resend-verification", json={"email": "anna@example.ru"})
    assert len(sent.messages) == 2


def test_no_more_than_five_emails_an_hour(client, db_session):
    sent = outbox()
    client.post("/api/auth/register", json=REGISTRATION)
    for _ in range(8):
        for token in db_session.query(EmailToken).all():
            token.created_at = token.created_at - timedelta(seconds=61)
        db_session.commit()
        client.post("/api/auth/resend-verification", json={"email": "anna@example.ru"})
    assert len(sent.messages) == 5


def test_a_cooldown_looks_the_same_for_a_missing_address(client):
    outbox()
    client.post("/api/auth/register", json=REGISTRATION)
    known = client.post("/api/auth/forgot-password", json={"email": "anna@example.ru"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.ru"})
    assert known.status_code == unknown.status_code == 202
    assert known.json()["retry_after"] == unknown.json()["retry_after"]


def test_one_address_cannot_send_endless_requests(client):
    outbox()
    for index in range(10):
        client.post("/api/auth/forgot-password", json={"email": f"user{index}@example.ru"})
    refused = client.post("/api/auth/forgot-password", json={"email": "user11@example.ru"})
    assert refused.status_code == 429
    assert "Слишком много писем" in refused.json()["detail"]["message"]
