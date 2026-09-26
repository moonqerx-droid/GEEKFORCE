import pytest
import yaml
from pydantic import ValidationError
from pathlib import Path

from app.core.config import Settings


def test_default_configuration_uses_mock_ai_and_sqlite():
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "mock"
    assert settings.database_url.startswith("sqlite")


def test_configuration_rejects_unknown_ai_provider():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_provider="mystery")


def test_compose_uses_healthy_postgres_before_starting_api():
    compose_path = Path(__file__).parents[3] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    database = compose["services"]["db"]
    api = compose["services"]["api"]

    assert database["image"] == "postgres:16-alpine"
    assert database["healthcheck"]["test"]
    assert api["depends_on"]["db"]["condition"] == "service_healthy"
    assert "postgresql+psycopg://" in api["environment"]["DATABASE_URL"]


def test_compose_runs_migrations_before_the_api_server():
    compose_path = Path(__file__).parents[3] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    command = compose["services"]["api"]["command"]

    assert "alembic upgrade head" in command
    assert command.index("alembic upgrade head") < command.index("uvicorn")


def test_ci_runs_a_real_postgres_smoke_test():
    workflow_path = Path(__file__).parents[3] / ".github" / "workflows" / "backend.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "postgres:16-alpine" in workflow
    assert "POSTGRES_TEST_DATABASE_URL" in workflow
    assert "test_postgres_smoke.py" in workflow
