import pytest
import yaml
from pydantic import ValidationError
from pathlib import Path

from app.core.config import Settings


def test_default_configuration_uses_mock_ai_and_sqlite():
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "mock"
    assert settings.database_url.startswith("sqlite")
    assert "http://localhost:5174" in settings.cors_origins
    assert "http://127.0.0.1:5174" in settings.cors_origins
    assert settings.app_public_url == "http://localhost:5174"


def test_incident_settings_have_safe_defaults():
    settings = Settings(_env_file=None)

    assert settings.incident_similarity_threshold == 0.55
    assert settings.incident_min_cluster_size == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("incident_similarity_threshold", -0.01),
        ("incident_similarity_threshold", 1.01),
        ("incident_min_cluster_size", 1),
        ("incident_min_cluster_size", 21),
    ],
)
def test_incident_settings_reject_unsafe_bounds(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_configuration_rejects_unknown_ai_provider():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_provider="mystery")


def test_configuration_accepts_ollama_without_an_external_api_key():
    settings = Settings(_env_file=None, ai_provider="ollama")

    assert settings.ai_provider == "ollama"


def test_configuration_accepts_rules_only_fallback():
    settings = Settings(_env_file=None, ai_provider="rules")

    assert settings.ai_provider == "rules"


def test_compose_uses_healthy_postgres_before_starting_api():
    compose_path = Path(__file__).parents[3] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    database = compose["services"]["db"]
    api = compose["services"]["api"]

    assert database["image"] == "postgres:16-alpine"
    assert database["healthcheck"]["test"]
    assert api["depends_on"]["db"]["condition"] == "service_healthy"
    assert "postgresql+psycopg://" in api["environment"]["DATABASE_URL"]
    assert "host.docker.internal:11434" in api["environment"]["OLLAMA_BASE_URL"]
    assert "OLLAMA_MODEL" in api["environment"]


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
