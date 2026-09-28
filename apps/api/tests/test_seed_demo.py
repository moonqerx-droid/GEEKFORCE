"""The demo seed must show Incident Radar right away and stay safe to re-run."""

from datetime import timedelta

import pytest
from helpflow_ai import TriageEngine
from helpflow_ai.knowledge import KnowledgeBase
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import utc_now
from app.db.base import Base
from app.models import Conversation, Incident
from app.repositories.conversations import ConversationRepository
from app.seed_demo import seed, seed_incident
from app.services.admin import AdminService, _aware
from app.services.triage import TriageDialogueService


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.drop_all(engine)


def open_incidents(session):
    return session.scalars(select(Incident).where(Incident.status.in_(("CANDIDATE", "ACTIVE")))).all()


def test_seed_shows_a_fresh_vpn_outage(factory):
    assert seed(total=12, session_factory=factory) is True
    assert seed_incident(session_factory=factory) is True

    with factory() as session:
        [incident] = open_incidents(session)
        members = session.scalars(select(Conversation).where(Conversation.incident_id == incident.id)).all()
        assert incident.service == "vpn"
        assert len(members) >= 4
        assert len({member.owner_id for member in members}) == len(members)
        oldest = min(_aware(member.escalated_at) for member in members)
        assert utc_now() - oldest <= timedelta(minutes=30)
        # Some joined on their first message, without any troubleshooting.
        assert any(not member.steps for member in members)


def test_seed_is_idempotent(factory):
    seed(total=12, session_factory=factory)
    seed_incident(session_factory=factory)

    assert seed(total=12, session_factory=factory) is False
    assert seed_incident(session_factory=factory) is False
    with factory() as session:
        assert len(open_incidents(session)) == 1


def test_live_vpn_request_joins_the_seeded_outage(factory):
    seed(total=12, session_factory=factory)
    seed_incident(session_factory=factory)

    with factory() as session:
        dialogue = TriageDialogueService(ConversationRepository(session), TriageEngine(KnowledgeBase.load(), None))
        conversation = dialogue.create_conversation()
        state = dialogue.handle_message(conversation.id, "Не подключается VPN, что делать?")

        assert state.status == "ESCALATED"
        assert state.incident_id == open_incidents(session)[0].id


def test_seeded_metrics_still_load(factory):
    seed(total=12, session_factory=factory)
    seed_incident(session_factory=factory)

    with factory() as session:
        metrics = AdminService(session, "http://localhost").metrics(7)
        assert metrics["total"] >= 5
        assert metrics["open"] >= 4


def test_seed_loads_the_demo_company_documents(factory):
    from app.models.knowledge import KnowledgeDocument
    from app.seed_demo import seed_documents

    seed(total=12, session_factory=factory)

    assert seed_documents(session_factory=factory) == 3
    assert seed_documents(session_factory=factory) == 0, "a second run adds nothing"
    with factory() as session:
        documents = session.query(KnowledgeDocument).all()
        assert sorted(d.title for d in documents) == ["Инструкция по VPN", "Правила паролей", "Регламент командировок"]
        assert all(d.status == "ready" and d.chunks for d in documents)


def test_employee_gets_an_answer_from_a_seeded_document(factory):
    from app.seed_demo import seed_documents

    seed(total=12, session_factory=factory)
    seed_documents(session_factory=factory)
    with factory() as session:
        service = TriageDialogueService(ConversationRepository(session), TriageEngine(KnowledgeBase.load(), None))
        conversation = service.create_conversation()
        session.commit()
        answered = service.handle_message(conversation.id, "Какие суточные положены в командировке по России?")

    assert answered.answer_kind == "document"
    assert "700 рублей" in answered.messages[-1].content
