from io import StringIO

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app import models  # noqa: F401 -- registers metadata


def test_initial_migration_creates_dialogue_tables(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    tables = set(inspect(create_engine(database_url)).get_table_names())
    assert {"conversations", "messages", "troubleshooting_steps"} <= tables


def test_initial_migration_adopts_pre_alembic_database(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(models.Conversation(id="preserved", status="NEW"))
        session.commit()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    assert inspect(engine).has_table("alembic_version")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260928_0013"
        assert connection.scalar(text("SELECT id FROM conversations WHERE id='preserved'")) == "preserved"
    inspector = inspect(engine)
    assert {"users", "auth_sessions", "email_tokens", "operator_invites"}.issubset(
        set(inspector.get_table_names())
    )
    assert "owner_id" in {column["name"] for column in inspector.get_columns("conversations")}


def test_initial_migration_rejects_incomplete_legacy_schema(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'broken.db'}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE conversations (id VARCHAR(36) PRIMARY KEY)"))
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    with pytest.raises(RuntimeError, match="incompatible pre-Alembic schema"):
        command.upgrade(config, "head")


def test_environment_database_url_is_migration_target(tmp_path, monkeypatch):
    target_url = f"sqlite:///{tmp_path / 'configured.db'}"
    monkeypatch.setenv("DATABASE_URL", target_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(target_url)
    assert inspect(engine).has_table("alembic_version")
    assert inspect(engine).has_table("conversations")


def test_offline_migration_emits_fresh_schema_sql():
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)

    command.upgrade(config, "head", sql=True)

    assert "CREATE TABLE conversations" in output.getvalue()


def test_triage_migration_upgrades_original_schema_without_losing_data(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'upgrade.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260925_0001")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO conversations
            (id,status,created_at,updated_at,symptoms,urgency,known_facts,missing_facts)
            VALUES ('old','NEW',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'[]','normal','{}','[]')
        """))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT id,workflow_version,asked_facts,verification_failed,revision,rag_source_ids,"
            "ai_fallback_reason,ai_latency_ms FROM conversations"
        )).one()
        assert tuple(row) == ("old", "legacy", "[]", 0, 1, "[]", None, None)


def test_ai_provenance_migration_roundtrip(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'provenance.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260926_0003")
    engine = create_engine(database_url)

    command.upgrade(config, "head")
    upgraded = {column["name"] for column in inspect(engine).get_columns("conversations")}
    assert {"rag_source_ids", "ai_fallback_reason", "ai_latency_ms"} <= upgraded

    command.downgrade(config, "20260926_0003")
    downgraded = {column["name"] for column in inspect(engine).get_columns("conversations")}
    assert {"rag_source_ids", "ai_fallback_reason", "ai_latency_ms"}.isdisjoint(downgraded)


def test_managed_accounts_migration_adds_revision_and_audit(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'managed.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    inspector = inspect(create_engine(database_url))
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"must_change_password", "revision"} <= user_columns
    assert inspector.has_table("admin_audit_events")


def test_incident_radar_migration_roundtrip(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'incident.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260928_0007")
    engine = create_engine(database_url)

    command.upgrade(config, "20260928_0008")
    assert {"incidents", "incident_updates"} <= set(inspect(engine).get_table_names())

    command.downgrade(config, "20260928_0007")
    assert {"incidents", "incident_updates"}.isdisjoint(inspect(engine).get_table_names())


def test_knowledge_migration_roundtrip_and_integrity(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'knowledge.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260928_0009")
    engine = create_engine(database_url)

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert {"knowledge_documents", "knowledge_chunks"} <= set(inspector.get_table_names())
    chunk_columns = {column["name"] for column in inspector.get_columns("knowledge_chunks")}
    assert {"id", "document_id", "position", "text", "char_count", "token_count", "metadata", "created_at"} <= chunk_columns
    document_indexes = {index["name"] for index in inspector.get_indexes("knowledge_documents")}
    assert {"ix_knowledge_documents_sha256", "ix_knowledge_documents_status"} <= document_indexes
    unique = inspector.get_unique_constraints("knowledge_chunks")
    assert any(set(item["column_names"]) == {"document_id", "position"} for item in unique)

    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO knowledge_documents (id, title, original_filename, media_type, size_bytes, sha256,"
            " status, created_at, updated_at, revision)"
            " VALUES ('d1', 't', 'f.txt', 'text/plain', 1, 'x', 'ready', '2026-09-28', '2026-09-28', 1)"
        ))
        connection.execute(text(
            "INSERT INTO knowledge_chunks (id, document_id, position, text, char_count, token_count,"
            " metadata, created_at) VALUES ('c1', 'd1', 0, 'a', 1, 1, '{}', '2026-09-28')"
        ))
    with pytest.raises(Exception), engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO knowledge_chunks (id, document_id, position, text, char_count, token_count,"
            " metadata, created_at) VALUES ('c2', 'd1', 0, 'b', 1, 1, '{}', '2026-09-28')"
        ))
    with pytest.raises(Exception), engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO knowledge_documents (id, title, original_filename, media_type, size_bytes, sha256,"
            " status, created_at, updated_at, revision)"
            " VALUES ('d2', 't', 'f.txt', 'text/plain', 1, 'y', 'archived', '2026-09-28', '2026-09-28', 1)"
        ))

    command.downgrade(config, "20260928_0009")
    assert {"knowledge_documents", "knowledge_chunks"}.isdisjoint(inspect(engine).get_table_names())


def test_latest_schema_stores_answer_metadata_on_messages(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'message-meta.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")
    columns = {
        column["name"]: column
        for column in inspect(create_engine(database_url)).get_columns("messages")
    }

    assert columns["answer_kind"]["nullable"] is True
    assert columns["citations"]["nullable"] is True


def test_reply_templates_migration_roundtrip(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'templates.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260928_0012")
    engine = create_engine(database_url)

    command.upgrade(config, "head")
    columns = {column["name"] for column in inspect(engine).get_columns("reply_templates")}
    assert {"id", "title", "body", "created_by", "created_at", "updated_at"} <= columns

    command.downgrade(config, "20260928_0012")
    assert "reply_templates" not in inspect(engine).get_table_names()
