import re

from app.api.routes.auth import get_email_sender
from app.main import app
from app.services.email import MemoryEmailSender


def test_employee_authentication_acceptance_flow(client):
    outbox = MemoryEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: outbox
    registration = {
        "first_name": "Анна", "last_name": "Иванова", "email": "anna@example.ru",
        "department": "it", "password": "StrongPass7", "password_confirmation": "StrongPass7",
        "accepted_terms": True,
    }
    assert client.post("/api/auth/register", json=registration).status_code == 201
    code = re.search(r"\b\d{6}\b", outbox.messages[-1].text).group(0)
    assert client.post("/api/auth/verify-email", json={
        "email": "anna@example.ru", "code": code,
    }).status_code == 204
    assert client.post("/api/auth/login", json={
        "email": "anna@example.ru", "password": "StrongPass7", "remember_me": False,
    }).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
