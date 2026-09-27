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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260926_0004"
        assert connection.scalar(text("SELECT id FROM conversations WHERE id='preserved'")) == "preserved"


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
