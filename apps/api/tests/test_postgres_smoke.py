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
from app.db.session import engine
from app.main import app
from app.models.auth import User


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
