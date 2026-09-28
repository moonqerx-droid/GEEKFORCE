"""Documents the support lead uploads are what the assistant answers company questions from."""

import pytest

from app.api.dependencies.auth import require_admin
from app.core.security import hash_password, utc_now
from app.main import app
from app.models.auth import User

QUESTION = "Какие суточные положены в командировке?"
POLICY = """# Командировки

Суточные в командировке по России — 700 рублей в день. Отчёт сдаётся в течение трёх дней после возвращения.
""".encode()


@pytest.fixture
def admin(db_session, client):
    user = User(
        id="admin-docs", first_name="Мария", last_name="Иванова", email="admin-docs@example.org",
        department="it", password_hash=hash_password("Pass12345678"), role="admin", email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    app.dependency_overrides[require_admin] = lambda: user
    return user


def ask(client, text):
    cid = client.post("/api/conversations").json()["id"]
    response = client.post(f"/api/conversations/{cid}/messages", json={"content": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_company_question_without_a_document_goes_to_a_specialist(client, admin):
    state = ask(client, QUESTION)

    assert state["status"] == "ESCALATED"


def test_uploaded_document_answers_with_a_quote(client, admin):
    uploaded = client.post("/api/admin/knowledge/documents",
                           files={"file": ("travel.md", POLICY, "text/markdown")}, data={"title": "Командировки"})
    assert uploaded.status_code == 201, uploaded.text

    state = ask(client, QUESTION)

    assert state["answer_kind"] == "document"
    assert "700 рублей в день" in state["messages"][-1]["content"]
    [citation] = state["citations"]
    assert citation["source_id"].startswith(f"document:{uploaded.json()['id']}:")
    assert "700 рублей" in citation["quote"]


def test_deleted_document_stops_answering(client, admin):
    document_id = client.post("/api/admin/knowledge/documents",
                              files={"file": ("travel.md", POLICY, "text/markdown")}).json()["id"]
    assert ask(client, QUESTION)["answer_kind"] == "document"

    client.delete(f"/api/admin/knowledge/documents/{document_id}")

    assert ask(client, QUESTION)["status"] == "ESCALATED"
