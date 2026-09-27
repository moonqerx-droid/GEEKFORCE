"""PostgreSQL integration smoke test, enabled only by the CI/runtime URL."""

import os
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import hash_password, utc_now
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Conversation, Message
from app.models.auth import User
from app.repositories.incidents import IncidentRepository
from app.services.incidents import IncidentService


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DATABASE_URL"),
    reason="requires the PostgreSQL integration service",
)


def test_migrated_postgres_serves_and_persists_an_api_conversation():
    assert engine.dialect.name == "postgresql"
    email = f"smoke-{uuid4().hex[:8]}@example.ru"
    with Session(engine) as session:
        session.add(User(
            first_name="Смоук", last_name="Тест", email=email, department="it",
            password_hash=hash_password("StrongPass123"), role="employee", email_verified_at=utc_now(),
        ))
        session.commit()

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": email, "password": "StrongPass123"})
        assert login.status_code == 200
        response = client.post("/api/conversations")

    assert response.status_code == 201
    conversation_id = response.json()["id"]
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        stored_id = connection.execute(
            text("SELECT id FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        ).scalar_one()

    assert revision == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert stored_id == conversation_id


def test_postgres_radar_groups_requests_and_delivers_a_broadcast():
    marker = uuid4().hex[:8]
    email = f"smoke-operator-{marker}@example.ru"
    service_name = f"VPN {marker}"
    with SessionLocal() as session:
        session.add(User(
            first_name="Анна", last_name="Смоук", email=email, department="it",
            password_hash=hash_password("StrongPass123"), role="operator", email_verified_at=utc_now(),
        ))
        radar = IncidentService(IncidentRepository(session), threshold=0.55, min_cluster_size=3)
        incident = None
        for _ in range(3):
            item = Conversation(
                workflow_version="triage-v1", status="ESCALATED", service=service_name,
                summary="Не подключается VPN", symptoms=["VPN не подключается"],
                known_facts={"error_text": "ошибка 809"}, playbook_id="vpn_connection",
                escalated_at=utc_now(),
            )
            item.messages.append(Message(role="user", content="Не подключается VPN, ошибка 809"))
            session.add(item)
            session.commit()
            incident = radar.observe_escalated(item.id) or incident
            session.commit()
        assert incident is not None and incident.signature_tokens

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"email": email, "password": "StrongPass123"}).status_code == 200
        listed = {item["id"]: item for item in client.get("/api/operator/incidents").json()}
        assert listed[incident.id]["conversation_count"] == 3
        result = client.post(f"/api/operator/incidents/{incident.id}/broadcast", json={
            "message": "Чиним VPN.", "request_key": f"smoke-{marker}",
            "expected_revision": listed[incident.id]["revision"],
        })

    assert result.status_code == 200, result.text
    assert len(result.json()["delivered_to"]) == 3


def test_postgres_knowledge_upload_cascade_and_unique_positions():
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

    email = f"smoke-admin-{uuid4().hex[:8]}@example.ru"
    with Session(engine) as session:
        session.add(User(
            first_name="Смоук", last_name="Админ", email=email, department="it",
            password_hash=hash_password("StrongPass123"), role="admin", email_verified_at=utc_now(),
        ))
        session.commit()
    body = f"# Правила VPN {uuid4().hex}\n\nПодключайтесь через «Континент». Ошибка 809 — роутер.".encode()

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"email": email, "password": "StrongPass123"}).status_code == 200
        created = client.post(
            "/api/admin/knowledge/documents",
            files={"file": ("vpn.md", body, "text/markdown")},
        )
        assert created.status_code == 201, created.text
        document_id = created.json()["id"]
        assert created.json()["status"] == "ready"

        with Session(engine) as session:
            session.add(KnowledgeChunk(
                document_id=document_id, position=0, text="дубль", char_count=5, token_count=1,
            ))
            with pytest.raises(IntegrityError):
                session.commit()

        # The database itself cascades, not only the ORM.
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM knowledge_documents WHERE id = :id"), {"id": document_id})
        with Session(engine) as session:
            assert session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)).all() == []
            assert session.get(KnowledgeDocument, document_id) is None
