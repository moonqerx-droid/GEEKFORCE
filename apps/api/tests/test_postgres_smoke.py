"""PostgreSQL integration smoke test, enabled only by the CI/runtime URL."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DATABASE_URL"),
    reason="requires the PostgreSQL integration service",
)


def test_migrated_postgres_serves_and_persists_an_api_conversation():
    assert engine.dialect.name == "postgresql"

    with TestClient(app) as client:
        response = client.post("/api/conversations")

    assert response.status_code == 201
    conversation_id = response.json()["id"]
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        stored_id = connection.execute(
            text("SELECT id FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        ).scalar_one()

    assert revision == "20260926_0004"
    assert stored_id == conversation_id
