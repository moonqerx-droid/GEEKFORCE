import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_configuration_uses_mock_ai_and_sqlite():
    settings = Settings(_env_file=None)

    assert settings.ai_provider == "mock"
    assert settings.database_url.startswith("sqlite")


def test_configuration_rejects_unknown_ai_provider():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_provider="mystery")
