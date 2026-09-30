import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.api.dependencies.auth import require_employee, require_operator
from app.models import Conversation, Incident, Message
from app.models.auth import User
from app.repositories.incidents import IncidentRepository
from app.services.incidents import IncidentService


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Rate limits live in the process; every test starts with none spent."""
    from app.api.routes import auth

    auth._rate_limiter._events.clear()
    yield
    auth._rate_limiter._events.clear()


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


@pytest.fixture
def crm_failure_factory(db_session):
    def create(code="502"):
        item = Conversation(
            workflow_version="triage-v1",
            status="ESCALATED",
            service="CRM",
            summary="CRM недоступна",
            symptoms=["не открывается"],
            known_facts={"error_text": code},
            playbook_id="service_unavailable",
        )
        item.messages.append(Message(role="user", content=f"CRM не работает, ошибка {code}"))
        db_session.add(item)
        db_session.flush()
        return item
    return create


@pytest.fixture
def mail_failure_factory(db_session):
    def create(code="502"):
        item = Conversation(
            workflow_version="triage-v1",
            status="ESCALATED",
            service="Корпоративная почта",
            summary="Почта недоступна",
            symptoms=["не открывается"],
            known_facts={"error_text": code},
            playbook_id="email_outlook",
        )
        item.messages.append(Message(role="user", content=f"Почта не работает, ошибка {code}"))
        db_session.add(item)
        db_session.flush()
        return item
    return create


@pytest.fixture
def incident_service(db_session):
    return IncidentService(
        IncidentRepository(db_session),
        threshold=0.55,
        min_cluster_size=3,
    )


@pytest.fixture
def candidate(db_session, incident_service, crm_failure_factory):
    created = None
    for _ in range(3):
        item = crm_failure_factory(code="502")
        created = incident_service.observe_escalated(item.id) or created
    assert created is not None
    db_session.flush()
    return created


@pytest.fixture
def seeded_crm_candidate(candidate):
    return candidate


@pytest.fixture
def incident_factory(db_session):
    def create(status="CANDIDATE", members=3):
        incident = Incident(
            status=status,
            service="crm",
            title=f"CRM {status}",
            signature_tokens=["crm", "502"],
            similarity_threshold=0.55,
        )
        db_session.add(incident)
        db_session.flush()
        for index in range(members):
            db_session.add(Conversation(
                workflow_version="triage-v1",
                status="ESCALATED",
                service="CRM",
                incident_id=incident.id,
                summary=f"CRM failure {index}",
            ))
        db_session.flush()
        return incident
    return create


@pytest.fixture
def resolved_incident(incident_factory):
    return incident_factory(status="RESOLVED", members=3)
