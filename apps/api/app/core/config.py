from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./helpflow.db"
    ai_provider: Literal["mock", "rules", "openai", "ollama"] = "mock"
    incident_similarity_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    incident_min_cluster_size: int = Field(default=3, ge=2, le=20)
    # Only requests escalated this recently can start a new incident.
    incident_window_minutes: int = Field(default=120, ge=5, le=24 * 60)
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]
    app_public_url: str = "http://localhost:5174"
    session_cookie_name: str = "helpflow_session"
    session_ttl_hours: int = 12
    remembered_session_ttl_days: int = 30
    cookie_secure: bool = False
    smtp_host: str = "smtp.yandex.ru"
    smtp_port: int = 465
    smtp_security: Literal["ssl", "starttls"] = "ssl"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "HelpFlow"
    admin_email: str = ""
    admin_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
