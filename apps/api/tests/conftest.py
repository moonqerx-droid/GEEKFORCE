import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.api.dependencies.auth import require_employee, require_operator
from app.models.auth import User


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_employee] = lambda: User(
        id="test-employee", first_name="Тест", last_name="Сотрудник",
        email="employee@test.local", department="it", password_hash="unused",
        role="employee", email_verified_at=None,
    )
    app.dependency_overrides[require_operator] = lambda: User(
        id="test-operator", first_name="Тест", last_name="Специалист",
        email="operator@test.local", department="it", password_hash="unused",
        role="operator", email_verified_at=None,
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
