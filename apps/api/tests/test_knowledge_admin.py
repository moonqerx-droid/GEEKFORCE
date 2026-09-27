"""Admin knowledge base: upload, list, detail, delete, and chunks for retrieval."""

from hashlib import sha256

import pytest
from sqlalchemy import select

from app.api.dependencies.auth import require_admin, require_verified_user
from app.api.routes.knowledge_admin import get_knowledge_service
from app.core.security import hash_password, utc_now
from app.main import app
from app.models.audit import AdminAuditEvent
from app.models.auth import User
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.company_knowledge import company_knowledge_chunks
from app.services.knowledge import KnowledgeLimits, KnowledgeService
from tests.knowledge_files import docx_with, pdf_with_text

URL = "/api/admin/knowledge/documents"
VPN_RULES = """# Удалённый доступ

Сотрудники подключаются к рабочим системам только через VPN «Континент».

## Если VPN не подключается

Перезагрузите компьютер и попробуйте снова. Ошибка 809 означает, что домашний роутер блокирует VPN.
""".encode()


def add_user(db_session, user_id, role):
    user = User(
        id=user_id, first_name="Мария", last_name="Иванова", email=f"{user_id}@example.org",
        department="it", password_hash=hash_password("Pass12345678"), role=role, email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def admin(db_session, client):
    user = add_user(db_session, "admin-kb", "admin")
    app.dependency_overrides[require_admin] = lambda: user
    return user


def upload(client, filename, content, content_type="text/plain", **form):
    return client.post(URL, files={"file": (filename, content, content_type)}, data=form)


# --- upload ---------------------------------------------------------------------

def test_admin_uploads_a_text_document(client, admin, db_session):
    response = upload(client, "vpn.md", VPN_RULES, "text/markdown", title="Правила VPN", service="VPN")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["title"] == "Правила VPN"
    assert body["service"] == "VPN"
    assert body["original_filename"] == "vpn.md"
    assert body["media_type"] == "text/markdown"
    assert body["size_bytes"] == len(VPN_RULES)
    assert body["sha256"] == sha256(VPN_RULES).hexdigest()
    assert body["chunk_count"] == 2
    assert body["uploaded_by"] == admin.id
    assert body["processed_at"] and body["error_message"] is None

    detail = client.get(f"{URL}/{body['id']}").json()
    assert [chunk["position"] for chunk in detail["chunks"]] == [0, 1]
    assert detail["chunks"][1]["metadata"]["heading"] == "Если VPN не подключается"
    assert "Ошибка 809" in detail["chunks"][1]["text"]
    assert [item["id"] for item in client.get(URL).json()] == [body["id"]]


@pytest.mark.parametrize(("filename", "content", "content_type", "expected"), [
    ("guide.pdf", pdf_with_text("VPN guide", "Restart the client."), "application/pdf", "Restart the client."),
    ("policy.docx", docx_with("Отпуск", ["Заявление подаётся за две недели."]),
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "за две недели"),
    ("notes.txt", "Пароль меняется раз в 90 дней.".encode(), "text/plain", "90 дней"),
])
def test_every_supported_format_becomes_ready(client, admin, filename, content, content_type, expected):
    body = upload(client, filename, content, content_type).json()

    assert body["status"] == "ready", body
    detail = client.get(f"{URL}/{body['id']}").json()
    assert expected in " ".join(chunk["text"] for chunk in detail["chunks"])
    assert body["title"] == filename.rsplit(".", 1)[0]


def test_filename_cannot_escape_or_inject(client, admin):
    body = upload(client, "../../etc/<b>passwd.txt", "текст правил".encode()).json()

    assert body["original_filename"] == "bpasswd.txt"
    assert "/" not in body["original_filename"]


def test_client_checksum_is_verified(client, admin):
    good = upload(client, "a.txt", "текст один".encode(), sha256=sha256("текст один".encode()).hexdigest())
    bad = upload(client, "b.txt", "текст два".encode(), sha256="0" * 64)

    assert good.status_code == 201
    assert bad.status_code == 422
    assert "SHA-256" in bad.json()["detail"]


# --- refused uploads -------------------------------------------------------------

def test_oversized_upload_is_refused_without_a_record(client, admin, db_session):
    app.dependency_overrides[get_knowledge_service] = lambda: KnowledgeService(
        db_session, KnowledgeLimits(max_upload_bytes=100),
    )

    response = upload(client, "big.txt", ("слово " * 100).encode())

    assert response.status_code == 413
    assert db_session.scalar(select(KnowledgeDocument)) is None


@pytest.mark.parametrize(("filename", "content", "content_type", "status"), [
    ("empty.txt", b"", "text/plain", 422),
    ("tool.exe", b"MZ\x90\x00", "application/octet-stream", 415),
    ("macro.docm", b"PK\x03\x04", "application/octet-stream", 415),
    ("image.pdf", pdf_with_text("x"), "image/png", 415),
])
def test_invalid_requests_are_refused(client, admin, db_session, filename, content, content_type, status):
    assert upload(client, filename, content, content_type).status_code == status
    assert db_session.scalar(select(KnowledgeDocument)) is None


@pytest.mark.parametrize(("filename", "content", "content_type", "code_text"), [
    ("fake.pdf", "это не PDF, а текст".encode(), "application/pdf", "не соответствует"),
    ("broken.pdf", b"%PDF-1.4\n1 0 obj << /Type /Catalog", "application/pdf", "повреждён"),
    ("blank.txt", b" \n \n", "text/plain", "нет текста"),
])
def test_unreadable_documents_are_kept_as_failed(client, admin, filename, content, content_type, code_text):
    response = upload(client, filename, content, content_type)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert code_text in body["error_message"]
    assert body["chunk_count"] == 0


def test_duplicate_of_a_ready_document_is_refused(client, admin):
    first = upload(client, "vpn.md", VPN_RULES).json()

    again = upload(client, "copy.md", VPN_RULES)

    assert again.status_code == 409
    assert again.json()["detail"]["document_id"] == first["id"]


def test_failed_document_can_be_uploaded_again(client, admin):
    upload(client, "fake.pdf", b"not a pdf", "application/pdf")

    assert upload(client, "fake.pdf", b"not a pdf", "application/pdf").status_code == 201


# --- access -----------------------------------------------------------------------

@pytest.mark.parametrize("role", ["employee", "operator"])
def test_only_admins_can_use_the_knowledge_base(client, db_session, role):
    user = add_user(db_session, f"{role}-kb", role)
    app.dependency_overrides[require_verified_user] = lambda: user

    assert upload(client, "vpn.md", VPN_RULES).status_code == 403
    assert client.get(URL).status_code == 403


def test_anonymous_request_is_refused(client):
    assert client.get(URL).status_code == 401


def test_untrusted_origin_is_refused(client, admin):
    response = client.post(URL, files={"file": ("vpn.md", VPN_RULES, "text/markdown")},
                           headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


# --- delete and audit --------------------------------------------------------------

def test_delete_removes_the_document_and_its_chunks(client, admin, db_session):
    document_id = upload(client, "vpn.md", VPN_RULES).json()["id"]

    assert client.delete(f"{URL}/{document_id}").status_code == 204
    assert client.get(f"{URL}/{document_id}").status_code == 404
    assert client.delete(f"{URL}/{document_id}").status_code == 404
    assert db_session.scalars(select(KnowledgeChunk)).all() == []


def test_admin_actions_are_audited_without_content(client, admin, db_session):
    document_id = upload(client, "vpn.md", VPN_RULES).json()["id"]
    client.delete(f"{URL}/{document_id}")

    events = db_session.scalars(select(AdminAuditEvent).order_by(AdminAuditEvent.created_at)).all()
    assert [event.action for event in events] == ["knowledge.document_uploaded", "knowledge.document_deleted"]
    assert all(event.actor_id == admin.id for event in events)
    assert events[0].changes["document_id"] == document_id
    assert events[0].changes["status"] == "ready"
    assert "Континент" not in str(events[0].changes)


# --- chunks for retrieval -----------------------------------------------------------

def test_only_ready_documents_feed_retrieval(client, admin, db_session):
    ready = upload(client, "vpn.md", VPN_RULES, title="Правила VPN", service="VPN").json()
    upload(client, "fake.pdf", b"not a pdf", "application/pdf")

    chunks = company_knowledge_chunks(db_session)

    assert [chunk.id for chunk in chunks] == [f"document:{ready['id']}:0", f"document:{ready['id']}:1"]
    second = chunks[1]
    assert second.title == "Правила VPN — Если VPN не подключается"
    assert second.service == "VPN"
    assert second.document_id == ready["id"] and second.position == 1
    assert "809" in second.text
    assert {"vpn", "подключается"} <= set(second.keywords)
    payload = second.as_engine_chunk()
    assert set(payload) == {"id", "service", "title", "text", "keywords", "escalation_team"}
    assert company_knowledge_chunks(db_session) == chunks, "order is stable"
